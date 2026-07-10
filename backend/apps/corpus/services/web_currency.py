"""PR9: web currency tripwire — durable research notes on cases.

Promoted from the 2026-07-10 standalone experiment
(benchmarks/web_adverse_layer_test.py: 30 cases → 4/4 precision, 3 novel
catches incl. Nahas→Doe 2025, 0 false positives, 1 false negative — Pexa's
quiet statutory supersession — which is why this layer COMPLEMENTS the
supersession mining pipeline rather than replacing it).

Flow: verification time only, for cases the answer RELIES on (answer.py owns
that detection). First reliance on a case runs one web-search call (OpenAI
Responses ``web_search``) asking "is this still good law?"; the verdict is
persisted as a ``CaseResearchNote`` on the decision node, so every future
turn — any surface — reads the note instead of re-searching. CLEAR notes
re-check after a freshness window; ADVERSE notes persist and go to the
attorney review queue (corpus admin). Only adverse + CORPUS-VERIFIED +
not-rejected notes ever reach an advisory. Web text never enters generation.

Same opt-in posture as PR5/PR8: ``RAG_WEB_CURRENCY_CHECK`` default off,
injectable checker for tests, every failure degrades to "no note".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from django.conf import settings
from django.utils import timezone

from apps.corpus.models import CaseResearchNote, Node, ReporterCitation

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-5-mini"

_ADVERSE_KINDS = {"overruled", "superseded_by_statute", "caution"}

_PROMPT = """You are checking whether an Iowa appellate case is still good law.

Case: {heading}
Citation(s): {citation}{topic_line}

Search the web for credible indications this case has been overruled, abrogated,
superseded by statute, or otherwise negatively treated (court opinions,
legislative history, bar journals, reputable annotators). Statutory supersession
is the easiest to miss: ALSO search whether the Iowa legislature has enacted or
amended a statute that displaces the case's rule on the topic it is being cited
for — a case can be quietly superseded by statute without any court saying so.
Distinguish real negative treatment from mere criticism or distinguishing.

Reply with ONLY a JSON object, no prose:
{{"adverse": true/false,
  "kind": "overruled" | "superseded_by_statute" | "caution" | "none",
  "by": "<the overruling case or superseding statute, as specifically as possible>",
  "evidence": "<one short quoted/paraphrased sentence>",
  "source_url": "<best source url or empty>"}}

