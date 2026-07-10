"""Shared answer-layer helpers: deterministic citation/quote verification,
stale-use (negative-treatment) detection, and the abstain / block decision.

PR4 extracts the post-hoc *answer gate* out of ``apps.api.chat`` so chat (and any
future answer-producing surface) call one verified path instead of re-implementing
it. The OpenAI tool-calling loop stays in ``chat.py`` — only the deterministic
checks that run *after* the model drafts an answer live here:

* :func:`verify_answer` — resolve every cited section against the corpus and
  check that quoted spans are near-verbatim (moved verbatim from the chat gate),
  **plus** the new caselaw **stale-use** check: did the drafted answer rely on a
  case the retrieved context flags ``negative`` (overruled / abrogated /
  superseded) *without acknowledging* that treatment?
* :func:`render_advisory` — the human-readable "could not be confirmed" block
  (moved), extended with stale-use warnings.
* :func:`should_abstain` / :func:`abstain_decision` — the "no good-law authority
  retrieved" signal and the policy that turns it (and silent stale-use) into a
  withheld answer **only** when ``settings.RAG_ABSTAIN_BLOCKING`` is on. Default
  is advisory: the answer is shown with warnings, never suppressed.

The MCP surface returns structured passages (no drafted answer to verify), so it
only consumes :func:`should_abstain` for its additive ``abstain`` field.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from django.conf import settings

from apps.corpus.models import Source
from apps.corpus.services import applicability, semantic_support, web_currency
from apps.corpus.services.lookups import validate_citations, verify_quotes
from apps.corpus.services.retrieval import RetrievedContext, RetrievedPassage

# ---------------------------------------------------------------------------
# Helpers moved verbatim from apps.api.chat (the answer gate). ``verify_document``
# keeps its own copies for the *document*-centric path; this is the answer path.
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
# Dollar amounts ("$7.25", "$1,000.50") parse as section-shaped citations
# ("7.25") and would be flagged as fabricated — statutory text and answers are
# full of them (minimum wage, fees, thresholds). Strip before scanning.
_MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_WS_RE = re.compile(r"\s+")

# Precedence when one citation is resolved against several sources: a citation
# that resolves *valid* in ANY loaded source is good law, even if it is
# not_found in the others. Higher rank wins the collapse.
_STATUS_RANK = {"valid": 3, "repealed": 1, "not_found": 0, "parse_error": 0}


def _is_real_section(citation) -> bool:
    """True only when the part after the chapter is numeric — a genuine
    section ("714.16", "32:1.10", "708.2A" → rest "16"/"1.10"/"2A"). Statutory
    answers enumerate subsection markers like "1.d", "2.a", "2.d(1)" that parse
    as section-shaped citations but are NOT standalone citations; their rest
    starts with a letter, so this filters them out for both corpora (real Code
    and Court Rule section numbers always start the rest with a digit)."""
    section = citation.section or ""
    chapter = citation.chapter or ""
    rest = section[len(chapter) + 1:] if section.startswith(chapter) else section
    return bool(rest) and rest[0].isdigit()


def _normalize_for_match(text: str) -> str:
    """Lowercase, unify quote glyphs, and collapse whitespace so a quoted
    passage can be compared against rule text without tripping on smart quotes
    or reflowed line breaks."""
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    # Unify hyphen/dash glyphs so "attorney-client" (U+2011 non-breaking
    # hyphen, en/em dashes) matches the plain "-" used in the rule text.
    for dash in ("‐", "‑", "‒", "–", "—"):
        text = text.replace(dash, "-")
    return _WS_RE.sub(" ", text).strip().lower()


# ---------------------------------------------------------------------------
# PR4: stale-use detection — did the drafted answer rely on a negative-treatment
# case from the retrieved context, without acknowledging the treatment?
# ---------------------------------------------------------------------------

# Severity at/above which a silently-used negative case is "invalidated" — the
# tier ``abstain_decision`` hard-blocks when ``RAG_ABSTAIN_BLOCKING`` is on. By
# construction the v1 classifier only assigns ``status="negative"`` at severity 5
# (overruled/abrogated/superseded/repudiated), so the default threshold of 5
# blocks exactly the negative set; the knob exists to raise the bar later.
STALE_BLOCK_SEVERITY = 5

# Iowa reporter-cite core ("763 N.W.2d 862", "200 Iowa 123", "5 Iowa App. 45"),
# matched against text already lowercased+ws-collapsed by ``_normalize_for_match``
# (so the dots in "n.w.2d" survive). A pincite ("778 n.w.2d at 40") is matched by
# the volume+reporter prefix below, not this full form.
_REPORTER_RE = re.compile(
    r"\b\d{1,4}\s+(?:n\.w\.(?:2d|3d)?|iowa(?:\s+app\.)?)\s+\d{1,4}\b"
)
# A case caption contains a " v. " (or starts "in re"). Used to decide whether a
# passage heading is a citable case name worth matching against the answer.
_CASE_V_RE = re.compile(r"\bv\.?\s")
# Cue words that signal the answer is *discussing* a case's negative treatment
# (so it is handling the stale case correctly, not relying on it as good law).
# Scoped to the treatment vocabulary itself (mirrors the classifier's
# ``_NEG_STEMS``). Generic verbs like "reject"/"abandon"/"invalidate" were
# deliberately dropped: even confined to the anchor's sentence they match benign
# analysis ("the court rejected the argument") and would fail OPEN — marking a
# silent reliance as acknowledged, the dangerous direction. ``supersed`` is
# bounded so it can't fire on "supersedeas" (the bond term).
_TREATMENT_CUE_RE = re.compile(
    r"\boverrul(?:e|ed|es|ing)\b|\babrogat\w*|\bsupersed(?:e|ed|es|ing)\b|"
    r"\brepudiat\w*|\bdisapprov\w*|"
    r"\bno longer (?:good law|controlling|the law|valid)\b|"
    r"\bdeclin\w*\s+to\s+(?:follow|extend)\b|\bnegative(?:ly)?\s+treat\w*",
    re.I,
)
# Sentence segmentation for the acknowledgment scan. We confine acknowledgment to
# the SAME sentence as the case mention (a cue about a *different* case one
# sentence over must not excuse a silent reliance on this one), but legal prose is
# dense with abbreviations whose period is NOT a sentence end — "State v. Later",
# "(Iowa App. 1991)", "Co.", "Inc.", "No." — and treating those as boundaries
# would split an acknowledgment away from the case it modifies. So a candidate
# boundary ("[.?;]" + whitespace, or a newline) only counts when the token ending
# at it is not a known abbreviation.
_SENT_PUNCT = re.compile(r"[.?;]\s|\n")
_TRAIL_WORD = re.compile(r"([a-z0-9]+)\)?$")
_ABBREV = frozenset(
    {
        "v", "vs", "no", "nos", "co", "inc", "corp", "ltd", "llc", "lp", "app",
        "ct", "cts", "id", "ed", "eds", "al", "etc", "dept", "div", "assn",
        "bros", "jr", "sr", "st", "mt", "dr", "mr", "ms", "mrs", "prof", "rev",
        "cf", "eg", "ie", "n", "w", "e", "s", "u", "p", "pp", "f", "a", "ch",
        "sec", "art", "para", "vol", "fed", "supp",
    }
)


def _is_sentence_boundary(norm: str, dot_idx: int) -> bool:
    """A candidate punctuation+space at ``dot_idx`` is a real sentence end unless
    the word it terminates is a known abbreviation (so "App."/"Co."/"v." inside a
    citation or caption do not chop a sentence).

    Looks back only a bounded window (the trailing token is at most a few chars):
    slicing the FULL prefix (``norm[:dot_idx]``) and searching it per boundary is
    O(n) each → O(n²) over long text — the same pathological pattern fixed in
    ``treatment._is_boundary``."""
    m = _TRAIL_WORD.search(norm[max(0, dot_idx - 24):dot_idx])
    return m is None or m.group(1) not in _ABBREV


def _sentence_span(norm: str, idx: int, end: int) -> tuple[int, int]:
    """The [start, stop) of the sentence containing the span ``[idx, end)``,
    skipping abbreviation 'boundaries'."""
    start = 0
    for m in _SENT_PUNCT.finditer(norm, 0, idx):
        if _is_sentence_boundary(norm, m.start()):
            start = m.end()
    stop = len(norm)
    for m in _SENT_PUNCT.finditer(norm, end):
        if _is_sentence_boundary(norm, m.start()):
            stop = m.start()
            break
    return start, stop


def _passage_anchors(p: RetrievedPassage) -> list[str]:
    """Normalized strings whose presence in the answer means the answer
    referenced this passage's decision: its case-name caption and any reporter
    cite.

    For caselaw, BOTH live in ``p.citation`` ("State v. Holder, 763 N.W.2d 862")
    — ``p.heading`` is the court+year line ("Supreme Court of Iowa, 2009"), NOT
    the case name (see ``corpus_tools._annotate_caselaw``). So the caption is
    mined from every field, taking whichever holds the ``X v. Y`` / ``In re``
    form; reporter cites are scraped from every field too."""
    anchors: list[str] = []
    for raw in (p.citation or "", p.heading or ""):
        norm = _normalize_for_match(raw)
        name = norm.split(",")[0].strip()
        if (
            name
            and (_CASE_V_RE.search(name) or name.startswith("in re"))
            and len(name) >= 8
        ):
            anchors.append(name)
        for m in _REPORTER_RE.finditer(norm):
            anchors.append(m.group(0))
    # Dedup, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for a in anchors:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _acknowledged_near(norm_content: str, anchor: str, by_citation: str) -> bool:
    """True when the SAME SENTENCE that mentions ``anchor`` also acknowledges the
    negative treatment — a treatment cue word, or the name of the case that did
    the treating. Confining the scan to the anchor's sentence is deliberate: a
    cue about a *different* case a sentence away must NOT mark this reliance as
    acknowledged (the fail-open direction). An answer that says "X was overruled
    by Y" in one breath is handling it correctly and is not flagged."""
    by_norm = _normalize_for_match(by_citation or "")
    by_name = by_norm.split(",")[0].strip()
    idx = norm_content.find(anchor)
    while idx != -1:
        start, stop = _sentence_span(norm_content, idx, idx + len(anchor))
        sentence = norm_content[start:stop]
        if _TREATMENT_CUE_RE.search(sentence):
            return True
        if len(by_name) >= 8 and by_name in sentence:
            return True
        idx = norm_content.find(anchor, idx + 1)
    return False


