"""PR5: LLM-assisted treatment classifier (v2).

v1 (:mod:`apps.corpus.services.treatment`) is a high-recall phrase scanner — it
flags every citing sentence carrying a negative stem near the target's reporter
cite. That deliberately over-flags: "In re Weidman ... should be overruled" flags
the *wrong* case when Weidman sits beside the target's cite; "overruled on other
grounds" survivors; and it can't read intent (distinguish vs. abrogate). This
module is the high-precision second pass.

For a v1 candidate, an LLM reads the **citing paragraph** + the **target's
identity** + the **citing court level** and decides whether the TARGET (not some
other case in the paragraph) is actually treated negatively, at what tier, with a
verbatim evidence span and a confidence. It reuses the
:mod:`apps.corpus.services.semantic_support` OpenAI-call shape (JSON mode, cheap
model default, graceful degradation, dependency-injectable for tests).

Pipeline role: v1 generates candidates cheaply and over-broadly; v2 confirms /
refines (one LLM call per candidate, the annotate command gates by citation depth
so budget goes to deep engagements). ``source="llm"``. A low-confidence verdict
becomes ``status="unknown"`` so we never *assert* bad law on a guess.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings

log = logging.getLogger(__name__)

# Fixed treatment vocabulary the model must choose from, mapped to v1's 0–5
# severity scale (so v2 flags compose with v1 flags and ``_STATUS_BY_SEVERITY``).
# severity is derived HERE from the label — we never trust the model to compute a
# number consistently, only to pick a category.
LABEL_SEVERITY: dict[str, int] = {
    "overruled": 5,
    "abrogated": 5,
    "superseded": 5,
    "repudiated": 5,
    "disapproved": 4,
    "no-longer-good-law": 4,
    "declined-to-follow": 4,
    "criticized": 4,
    "questioned": 4,
    "limited": 3,
    "distinguished": 3,
    "none": 0,
}

# The same status mapping v1 uses (kept local to avoid importing the v1 module's
# private name): 5 → negative, 3–4 → caution, else good/unknown handled by caller.
_STATUS_BY_SEVERITY = {5: "negative", 4: "caution", 3: "caution", 0: "good"}

# Below this confidence we do not assert a negative finding — the verdict is
# downgraded to ``unknown`` (route to a human / leave the case unflagged) rather
# than risk telling a lawyer a good case is dead on a shaky read.
DEFAULT_MIN_CONFIDENCE = 0.55

_DEFAULT_MODEL = "gpt-4o"
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_PREFIXES)


SYSTEM_PROMPT = (
    "You are a legal citator. You decide whether a CITING opinion treats a "
    "specific TARGET decision negatively — i.e. undercuts the target as good "
    "law. You are given the target case's name and reporter citation, the citing "
    "case's name and court level, and a paragraph from the citing opinion that "
    "mentions the target.\n\n"
    "Choose exactly one label for how the citing court treats the TARGET. The "
    "\"label\" field must be EXACTLY ONE of these tokens, verbatim, never a list "
    "or a group: overruled, abrogated, superseded, repudiated, disapproved, "
    "no-longer-good-law, declined-to-follow, criticized, questioned, limited, "
    "distinguished, none.\n\n"
    "What they mean:\n"
    "  • overruled, abrogated, superseded, repudiated — the target is no "
    "longer good law (severity: invalidated). Pick the one word the court uses.\n"
    "  • disapproved, no-longer-good-law, declined-to-follow, criticized, "
    "questioned — the target is undercut but not formally killed.\n"
    "  • limited, distinguished — the target survives; the court merely narrows "
    "it or sets it aside on the facts (a caution, not an invalidation).\n"
    "  • none — the target is NOT treated negatively in this paragraph.\n\n"
    "Decide 'none' (this is the default — prefer it whenever unsure) when:\n"
    "  • the negative word is about a TRIAL-COURT RULING, not case law — "
    "'overruled the objection / the motion / the demurrer'.\n"
    "  • the negative treatment is about a DIFFERENT case mentioned in the "
    "paragraph, not the target. Read carefully: the target_is_subject field must "
    "be true ONLY if the target itself is the case being undercut.\n"
    "  • it is hypothetical / negated / a request — 'declined to overrule', 'we "
    "need not overrule', 'asked us to overrule', 'ought to be overruled' "
    "(a dissent's wish).\n"
    "  • the TARGET is the one DOING the overruling (the target is the agent: "
    "'[target], overruling X').\n"
    "  • 'overruled on other grounds' / 'overruled in part' — the target still "
    "stands for the point it is cited for: use 'limited', not 'overruled'.\n\n"
    "Quote a VERBATIM span from the supplied paragraph as evidence (empty string "
    "if label is none). Give a confidence in [0,1] for your label. Judge ONLY "
    "from the supplied paragraph — never use outside knowledge of the cases.\n\n"
    'Respond with ONLY a JSON object: {"label": "...", "target_is_subject": '
    'true|false, "evidence": "...", "confidence": 0.0}.'
)


@dataclass
class LLMTreatmentVerdict:
    """One LLM verdict for a (citing opinion, target) pair."""

    label: str
    severity: int
    status: str
    target_is_subject: bool
    evidence: str
    confidence: float
    # True when no verdict was obtained at all (API error, rate limit, parse
    # failure) — distinct from a genuine low-confidence read so a batch can count
    # failures instead of silently reporting them as "uncertain, kept v1".
    error: bool = False

    @property
    def is_negative(self) -> bool:
        """True when the model affirmatively found a real negative treatment of
        the target (subject confirmed, a non-``none`` label, severity ≥ 3)."""
        return (
            self.target_is_subject
            and self.label != "none"
            and self.severity >= 3
        )


# A verdict that asserts nothing — used for empty input, no key, parse failure, or
# a sub-threshold confidence. status "unknown" so the caller does not persist it.
UNKNOWN_VERDICT = LLMTreatmentVerdict(
    label="none", severity=0, status="unknown",
    target_is_subject=False, evidence="", confidence=0.0,
)

# UNKNOWN plus the error bit: the call itself failed, nothing was classified.
FAILED_VERDICT = LLMTreatmentVerdict(
    label="none", severity=0, status="unknown",
    target_is_subject=False, evidence="", confidence=0.0, error=True,
)


class TreatmentClassifier(Protocol):
    def classify(
        self,
        *,
        target_name: str,
        target_citation: str,
        citing_name: str,
        citing_court_level: int | None,
        paragraph: str,
    ) -> LLMTreatmentVerdict:
        ...


@dataclass
class OpenAITreatmentClassifier:
    """One OpenAI chat-completion call per (citing opinion, target) candidate."""

    model: str = _DEFAULT_MODEL
    api_key: str | None = None
    max_tokens: int = 500

    def _key(self) -> str:
        return self.api_key or getattr(settings, "OPENAI_API_KEY", "")

    def classify(
        self,
        *,
        target_name: str,
        target_citation: str,
        citing_name: str,
        citing_court_level: int | None,
        paragraph: str,
    ) -> LLMTreatmentVerdict:
        if not paragraph.strip():
            return UNKNOWN_VERDICT
        key = self._key()
        if not key:
            return UNKNOWN_VERDICT
        try:
            from openai import OpenAI
        except ImportError:
            log.warning("openai SDK not installed; treatment v2 unavailable")
            return UNKNOWN_VERDICT

        level = {1: "supreme court", 2: "court of appeals"}.get(
            citing_court_level or 0, "unknown"
        )
        user = (
            f"TARGET case: {target_name or '(unknown)'}\n"
            f"TARGET citation: {target_citation or '(unknown)'}\n"
            f"CITING case: {citing_name or '(unknown)'} (court: {level})\n\n"
            f"PARAGRAPH FROM THE CITING OPINION:\n{paragraph}"
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
            kwargs["max_completion_tokens"] = max(self.max_tokens, 4000)
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["max_tokens"] = self.max_tokens
            kwargs["temperature"] = 0
        try:
            # Batch runs sit at the org's tokens-per-minute ceiling; the SDK's
            # built-in backoff honors Retry-After on 429, so give it room.
            client = OpenAI(api_key=key, max_retries=8)
            resp = client.chat.completions.create(**kwargs)
            # Token accounting (lazy import — see semantic_support for why).
            # Batch runs have no collector open, so these land unattributed —
            # which is correct: citator spend is platform spend, not a user's.
            from apps.api.usage import FEATURE_TREATMENT, emit_completion_usage

            emit_completion_usage(FEATURE_TREATMENT, resp, fallback_model=self.model)
            text = resp.choices[0].message.content or ""
        except Exception:  # noqa: BLE001 — a model failure must not crash a batch
            log.exception("treatment v2 classify failed")
            return FAILED_VERDICT
        return parse_verdict(text)


def _coerce_label(raw) -> str | None:
    """Map the model's ``label`` onto the fixed vocabulary. Exact match first;
    otherwise, when the model echoes a whole prompt group ("overruled / abrogated
    / superseded / repudiated" — observed on gpt-4o), take the FIRST token in that
    group that is a known label (the groups are listed most-severe first). A
    label with no known token at all is ``None``."""
    label = str(raw or "").strip().lower()
    if label in LABEL_SEVERITY:
        return label
    for tok in re.split(r"[\s/,|]+", label):
        if tok in LABEL_SEVERITY:
            return tok
    return None


def parse_verdict(text: str) -> LLMTreatmentVerdict:
    """Parse the model JSON defensively into a verdict — format/severity only, NO
    policy. A malformed response or an unknown label degrades to
    :data:`UNKNOWN_VERDICT` (label none / confidence 0), which the caller's
    confidence policy then treats as 'uncertain' (keeps the v1 flag) rather than a
    rejection. The keep/drop/override decision lives in the annotate command so it
    can act only when the model is confident."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return UNKNOWN_VERDICT
    if not isinstance(data, dict):
        return UNKNOWN_VERDICT

    label = _coerce_label(data.get("label", ""))
    if label is None:
        return UNKNOWN_VERDICT
    # Defensive like the other fields: a quoted-string boolean ("false") would
    # be truthy under a bare bool(), flipping a confident NOT-subject rejection
    # into a kept flag — the unsafe (false-negative-treatment) direction.
    raw_subject = data.get("target_is_subject", False)
    subject = (
        raw_subject if isinstance(raw_subject, bool)
        else str(raw_subject).strip().lower() in ("true", "1", "yes")
    )
    evidence = str(data.get("evidence", "")).strip()
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    severity = LABEL_SEVERITY[label]
    return LLMTreatmentVerdict(
        label=label,
        severity=severity,
        status=_STATUS_BY_SEVERITY.get(severity, "caution"),
        target_is_subject=subject,
        evidence=evidence,
        confidence=confidence,
    )


def default_treatment_classifier() -> TreatmentClassifier | None:
    """Real classifier when an OpenAI key is configured, else ``None`` (the
    annotate command then runs v1-only)."""
    if getattr(settings, "OPENAI_API_KEY", ""):
        return OpenAITreatmentClassifier()
    return None


def paragraph_around(body: str, evidence: str, *, window: int = 700) -> str:
    """Extract the citing paragraph: a window of ``body`` centered on the v1
    ``evidence`` sentence (the lexical trigger), so the LLM sees the surrounding
    context that disambiguates which case is being treated. Falls back to the
    evidence sentence alone if it can't be located."""
    if not body or not evidence:
        return evidence or ""
    probe = evidence[:80]
    idx = body.find(probe)
    if idx == -1:
        # The v1 evidence sentence comes from the NORMALIZED body (PDF hyphen
        # wraps repaired, mid-sentence ``\n\n`` collapsed), so it rarely occurs
        # verbatim in the raw text. Search the same normalization instead.
        from apps.corpus.services.treatment import _normalize_body

        body = _normalize_body(body)
        idx = body.find(probe)
        if idx == -1:
            return evidence
    lo = max(0, idx - window)
    hi = min(len(body), idx + len(evidence) + window)
    return body[lo:hi]