adverse=false with kind "none" if it appears to be good law or you find nothing
credible. Do not guess: an empty result is better than a fabricated one."""

_SECTION_RE = re.compile(r"\b(\d{1,3}[A-Z]?\.\d+[A-Z]?)\b")
_REPORTER_RE = re.compile(r"\b(\d{1,4})\s+(N\.W\.\s?[23]?d?|Iowa)\s+(\d{1,5})\b")
_CASE_NAME_RE = re.compile(r"([A-Z][A-Za-z']+)\s+v\.?\s+([A-Z][A-Za-z']+)")


class WebCurrencyChecker(Protocol):
    model: str

    def check(
        self, heading: str, citation: str, topic: str = ""
    ) -> dict[str, Any] | None: ...


@dataclass
class OpenAIWebCurrencyChecker:
    """One Responses-API web_search call per case. Returns a verdict dict or
    ``None`` on any failure (timeout, refusal, parse) — no note, no problem."""

    api_key: str = ""
    model: str = _DEFAULT_MODEL
    timeout: float | None = None

    def check(
        self, heading: str, citation: str, topic: str = ""
    ) -> dict[str, Any] | None:
        key = self.api_key or getattr(settings, "OPENAI_API_KEY", "")
        if not key:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        timeout = self.timeout or getattr(settings, "RAG_WEB_CURRENCY_TIMEOUT", 40)
        # The topic is what makes quiet statutory supersession findable: "is
        # Pexa good law" finds nothing, but "…relied on for billed-vs-paid
        # medical expense evidence" surfaces the §668.14A discussions.
        topic_line = (
            f"\nThe answer relies on this case for: {topic[:400]}" if topic else ""
        )
        try:
            # max_retries=0: a timed-out check must FAIL FAST, not silently
            # triple the latency — the design already tolerates a missed check
            # (the case is simply re-tried under a future answer's budget).
            client = OpenAI(api_key=key, timeout=timeout, max_retries=0)
            resp = client.responses.create(
                model=self.model,
                tools=[{"type": "web_search"}],
                input=_PROMPT.format(
                    heading=heading,
                    citation=citation or "(none)",
                    topic_line=topic_line,
                ),
            )
            text = (resp.output_text or "").strip()
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
            data = json.loads(text)
        except Exception:  # noqa: BLE001 — a web failure must not break verify
            logger.warning("web currency check failed for %s", citation or heading)
            return None
        if not isinstance(data, dict):
            return None
        kind = str(data.get("kind") or "none")
        return {
            "adverse": bool(data.get("adverse")) and kind in _ADVERSE_KINDS,
            "kind": kind if kind in _ADVERSE_KINDS else "none",
            "by": str(data.get("by") or "")[:300],
            "evidence": str(data.get("evidence") or "")[:1000],
            "source_url": str(data.get("source_url") or "")[:500],
        }


def default_checker() -> WebCurrencyChecker | None:
    if not getattr(settings, "OPENAI_API_KEY", ""):
        return None
    return OpenAIWebCurrencyChecker()


def corpus_verify(claimed_by: str) -> tuple[bool, list[str]]:
    """Does the authority the web names resolve against OUR corpus? Statute
    section → live lookup; reporter cite → ReporterCitation; else case-name
    heading match. Unverifiable claims are stored for review but never shown."""
    from apps.corpus.services.lookups import lookup_citation

    matches: list[str] = []
    for sec in _SECTION_RE.findall(claimed_by)[:4]:
        try:
            r = lookup_citation(f"Iowa Code § {sec}")
        except Exception:  # noqa: BLE001
            continue
        node = getattr(r, "node", None)
        if node is not None:
            matches.append(f"statute {sec}: {node.heading[:60]}")
    for vol, rep, page in _REPORTER_RE.findall(claimed_by)[:4]:
        rep_norm = rep.replace(" ", "")
        if ReporterCitation.objects.filter(
            reporter=rep_norm, volume=vol, page=page, to_node__isnull=False
        ).exists():
            matches.append(f"case cite {vol} {rep_norm} {page}")
    if not matches:
        m = _CASE_NAME_RE.search(claimed_by)
        if m:
            hit = (
                Node.objects.filter(
                    source__slug="iowa-caselaw", heading__icontains=m.group(1)
                )
                .filter(heading__icontains=m.group(2))
                .first()
            )
            if hit is not None:
                matches.append(f"case name: {hit.heading[:60]}")
    return bool(matches), matches


def note_is_current(note: CaseResearchNote | None) -> bool:
    """True when the stored note answers the question without a new web call:
    any ADVERSE note (they persist; review governs them), or a CLEAR note
    inside the freshness window."""
    if note is None:
        return False
    if note.status == CaseResearchNote.Status.ADVERSE:
        return True
    max_age = getattr(settings, "RAG_WEB_CURRENCY_MAX_AGE_DAYS", 30)
    return note.checked_at >= timezone.now() - timedelta(days=max_age)


def get_note(cluster_id: int) -> CaseResearchNote | None:
    return CaseResearchNote.objects.filter(
        node_id=cluster_id, kind=CaseResearchNote.Kind.WEB_CURRENCY
    ).first()


def check_and_store(
    cluster_id: int,
    heading: str,
    citation: str,
    checker: WebCurrencyChecker,
    topic: str = "",
) -> CaseResearchNote | None:
    """Run the web check for one decision node and persist the verdict.
    Returns the stored (or pre-existing) note; ``None`` when the node doesn't
    exist or the check failed. An attorney's REJECTED verdict on the same
    claimed authority is preserved across re-checks; a NEW claimed authority
    reopens review."""
    node = Node.objects.filter(pk=cluster_id).first()
    if node is None:
        return None
    existing = get_note(cluster_id)
    verdict = checker.check(heading, citation, topic=topic)
    if verdict is None:
        return existing

    if verdict["adverse"]:
        status = CaseResearchNote.Status.ADVERSE
        verified, matches = corpus_verify(verdict["by"])
    else:
        status = CaseResearchNote.Status.CLEAR
        verified, matches = False, []

    review = CaseResearchNote.Review.PENDING
    if (
        existing is not None
        and existing.review_status == CaseResearchNote.Review.REJECTED
        and existing.claimed_by == verdict["by"]
    ):
        review = CaseResearchNote.Review.REJECTED

    note, _ = CaseResearchNote.objects.update_or_create(
        node=node,
        kind=CaseResearchNote.Kind.WEB_CURRENCY,
        defaults={
            "status": status,
            "adverse_kind": verdict["kind"] if verdict["adverse"] else "",
            "claimed_by": verdict["by"] if verdict["adverse"] else "",
            "evidence": verdict["evidence"] if verdict["adverse"] else "",
            "source_url": verdict["source_url"] if verdict["adverse"] else "",
            "corpus_verified": verified,
            "corpus_matches": matches,
            "review_status": review,
            "model": getattr(checker, "model", ""),
            "checked_at": timezone.now(),
        },
    )
    return note


def advisory_worthy(note: CaseResearchNote | None) -> bool:
    """Only adverse, corpus-verified, not-attorney-rejected notes surface."""
    return (
        note is not None
        and note.status == CaseResearchNote.Status.ADVERSE
        and note.corpus_verified
        and note.review_status != CaseResearchNote.Review.REJECTED
    )