def _stale_used(content: str, context: RetrievedContext | None) -> list[dict[str, Any]]:
    """Negative-treatment decisions from ``context`` that the drafted ``content``
    actually references. Each entry carries an ``acknowledged`` flag: True when
    the answer notes the treatment (good — distinguishing a dead case), False
    when it leans on the case silently (the dangerous "overruled-as-good-law"
    failure). Deterministic; matches by case-name caption or reporter cite."""
    if context is None:
        return []
    norm = _normalize_for_match(content)
    if not norm:
        return []
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for p in context.passages:
        t = p.treatment
        if t.status != "negative":
            continue
        if p.cluster_id in seen:
            continue
        anchors = _passage_anchors(p)
        hit = next((a for a in anchors if a and a in norm), None)
        if hit is None:
            continue
        seen.add(p.cluster_id)
        out.append(
            {
                "citation": p.citation,
                "heading": p.heading,
                "label": t.label,
                "severity": t.severity,
                "by_citation": t.by_citation,
                "excerpt": t.excerpt,
                "acknowledged": _acknowledged_near(norm, hit, t.by_citation),
            }
        )
    return out


# ---------------------------------------------------------------------------
# PR5: claim-level NLI — caselaw holdings the retrieved opinion CONTRADICTS
# (the misgrounding gap: a real case cited for something it does not support).
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences, skipping abbreviation 'boundaries' (reuses
    the same ``v.``/``App.``-aware logic as the acknowledgment scan)."""
    lowered = text.lower()
    out: list[str] = []
    start = 0
    for m in _SENT_PUNCT.finditer(text):
        if _is_sentence_boundary(lowered, m.start()):
            out.append(text[start : m.start() + 1])
            start = m.end()
    if start < len(text):
        out.append(text[start:])
    return out


def _misgrounded_claims(
    content: str,
    context: RetrievedContext | None,
    checker: "semantic_support.SemanticChecker | None",
) -> list[dict[str, Any]]:
    """Caselaw claims in the answer that the retrieved opinion text CONTRADICTS.

    For each referenced caselaw passage, gather the answer sentences that mention
    it (same anchor match as stale-use) and run one entailment call against the
    passage's retrieved text; a ``contradicted`` verdict is a misgrounding (the
    answer attributes to the case a holding its text does not support). Reuses
    :mod:`semantic_support`. Empty when no checker or no caselaw is referenced."""
    if context is None or checker is None:
        return []
    sentences = [(_normalize_for_match(s), s.strip()) for s in _split_sentences(content)]
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for p in context.passages:
        if p.source_slug != "iowa-caselaw" or p.cluster_id in seen:
            continue
        anchors = _passage_anchors(p)
        if not anchors:
            continue
        claims = [raw for sn, raw in sentences if raw and any(a in sn for a in anchors)]
        source_text = p.excerpt or p.snippet
        if not claims or not source_text:
            continue
        seen.add(p.cluster_id)
        verdicts = checker.check_claims(claims, source_text)
        for claim, v in zip(claims, verdicts):
            if v.verdict == semantic_support.CONTRADICTED:
                out.append(
                    {
                        "citation": p.citation or p.heading,
                        "claim": claim,
                        "evidence": v.evidence,
                    }
                )
    return out


# ---------------------------------------------------------------------------
# Verify (moved from chat._verify_answer) + stale-use + claim-NLI
# ---------------------------------------------------------------------------


def verify_answer(
    content: str,
    *,
    source_slug: str | None = None,
    context: RetrievedContext | None = None,
    claim_checker: "semantic_support.SemanticChecker | None" = None,
    applicability_checker: "applicability.ApplicabilityChecker | None" = None,
    web_currency_checker: "web_currency.WebCurrencyChecker | None" = None,
    premise_problems: list[dict[str, Any]] | None = None,
    question: str | None = None,
) -> dict[str, Any] | None:
    """Check the drafted answer's citations and quotes against the corpus, and
    (PR4) flag any negative-treatment case it relied on silently.

    Works for single-source answers AND mixed answers that legitimately span
    corpora — a construction-defect question is grounded in both the Iowa Code
    (§ 614.1 repose) and the Iowa Court Rules (1.402 relation-back, 32:3.3
    candor). Every citation is resolved against ALL loaded sources and kept if
    it resolves in any one of them; the quote-grounding corpus is the union of
    every resolved rule's text. ``source_slug`` only labels the advisory now —
    it no longer gates whether verification runs, so an unscoped / multi-corpus
    answer (the highest-risk kind) is still checked.

    ``context`` is the retrieved context for the turn (passages carry the PR3
    ``treatment`` flag). When supplied, the report's ``stale_used`` lists the
    negative-treatment cases the answer references; when ``None`` (the legacy
    call shape) the stale check is a no-op and the report is byte-identical to
    the pre-PR4 gate. The retrieved passage text also joins the quote-grounding
    corpus: a caselaw answer quotes the *opinions* it retrieved, and checking
    those quotes only against statutory rule text flagged every accurate
    opinion quote as "not found".

    ``question`` is the user's question for the turn. A quoted span the answer
    *echoes from the question* ("anywhere in North America" in a hypothetical)
    is the user's language, not a source quotation, and is skipped instead of
    being flagged as unverifiable.

    Returns a structured report, or ``None`` when there is nothing to check
    (empty answer or no sources loaded).
    """
    if not content.strip():
        return None
    sources = list(Source.objects.all())
    if not sources:
        return None
    primary = next((s for s in sources if s.slug == source_slug), None)

    # Strip URLs before scanning. Source links like ``.../chapter_32.pdf``
    # contain ``number.word`` runs ("32.pdf") that parse as section-shaped
    # citations and would be flagged as fabricated. The citation text in a
    # markdown link *label* — ``[Iowa Ct. R. 32:1.10](http://...)`` — survives,
    # so real citations are still checked; only the URL target is removed.
    scan_text = _MONEY_RE.sub(" ", _URL_RE.sub(" ", content))

    # Resolve every citation against each source. The reports share identical
    # item order (same regex over the same text), so item ``i`` is the same
    # in-text citation in all of them; we collapse to its best status.
    reports = [validate_citations(scan_text, source=s) for s in sources]
    base_items = reports[0].items

    citation_problems: list[dict[str, str]] = []
    grounding_parts: list[str] = []
    # PR8: the distinct authorities the answer cites (raw cite + resolved
    # section heading), fed to the domain-applicability check below.
    cited_authorities: list[dict[str, str]] = []
    cited_seen: set[str] = set()
    confident_total = 0
    for idx, base in enumerate(base_items):
        items_here = [rep.items[idx] for rep in reports]
        for it in items_here:
            if it.status != "valid":
                continue
            if it.node is not None and it.node.heading:
                grounding_parts.append(it.node.heading)
            if it.version is not None and it.version.body_text:
                grounding_parts.append(it.version.body_text)

        cit = base.citation
        if cit is None or cit.section is None or not _is_real_section(cit):
            continue
        confident_total += 1
        best = max(items_here, key=lambda it: _STATUS_RANK.get(it.status, 0))
        if best.status in ("not_found", "repealed"):
            citation_problems.append({"raw": best.raw.strip(), "status": best.status})
        elif best.status == "valid" and best.node is not None:
            key = (cit.section or best.raw).strip().lower()
            if key not in cited_seen:
                cited_seen.add(key)
                cited_authorities.append(
                    {"raw": best.raw.strip(), "heading": best.node.heading or ""}
                )

    # Quote check. We reuse ``verify_quotes`` purely to extract the quoted spans;
    # its own source-scoped citation pairing is ignored. A quote verifies when it
    # is reconstructable from a few CONTIGUOUS runs of the union grounding text.
    # The grounding corpus is the union of every resolved rule's text AND the
    # retrieved passages — caselaw answers quote the opinions they retrieved,
    # which never resolve through ``validate_citations`` (that is section-shaped
    # statutes/rules only).
    if context is not None:
        for p in context.passages:
            grounding_parts.append(p.excerpt or p.snippet or "")
    grounding = _normalize_for_match(" ".join(grounding_parts))
    question_norm = _normalize_for_match(question or "")

    quote_problems: list[dict[str, str]] = []
    verifiable_quotes = 0
    if grounding:
        for q in verify_quotes(scan_text, source=primary or sources[0]).items:
            qn = _normalize_for_match(q.quote)
            if (
                "\n" in q.quote
                or "…" in q.quote
                or "..." in q.quote
                or "[" in q.quote
                or len(qn.split()) < 4
            ):
                continue
            if question_norm and qn in question_norm:
                # The answer is quoting the USER (restating a hypothetical /
                # the question's own words) — not attributing text to a source.
                continue
            verifiable_quotes += 1
            if qn in grounding:
                continue  # verbatim (normalized) — verified
            sm = SequenceMatcher(None, qn, grounding, autojunk=False)
            covered = sum(b.size for b in sm.get_matching_blocks() if b.size >= 4)
            if covered / max(len(qn), 1) < 0.6:
                quote_problems.append({"quote": q.quote, "status": "not_found"})

    # PR4: stale-use (caselaw). Silent reliance on a negative case is the
    # dangerous failure; an acknowledged mention is correct handling.
    stale_used = _stale_used(content, context)
    stale_silent = [s for s in stale_used if not s["acknowledged"]]

    # PR5: claim-level NLI (caselaw misgrounding). Runs only when a checker is
    # explicitly injected (tests) or ``RAG_CLAIM_NLI`` is on and a key resolves a
    # default checker — otherwise a no-op, so the legacy report is unchanged.
    misgrounded: list[dict[str, Any]] = []
    if context is not None:
        checker = claim_checker
        if checker is None and getattr(settings, "RAG_CLAIM_NLI", False):
            checker = semantic_support.default_checker()
        if checker is not None:
            misgrounded = _misgrounded_claims(content, context, checker)

    # PR8: domain applicability — a citation can be real, accurately quoted,
    # and current, yet drawn from the wrong body of law (UCC § 554.2718
    # applied to a residential lease). Same opt-in posture as PR5: runs when a
    # checker is injected (tests) or ``RAG_APPLICABILITY_CHECK`` is on and a
    # key resolves the default checker; otherwise a no-op. Only
    # ``inapplicable`` verdicts (wrong domain presented as governing) are
    # problems — a candid analogy is fine.
    domain_problems: list[dict[str, Any]] = []
    app_checker = applicability_checker
    if app_checker is None and getattr(settings, "RAG_APPLICABILITY_CHECK", False):
        app_checker = applicability.default_checker()
    if app_checker is not None and question and cited_authorities:
        verdicts = app_checker.check(question, cited_authorities)
        domain_problems = [v for v in verdicts if v.get("fit") == "inapplicable"]

    # PR9: web currency tripwire — for cases the answer relies on that the
    # citator does NOT already flag, read (or create) the durable research
    # note. Same opt-in posture as PR5/PR8; every failure degrades to no note.
    web_currency_problems: list[dict[str, Any]] = []
    wc_checker = web_currency_checker
    if wc_checker is None and getattr(settings, "RAG_WEB_CURRENCY_CHECK", False):
        wc_checker = web_currency.default_checker()
    if wc_checker is not None and context is not None:
        web_currency_problems = _web_currency_problems(
            content, context, wc_checker, topic=question or ""
        )

    premise_problems = premise_problems or []
    return {
        "ok": (
            not citation_problems and not quote_problems
            and not stale_silent and not misgrounded and not premise_problems
            and not domain_problems and not web_currency_problems
        ),
        "source_label": primary.name if primary else "any loaded source",
        "citations_total": confident_total,
        "citations_verified": confident_total - len(citation_problems),
        "quotes_total": verifiable_quotes,
        "quotes_verified": verifiable_quotes - len(quote_problems),
        "citation_problems": citation_problems,
        "quote_problems": quote_problems,
        # Additive (PR4): every negative case the answer touched, each tagged
        # acknowledged/silent. Empty for the legacy ``context=None`` call.
        "stale_used": stale_used,
        # Additive (PR5): caselaw claims the retrieved opinion contradicts.
        "misgrounded": misgrounded,
        # Additive (PR8): cited authorities whose body of law does not govern
        # the fact pattern (real cite, wrong domain).
        "domain_problems": domain_problems,
        # Additive (PR9): relied-on cases with an adverse, corpus-verified web
        # research note the citator doesn't know about yet.
        "web_currency_problems": web_currency_problems,
        # Additive (PR6): the USER's case-holding premises the opinion doesn't
        # support (computed pre-answer by the chat layer; passed through here so
        # the trace + advisory carry one unified report).
        "premise_problems": premise_problems,
    }


def _web_currency_problems(
    content: str,
    context: RetrievedContext,
    checker: "web_currency.WebCurrencyChecker",
    topic: str = "",
) -> list[dict[str, Any]]:
    """Relied-on caselaw with an adverse research note (PR9).

    Reliance = the same anchor test as stale-use (case name / reporter cite
    appears in the answer). Passages the citator already flags are skipped —
    they get the stronger deterministic advisory. At most
    ``RAG_WEB_CURRENCY_BUDGET`` NEW web checks run per answer (a stored note is
    free); un-checked cases simply wait for a future turn's budget."""
    budget = getattr(settings, "RAG_WEB_CURRENCY_BUDGET", 2)
    norm = _normalize_for_match(content)
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for p in context.passages:
        if p.source_slug != "iowa-caselaw" or p.cluster_id in seen:
            continue
        seen.add(p.cluster_id)
        # Skip only NEGATIVE flags (those already draw the strong deterministic
        # stale-use advisory). A CAUTION flag is deliberately still web-checked:
        # phrase-derived labels can be wrong-sided — live failure 2026-07-10,
        # Frohwein carried caution/"overruled-on-other-grounds" while Youngblut
        # overruled it ON the relied-upon point, and deferring to the flag made
        # PR9 silent exactly when it was needed.
        if p.treatment.status == "negative":
            continue
        anchors = _passage_anchors(p)
        if not anchors or not any(a in norm for a in anchors):
            continue
        note = web_currency.get_note(p.cluster_id)
        if not web_currency.note_is_current(note):
            if budget <= 0:
                continue
            budget -= 1
            note = web_currency.check_and_store(
                p.cluster_id, p.heading, p.citation, checker, topic=topic
            )
        if not web_currency.advisory_worthy(note):
            continue
        # Acknowledged-skip (mirrors stale-use): an answer that already tells
        # the reader about the adverse authority handled it correctly — a
        # "may have been overruled" advisory on top is redundant noise. The
        # answer acknowledges when it names the claimed authority (case
        # caption or a reporter cite from claimed_by appears in the text).
        claimed_norm = _normalize_for_match(note.claimed_by)
        name = claimed_norm.split(",")[0].strip()
        acknowledged = (
            bool(name and _CASE_V_RE.search(name) and name in norm)
            or any(c in norm for c in _REPORTER_RE.findall(claimed_norm))
            # Statute-superseded notes: naming the superseding SECTION is the
            # acknowledgment (an answer already citing § 668.14A has engaged
            # the supersession; the advisory would be redundant).
            or any(
                s.lower() in norm
                for s in web_currency._SECTION_RE.findall(note.claimed_by or "")
            )
        )
        if acknowledged:
            continue
        out.append(
            {
                "citation": p.citation or p.heading,
                "kind": note.adverse_kind,
                "by": note.claimed_by,
                "evidence": note.evidence,
                "source_url": note.source_url,
                "review_status": note.review_status,
            }
        )
    return out


