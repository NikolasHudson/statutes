"""Semantic support check for paraphrased claims (Verify Document, Phase 1.3).

Verbatim quotes are graded deterministically (string match against the cited
provision). But a document often *paraphrases* what a provision says without
quotation marks — "Section 364.22 requires a municipality to file a formal
municipal infraction." That assertion can be just as fabricated as a fake
quote, and a string match can't catch it. This module asks a small LLM whether
the cited provision actually **supports**, only **partially** supports, or
**contradicts** each such claim.

Uses the same OpenAI key the chat endpoint spends (``settings.OPENAI_API_KEY``)
and a cheap model. ``default_checker()`` returns ``None`` when no key is
configured — in which case the verifier skips the paraphrase layer and grades
verbatim-only (it does NOT blanket-yellow every cite). A per-call failure, by
contrast, yields ``unverified`` for that one claim so the citation is honestly
flagged yellow rather than passed as confirmed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings


log = logging.getLogger(__name__)

# Verdicts. ``no_claim`` means the sentence cites the provision but asserts
# nothing checkable ("see § 714.16") — neutral, doesn't affect the cite's color.
SUPPORTED = "supported"
PARTIAL = "partial"
CONTRADICTED = "contradicted"
UNVERIFIED = "unverified"
NO_CLAIM = "no_claim"

_VALID_VERDICTS = {SUPPORTED, PARTIAL, CONTRADICTED, NO_CLAIM}

# The checker uses whichever model the caller passes (the chat surface threads
# through the user's selected model). This default is only used when no model is
# supplied — gpt-4o is stable and legally sound; gpt-4o-mini proved too weak and
# run-to-run-inconsistent on nuanced legal reasoning (e.g. that a subsection
# tolls a deadline).
_DEFAULT_MODEL = "gpt-4o"

# Reasoning-tier models (gpt-5 / o-series) reject ``temperature`` and
# ``max_tokens`` and instead take ``max_completion_tokens`` + ``reasoning_effort``
# — same split the chat endpoint handles. They also spend hidden reasoning
# tokens, so they need a larger completion budget to still emit the JSON.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_PREFIXES)


SYSTEM_PROMPT = (
    "You verify whether a legal source text supports factual claims made about "
    "it. You are given the full text of ONE statutory provision or court rule "
    "(it may contain several numbered/lettered subsections), and a numbered "
    "list of claim sentences from a document that cite it.\n"
    "\n"
    "If a claim cites a specific subsection — e.g. (2), (1)(b), 1.904(2) — judge "
    "it primarily against THAT subsection's text within the source, using the "
    "rest of the rule only for context. BUT if the cited subsection does not "
    "support the claim while ANOTHER subsection of the same rule clearly does "
    "(the author cited the wrong subsection of the RIGHT rule), that is "
    '"partial" (wrong subsection) — NOT "contradicted". E.g. a claim cites '
    "2.19(8) for a motion for judgment of acquittal, but the rule places that "
    'motion in 2.19(7) → "partial".\n'
    "\n"
    "A claim sentence may cite MORE THAN ONE provision and bundle separate "
    "assertions (one per citation). You are evaluating THIS source only. Judge "
    "ONLY the portion of the sentence that pertains to THIS provision; ignore "
    "clauses that are clearly tied to a different citation. Do not penalize this "
    "provision for an assertion that belongs to another cited rule.\n"
    "\n"
    "Classify each claim STRICTLY from the supplied text:\n"
    '  - "supported": the source supports the claim. This INCLUDES reasonable '
    "legal characterizations or applications of the rule to facts, and "
    "correct paraphrases, even if not word-for-word.\n"
    '  - "partial": the source genuinely supports the CORE proposition of the '
    "claim, but the claim overstates or narrows it, attributes content to the "
    "wrong subsection, or mixes in a detail the provision does not address.\n"
    '  - "contradicted": EITHER the source states something LOGICALLY '
    "INCOMPATIBLE with the claim (a different number/deadline — claim says 60 "
    "days, source says 30; the opposite requirement; or the source expressly "
    "PERMITS the very thing the claim says it forbids), OR the source is about "
    "a DIFFERENT SUBJECT and provides no support for the claim's core "
    "proposition at all (a miscitation — e.g. the claim is about gambling "
    "consideration but the cited section is about abolishing seals).\n"
    '  - "no_claim": the sentence merely references the provision and asserts '
    "nothing checkable.\n"
    "\n"
    "IMPORTANT — first ask: does the cited provision GOVERN THE SUBJECT MATTER "
    "of the claim at all?\n"
    "  • If YES (same subject), and the claim merely overstates, narrows, or "
    "adds a detail the provision is silent on, that is NOT a contradiction — a "
    'mere omission never makes a contradiction. Choose "supported" or '
    '"partial". Example: the claim says a city "must enforce ordinance '
    'violations by municipal infraction rather than by fund seizure"; the '
    "cited section IS the municipal-infractions statute but is permissive and "
    'silent on fund seizures → "partial" (on-topic, overstated), NOT '
    '"contradicted".\n'
    "  • If NO (the provision governs a DIFFERENT subject entirely), it cannot "
    "support the claim no matter how the claim is phrased — this is a "
    'miscitation → "contradicted". Example: the claim is about a gambling '
    "contract being void for illegal consideration, but the cited section is "
    'about abolishing private seals → "contradicted". Never use "partial" as a '
    "soft landing for a provision that does not govern the claim's subject.\n"
    "\n"
    "NUMBERS ARE NOT APPROXIMATE: if the source states a specific number, "
    "deadline, or monetary amount and the claim states a DIFFERENT one, that is "
    'a "contradicted" — even when the surrounding wording matches. E.g. the '
    'claim says a writing is required for goods over "$50" but the statute says '
    '"five hundred dollars or more" → "contradicted" (a 10x threshold error), '
    'NOT "partial".\n'
    "\n"
    "INVERSE APPLICATION IS SUPPORT: legal argument routinely runs a rule "
    "backwards. If a rule defines X as requiring feature Y, a claim that "
    "something is NOT X because it lacks Y is a correct application of that "
    'rule → "supported" (not "partial"). E.g. the rule defines hearsay as a '
    "statement offered to prove the truth of the matter asserted; a claim that "
    "a statement is non-hearsay because it is NOT offered for its truth is "
    '"supported".\n'
    "\n"
    "Judge only against the supplied text — never use outside knowledge. For "
    "each claim provide a short verbatim evidence span from the source (empty "
    "string if none). Respond with ONLY a JSON object of the form "
    '{"results": [{"verdict": "...", "evidence": "..."}]} — one entry per '
    "claim, in order."
)


@dataclass
class SemanticVerdict:
    verdict: str  # one of the constants above
    evidence: str = ""


class SemanticChecker(Protocol):
    def check_claims(
        self, claims: list[str], source_text: str
    ) -> list[SemanticVerdict]:
        ...


@dataclass
class OpenAIChecker:
    """Grades paraphrased claims with one OpenAI chat-completion call per
    citation (all of that cite's claims batched). JSON mode keeps the response
    machine-parseable."""

    model: str = _DEFAULT_MODEL
    api_key: str | None = None
    max_tokens: int = 700

    def _key(self) -> str:
        # Settings is the source of truth (django-environ loads it from .env),
        # same as the chat endpoint — keeps the key overridable in tests.
        return self.api_key or getattr(settings, "OPENAI_API_KEY", "")

    def check_claims(
        self, claims: list[str], source_text: str
    ) -> list[SemanticVerdict]:
        if not claims:
            return []
        key = self._key()
        if not key:
            return [SemanticVerdict(UNVERIFIED) for _ in claims]
        try:
            from openai import OpenAI
        except ImportError:
            log.warning("openai SDK not installed; semantic check unavailable")
            return [SemanticVerdict(UNVERIFIED) for _ in claims]
        numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims))
        user = (
            f"SOURCE TEXT:\n{source_text}\n\n"
            f"CLAIMS ({len(claims)}):\n{numbered}"
        )
        kwargs: dict = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        }
        if _is_reasoning_model(self.model):
            # Reasoning spends hidden tokens before the JSON; give it headroom
            # and keep effort low (this is bounded classification, not analysis).
            kwargs["max_completion_tokens"] = max(self.max_tokens, 4000)
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["max_tokens"] = self.max_tokens
            kwargs["temperature"] = 0
        try:
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(**kwargs)
            # Token accounting (lazy import: corpus must not hard-depend on
            # the api app at module load). Attributed to the active turn's
            # user when a collector is open, unattributed otherwise.
            from apps.api.usage import FEATURE_VERIFICATION, emit_completion_usage

            emit_completion_usage(
                FEATURE_VERIFICATION, resp, fallback_model=self.model
            )
            text = resp.choices[0].message.content or ""
            return _parse_verdicts(text, len(claims))
        except Exception:  # noqa: BLE001 — never let a model failure break verify
            log.exception("semantic support check failed")
            return [SemanticVerdict(UNVERIFIED) for _ in claims]


def _parse_verdicts(text: str, n: int) -> list[SemanticVerdict]:
    """Parse the model's JSON defensively; pad/truncate to ``n`` and mark
    anything unparseable as ``unverified`` so a bad response degrades to a
    yellow rather than a silent pass."""
    out: list[SemanticVerdict] = []
    try:
        data = json.loads(text)
        rows = data.get("results") if isinstance(data, dict) else data
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    out.append(SemanticVerdict(UNVERIFIED))
                    continue
                verdict = str(item.get("verdict", "")).strip().lower()
                if verdict not in _VALID_VERDICTS:
                    verdict = UNVERIFIED
                out.append(
                    SemanticVerdict(verdict, str(item.get("evidence", "")).strip())
                )
    except (json.JSONDecodeError, AttributeError, TypeError):
        out = []
    out = out[:n]
    out += [SemanticVerdict(UNVERIFIED) for _ in range(n - len(out))]
    return out


def default_checker() -> SemanticChecker | None:
    """Real checker when an OpenAI key is configured, else None (paraphrase
    layer disabled — verbatim grading still runs)."""
    if getattr(settings, "OPENAI_API_KEY", ""):
        return OpenAIChecker()
    return None