def render_advisory(report: dict[str, Any]) -> str:
    """Render a human-readable advisory block for an answer whose verification
    turned up problems. Returns "" when everything checked out, so a clean
    answer is never decorated."""
    if report["ok"]:
        return ""
    label = report.get("source_label") or "the cited corpus"
    lines: list[str] = []
    for p in report["citation_problems"]:
        reason = (
            "could not be found in" if p["status"] == "not_found"
            else "appears to be repealed in"
        )
        lines.append(f"- Citation **{p['raw']}** {reason} {label}.")
    for p in report["quote_problems"]:
        quote = p["quote"]
        snippet = quote if len(quote) <= 100 else quote[:100].rstrip() + "…"
        lines.append(
            f"- The quotation “{snippet}” was not found verbatim in the "
            f"cited source text."
        )
    for s in report.get("stale_used", []):
        if s["acknowledged"]:
            continue  # the answer already flags the treatment — not a problem
        who = s["by_citation"] or "a later Iowa decision"
        label_txt = s["label"] or "negatively treated"
        cite = s["citation"] or s["heading"] or "a cited case"
        ev = s["excerpt"]
        ev_txt = f" (“{ev[:140].rstrip()}…”)" if len(ev) > 140 else (
            f" (“{ev}”)" if ev else ""
        )
        lines.append(
            f"- **{cite}** was {label_txt} by {who} and should not be relied on "
            f"as good law{ev_txt}. Confirm current authority before citing it."
        )
    for m in report.get("misgrounded", []):
        cite = m.get("citation") or "a cited case"
        claim = m["claim"]
        claim_txt = claim if len(claim) <= 160 else claim[:160].rstrip() + "…"
        lines.append(
            f"- The characterization of **{cite}** (“{claim_txt}”) is not "
            f"supported by — and may conflict with — the retrieved opinion text. "
            f"Re-read the case before relying on this point."
        )
    for d in report.get("domain_problems", []):
        heading = d.get("heading") or ""
        heading_txt = f" (“{heading}”)" if heading else ""
        reason = (d.get("reason") or "").strip().rstrip(".")
        reason_txt = (
            f": {reason}" if reason
            else " — its chapter addresses a different subject matter"
        )
        lines.append(
            f"- **{d['raw']}**{heading_txt} may not govern this fact "
            f"pattern{reason_txt}. Check whether an on-domain provision "
            f"controls before relying on it."
        )
    for w in report.get("web_currency_problems", []):
        kind_txt = {
            "overruled": "overruled",
            "superseded_by_statute": "superseded by statute",
            "caution": "qualified",
        }.get(w.get("kind", ""), "negatively treated")
        by = w.get("by") or "a later authority"
        ev = (w.get("evidence") or "").strip()
        ev_txt = (f" (“{ev[:140].rstrip()}…”)" if len(ev) > 140
                  else (f" (“{ev}”)" if ev else ""))
        reviewed = w.get("review_status") == "approved"
        confidence_txt = (
            "" if reviewed
            else " This is an automated research note pending attorney review."
        )
        lines.append(
            f"- Secondary sources indicate **{w['citation']}** may have been "
            f"{kind_txt} by {by}{ev_txt}.{confidence_txt} Verify currency "
            f"before relying on it."
        )
    for pp in report.get("premise_problems", []):
        # Currency axis (PR7): the premise rests on a case that is no longer good
        # law — the load-bearing correction (it stands even when the reading is
        # faithful). Rendered first / instead of the fidelity note.
        if pp.get("currency") in ("negative", "caution"):
            who = pp.get("treating_case") or "a later Iowa decision"
            verb = (pp.get("treatment_label") or "negatively treated").replace("-", " ")
            ev = (pp.get("treatment_evidence") or "").strip()
            ev_txt = (f" (“{ev[:140].rstrip()}…”)" if len(ev) > 140
                      else (f" (“{ev}”)" if ev else ""))
            status_txt = ("is no longer good law" if pp["currency"] == "negative"
                          else "was qualified on another point")
            lines.append(
                f"- Your question relies on **{pp['case']}**, which {status_txt} — "
                f"it was {verb} by {who}{ev_txt}. Even if your reading of it is "
                f"correct, it is no longer controlling; check current authority "
                f"before relying on it."
            )
            continue
        # Fidelity axis — only contradicted/partial render a problem (a currency-only
        # finding with verdict "supported"/"unchecked" must not produce a spurious
        # "partially supported" line).
        if pp.get("verdict") not in ("contradicted", "partial"):
            continue
        how = (
            "is contradicted by" if pp["verdict"] == "contradicted"
            else "is only partially supported by"
        )
        ev = (pp.get("evidence") or "").strip()
        ev_txt = (f" (opinion: “{ev[:140].rstrip()}…”)" if len(ev) > 140
                  else (f" (opinion: “{ev}”)" if ev else ""))
        lines.append(
            f"- Your premise about **{pp['case']}** {how} the retrieved "
            f"opinion{ev_txt}. Confirm what the case actually holds before "
            f"relying on it."
        )
    if not lines:
        return ""
    return (
        "\n\n---\n\n"
        "**⚠️ Automated verification.** The following could not be "
        "confirmed against the source text and should be checked before you rely "
        "on them:\n\n" + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# PR4: abstain — no good-law authority retrieved — and the block policy
# ---------------------------------------------------------------------------


def should_abstain(context: RetrievedContext | None) -> tuple[bool, str]:
    """Whether the retrieved context offers no good-law authority to answer on.

    Deterministic and deliberately conservative (this is advisory by default):
    fires only when (a) nothing was retrieved, or (b) every retrieved passage is
    dead law — flagged ``negative`` (overruled/superseded caselaw) or a
    **repealed** section (PR8g: ``is_repealed`` rides on every passage; treatment
    is caselaw-only, so without this read a repealed § would be presumed good).
    ``unknown`` treatment on a non-repealed passage — the default for unflagged
    cases and live statutes — is treated as presumptively good: phrase-scan
    recall is partial, so the absence of a flag is NOT evidence of staleness.
    Returns ``(abstain, reason)``."""
    if context is None or not context.passages:
        return True, "no on-point Iowa authority was retrieved"
    if all(
        p.treatment.status == "negative" or p.is_repealed
        for p in context.passages
    ):
        return (
            True,
            "every Iowa authority retrieved on this question has been negatively "
            "treated (overruled / superseded) or repealed",
        )
    return False, ""


def _abstain_blocking_enabled() -> bool:
    return bool(getattr(settings, "RAG_ABSTAIN_BLOCKING", False))


def _block_severity() -> int:
    return int(getattr(settings, "RAG_STALE_BLOCK_SEVERITY", STALE_BLOCK_SEVERITY))


def abstain_decision(
    report: dict[str, Any] | None,
    context: RetrievedContext | None,
    *,
    searched: bool = True,
) -> tuple[bool, str]:
    """Decide whether the chat finalizer should SUPPRESS the drafted answer and
    replace it with a notice. Only ever blocks when ``RAG_ABSTAIN_BLOCKING`` is
    on — default off, so default behavior is fully preserved (advisory only).

    Two block triggers, in order:

    1. **Silent stale use** — the answer relied on a negative case at or above
       ``RAG_STALE_BLOCK_SEVERITY`` *without* acknowledging its treatment. (An
       answer that correctly flags the overruling is never blocked.)
    2. **No good law** — a search ran for this turn and :func:`should_abstain`
       says every retrieved authority is negative (or nothing was retrieved).
       Guarded by ``searched`` so an answer that used ``lookup_citation`` / a
       pinned document instead of search is not blocked for an empty search set.
       Note: this fires even when the answer *correctly* explained that every
       case is overruled — by design, an all-negative context means there is no
       good-law authority to stand on, so the policy abstains. In practice such
       answers usually also cite a statute / unflagged case, which makes the
       context not all-negative and leaves this branch dormant.

    Returns ``(block, replacement_message)``; ``replacement_message`` is the
    standalone text to show in place of the answer when ``block`` is True.
    """
    if not _abstain_blocking_enabled():
        return False, ""

    threshold = _block_severity()
    invalid = [
        s
        for s in (report or {}).get("stale_used", [])
        if not s["acknowledged"] and s["severity"] >= threshold
    ]
    if invalid:
        return True, _withheld_message(invalid)

    if searched:
        abstain, reason = should_abstain(context)
        if abstain:
            return True, _abstain_message(reason)

    return False, ""


def _withheld_message(invalid: list[dict[str, Any]]) -> str:
    cases = []
    for s in invalid:
        who = s["by_citation"] or "a later Iowa decision"
        cite = s["citation"] or s["heading"] or "a cited case"
        cases.append(f"- **{cite}** ({s['label'] or 'negatively treated'} by {who})")
    return (
        "⛔ **Answer withheld.** A draft answer relied on Iowa authority that "
        "has since been invalidated, so it was not shown:\n\n"
        + "\n".join(cases)
        + "\n\nRelying on overruled precedent as good law is exactly the error "
        "this assistant is built to prevent. Please consult current authority or "
        "refine the question; you can ask for the procedural history of the case "
        "above if you need to understand how it was treated."
    )


def _abstain_message(reason: str) -> str:
    return (
        "I could not locate good-law Iowa authority on this question "
        f"({reason}). Rather than stretch an off-point or overruled source, I am "
        "not providing an answer. Please refine the question or consult a current "
        "primary source directly."
    )
