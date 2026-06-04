"""Citation-centric document verification (Verify Document feature).

Where ``apps.api.chat._verify_answer`` is *answer*-centric — it scans a drafted
answer and returns aggregate counts plus two problem lists — this service is
*citation*-centric: it walks an uploaded document and returns one
``CitationFinding`` per citation, each rolled up to a single traffic-light
``status`` (green / yellow / red). That shape is what the "verify document"
checklist UI renders, one row per cite.

Two things are checked per citation, deterministically (an optional LLM layer
for paraphrased claims is wired in by ``semantic_support`` — see Phase 1.3):

  1. **Format + existence** — does the citation parse, and does it resolve to a
     live provision in *any* loaded source? (Multi-source, like the chat gate.)
  2. **Language** — does each quoted passage attributed to the citation (by
     proximity) actually appear in that provision's text, or is it fabricated?

The heavy lifting is reused from ``lookups`` (``validate_citations``,
``_match_quote_against_body``) and mirrors the proven multi-source rollup in the
chat verification gate. Pure-read; no writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.citations.parser import _SIGIL_TOKEN_RE
from apps.corpus.models import Source
from apps.corpus.services.citation_format import (
    canonical_citation,
    near_match,
    normalize_citation_hyphens,
    reporter_letters,
    source_hint,
    written_citation,
)
from apps.corpus.services.lookups import (
    QUOTE_EXACT,
    QUOTE_FUZZY,
    QUOTE_NOT_FOUND,
    VALIDATION_NOT_FOUND,
    VALIDATION_PARSE_ERROR,
    VALIDATION_REPEALED,
    VALIDATION_VALID,
    _QUOTE_CITATION_WINDOW,
    _QUOTE_FUZZY_THRESHOLD,
    _QUOTE_MIN_LEN,
    _QUOTE_RE,
    _match_quote_against_body,
    validate_citations,
)
from apps.corpus.services.provision_slice import slice_provision
from apps.corpus.services.semantic_support import (
    NO_CLAIM,
    SemanticChecker,
    default_checker,
)

# Sentinel so callers can pass ``semantic=None`` to explicitly disable the
# paraphrase layer, distinct from "not passed → use the configured default".
_USE_DEFAULT_CHECKER = object()

# An unquoted assertion needs at least this many words to be worth a semantic
# check — shorter spans are bare references ("see § 714.16"), not claims.
_MIN_CLAIM_WORDS = 6

# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------

GREEN = "green"
YELLOW = "yellow"
RED = "red"

# Precedence when one citation resolves against several sources: valid in ANY
# loaded source wins. Identical to the chat gate's ``_STATUS_RANK``.
_STATUS_RANK = {
    VALIDATION_VALID: 3,
    VALIDATION_REPEALED: 1,
    VALIDATION_NOT_FOUND: 0,
    VALIDATION_PARSE_ERROR: 0,
}

# Strip URLs and dollar amounts before scanning — both produce ``number.word``
# / ``number.number`` runs ("chapter_32.pdf", "$7.25") that parse as
# section-shaped citations and would be flagged as fabricated. Same guard the
# chat gate uses.
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")


def _blank(m: re.Match) -> str:
    """Same-length blank so substitutions don't shift downstream offsets."""
    return " " * (m.end() - m.start())


def _is_real_section(citation) -> bool:
    """True only when the part after the chapter is numeric — a genuine section
    ("714.16", "32:1.10", "708.2A") rather than a subsection list marker
    ("1.d", "2.a") that parses section-shaped but is not a standalone cite.
    Mirrors ``apps.api.chat._is_real_section``."""
    section = citation.section or ""
    chapter = citation.chapter or ""
    rest = section[len(chapter) + 1:] if section.startswith(chapter) else section
    return bool(rest) and rest[0].isdigit()


# A short decimal — single/double-digit chapter, a "." separator, and a
# single-digit tail ("4.1", "2.0", "9.5"). This shape is section-valid but
# collides with everyday numbers: engine sizes ("a 4.1 motor"), versions
# ("v2.0"), ratios, and outline markers. Structurally unambiguous cites are
# NOT matched: 3+ digit chapters ("714.16"), 2+ digit tails ("1.305", "2.19"),
# the colon court-rule form ("32:1.10"), and anything carrying a subdivision.
_AMBIGUOUS_BARE_RE = re.compile(r"^\d{1,2}\.\d$")


def _is_ambiguous_bare_decimal(citation) -> bool:
    """True for a short ``N.M`` decimal that parses section-shaped but reads as
    an ordinary number in prose. Used to demand a citation cue before grading
    such a token, so "a top of the line 4.1 motor" isn't flagged as a cite to
    Iowa Code § 4.1."""
    if citation is None or getattr(citation, "subdivisions", ()):
        return False
    return bool(_AMBIGUOUS_BARE_RE.match(citation.section or ""))


def _has_left_cue(text: str, start: int) -> bool:
    """Whether a citation cue (§, "section", "chapter", "rule", "Iowa Code",
    "I.C.", or a reporter abbreviation) sits immediately before ``start``.

    ``_ITER_RE`` only folds §/section/chapter/I.C. into the matched token, so a
    "rule 4.1" or "Iowa R. Civ. P. 4.1" comes back as a bare "4.1" with no
    attached sigil. Scanning a short left window with the parser's own sigil
    vocabulary recovers those — keeping a genuinely-cited short decimal while
    still dropping one that stands alone in prose."""
    left = text[max(0, start - 40):start]
    return any(m.end() == len(left) for m in _SIGIL_TOKEN_RE.finditer(left))


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass
class LanguageCheck:
    """One piece of language attributed to a citation, plus how it compares to
    the real source text.

    ``kind`` is "quote" for text in quotation marks (checked verbatim) or
    "paraphrase" for an unquoted claim near the cite (checked by the semantic
    layer). ``verdict`` is the per-claim outcome; ``source_excerpt`` is the
    closest matching passage from the provision so the UI can show claim-vs-
    source side by side."""

    claim_text: str
    kind: str  # "quote" | "paraphrase"
    verdict: str  # exact | fuzzy | not_found | supported | partial | contradicted
    match_score: float
    source_excerpt: str
    span: tuple[int, int]


@dataclass
class FormResult:
    """Step 1 — is the citation written correctly?

    ``status``: "ok" (proper form), "corrected" (resolves but mis-styled; a
    correction is offered), or "unresolvable" (no exact match; ``canonical`` may
    carry a "did you mean?" near-match). ``written`` is what the author typed;
    ``canonical`` is the proper form."""

    status: str
    written: str
    canonical: str | None
    note: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "written": self.written,
            "canonical": self.canonical,
            "note": self.note,
        }


@dataclass
class CitationFinding:
    """One citation from the document with its rolled-up traffic-light status."""

    raw: str
    span: tuple[int, int]
    status: str  # green | yellow | red
    format_ok: bool
    resolution: str  # valid | repealed | not_found | parse_error
    source_label: str | None
    target_path: str | None
    language_checks: list[LanguageCheck]
    detail: str
    form: FormResult | None = None
    # Internal: the provision text quotes are matched against. Never serialized.
    grounding: str = field(default="", repr=False)

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "span": list(self.span),
            "status": self.status,
            "format_ok": self.format_ok,
            "resolution": self.resolution,
            "source_label": self.source_label,
            "target_path": self.target_path,
            "detail": self.detail,
            "form": self.form.to_dict() if self.form else None,
            "language_checks": [
                {
                    "claim_text": lc.claim_text,
                    "kind": lc.kind,
                    "verdict": lc.verdict,
                    "match_score": round(lc.match_score, 3),
                    "source_excerpt": lc.source_excerpt,
                    "span": list(lc.span),
                }
                for lc in self.language_checks
            ],
        }


@dataclass
class DocumentReport:
    findings: list[CitationFinding]

    @property
    def total(self) -> int:
        return len(self.findings)

    def count(self, status: str) -> int:
        return sum(1 for f in self.findings if f.status == status)

    def summary(self) -> dict:
        return {
            "total": self.total,
            "green": self.count(GREEN),
            "yellow": self.count(YELLOW),
            "red": self.count(RED),
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def verify_document(
    text: str,
    *,
    sources: list[Source] | None = None,
    include_pending: bool = False,
    semantic: SemanticChecker | None = _USE_DEFAULT_CHECKER,  # type: ignore[assignment]
) -> DocumentReport:
    """Verify every citation in ``text`` against all loaded sources.

    Verbatim quotes are graded deterministically against the cited provision's
    text. Unquoted assertions near a citation are graded by the ``semantic``
    checker (defaults to the configured Anthropic checker; pass ``None`` to
    disable and grade verbatim-only).
    """
    if semantic is _USE_DEFAULT_CHECKER:
        semantic = default_checker()
    findings, scan_text = _build_findings(text, sources, include_pending)
    for f in findings:
        _finalize(f, scan_text, semantic)
    return DocumentReport(findings=findings)


def iter_verify_document(
    text: str,
    *,
    sources: list[Source] | None = None,
    include_pending: bool = False,
    semantic: SemanticChecker | None = _USE_DEFAULT_CHECKER,  # type: ignore[assignment]
):
    """Streaming variant of :func:`verify_document` for the per-citation
    progress UI. Yields, in order:

        ("start",   {"char_count": int, "citations_total": int})
        ("citation", CitationFinding)   # one per cite, fully finalized
        ("summary", {"total", "green", "yellow", "red"})

    The deterministic work (validation + quote matching) is done up front in
    ``start``; the per-citation semantic check then runs as each row streams,
    so the slow LLM calls fill chips in live rather than blocking the whole
    response.
    """
    if semantic is _USE_DEFAULT_CHECKER:
        semantic = default_checker()
    findings, scan_text = _build_findings(text, sources, include_pending)
    yield ("start", {"char_count": len(text or ""), "citations_total": len(findings)})
    for f in findings:
        _finalize(f, scan_text, semantic)
        yield ("citation", f)
    yield ("summary", DocumentReport(findings=findings).summary())


def _build_findings(
    text: str, sources: list[Source] | None, include_pending: bool
) -> tuple[list[CitationFinding], str]:
    """Run the fast, deterministic pass: scrub, resolve every citation across
    all sources, build one finding per confident citation, and attach verbatim
    quote checks. Returns the findings (not yet rolled up) and the scrubbed
    text (offsets aligned to the original) for the semantic pass."""
    if sources is None:
        sources = list(Source.objects.all())
    if not text or not text.strip() or not sources:
        return [], ""

    # Rescue reporter-anchored hyphen citations ("Ia. Code 321-218" →
    # "...321.218") so they aren't silently dropped. Length-preserving, so all
    # spans below still line up with the original document.
    text = normalize_citation_hyphens(text)

    # Length-preserving scrub: replace each match with the same number of
    # spaces so every span stays aligned to the *original* document. This is
    # used ONLY for citation *parsing* — it stops a URL ("chapter_32.pdf") or a
    # dollar amount ("$7.25") from being misread as a citation ("32.pdf",
    # "7.25"). Quote and claim extraction below use the ORIGINAL text, so the
    # LLM still sees monetary amounts (e.g. a claim of "$50" vs a statute's
    # "$500" must be checkable) — the offsets line up because the scrub is
    # length-preserving.
    scan_text = _MONEY_RE.sub(_blank, _URL_RE.sub(_blank, text))

    # Resolve every citation against each source. All reports share item order
    # (same regex over the same text), so item ``i`` is the same in-text
    # citation in each — we collapse to its best status across sources.
    reports = [
        validate_citations(scan_text, source=s, include_pending=include_pending)
        for s in sources
    ]
    base_items = reports[0].items

    findings: list[CitationFinding] = []
    for idx, base in enumerate(base_items):
        cit = base.citation
        is_section = (
            cit is not None and cit.section is not None and _is_real_section(cit)
        )
        has_sigil = bool(_SIGIL_TOKEN_RE.match(base.raw))
        # Confidence filter: only treat a match as a citation worth grading when
        # it is section-shaped OR carries an explicit sigil (§, "section",
        # "chapter", "Iowa Ct. R.", ...). Drops bare numbers like the "90" in
        # "within 90 days". A sigil-bearing-but-unparseable match still gets
        # through here so a genuinely malformed citation is graded red.
        if not is_section and not has_sigil:
            continue
        # A sigil-less short decimal ("4.1 motor", "a 2.0 engine") is
        # section-shaped but is far more often a number in prose than a cite to
        # Iowa Code § 4.1 — which a brief writes as "§ 4.1" / "section 4.1" /
        # "rule 4.1". Require a nearby cue before grading it; structurally
        # unambiguous cites (714.16, 1.305, 32:1.10, subdivided) are unaffected.
        if (
            not has_sigil
            and _is_ambiguous_bare_decimal(cit)
            and not _has_left_cue(text, base.span[0])
        ):
            continue

        items_here = [rep.items[idx] for rep in reports]
        best = max(items_here, key=lambda it: _STATUS_RANK.get(it.status, 0))

        # Disambiguate a citation that resolves in more than one corpus by the
        # reporter the author actually wrote: "IRCrP 2.19" should resolve to the
        # Criminal Procedure rule, not the coincidental Iowa Code § 2.19. Only
        # overrides when the hinted source also resolves the cite.
        hint = source_hint(text, base.span)
        if hint is not None:
            hinted = next(
                (
                    it
                    for it in items_here
                    if it.node is not None
                    and it.node.source.slug == hint
                    and it.status == VALIDATION_VALID
                ),
                None,
            )
            if hinted is not None:
                best = hinted

        source_label: str | None = None
        target_path: str | None = None
        grounding = ""
        if best.status == VALIDATION_VALID and best.node is not None:
            source_label = best.node.source.name
            target_path = best.node.path
            # Chapter-only citations have no body of their own; matching a
            # quote against just a chapter heading would false-flag a quote
            # pulled from one of its sections, so they get no quote checks.
            if best.version is not None and best.version.body_text:
                body = best.version.body_text
                # Narrow grounding to the cited subsection when the citation
                # carries subdivisions ("§ 714H.5(4)" → just subsection 4),
                # so a claim about (4) can't be "supported" by text from (2).
                # Falls back to the full section body when the slice is
                # ambiguous, so this never grounds against less than today.
                subs = getattr(cit, "subdivisions", ()) if cit is not None else ()
                if subs:
                    sliced = slice_provision(body, subs)
                    if sliced:
                        body = sliced
                parts = []
                if best.node.heading:
                    parts.append(best.node.heading)
                parts.append(body)
                grounding = "\n".join(parts)

        findings.append(
            CitationFinding(
                raw=base.raw.strip(),
                span=base.span,
                status="",  # filled by rollup
                format_ok=best.status != VALIDATION_PARSE_ERROR,
                resolution=best.status,
                source_label=source_label,
                target_path=target_path,
                language_checks=[],
                detail="",
                form=_check_form(scan_text, base.span, cit, best, sources),
                grounding=grounding,
            )
        )

    # Quotes and claim sentences come from the ORIGINAL text (with $ amounts
    # intact); citation spans align because the scrub is length-preserving.
    _attach_quote_checks(text, findings)
    return findings, text


# A bare subdivision token directly after the citation's closing paren, e.g. the
# "b" in "6.101(1)b" — the parser only captures parenthesized subdivisions, so
# this trailing one is dropped. ``(?![A-Za-z0-9])`` ensures it's a lone token
# (so we don't grab the "t" of "6.101(1)the").
_TRAILING_SUB = re.compile(r"([A-Za-z0-9])(?![A-Za-z0-9])")


_HYPHEN_SUB = re.compile(r"-([A-Za-z0-9])(?![A-Za-z0-9])")


def _recover_trailing_subdivisions(
    text: str, span: tuple[int, int], allow_hyphen: bool = False
) -> tuple[str, ...]:
    """Subdivisions the parser dropped because they weren't parenthesized.

    Two forms: a bare token after a closing paren ("6.101(1)b" → ("b",)), and —
    for court rules, where it's a known convention — a CHAIN of hyphenated
    subsections ("2.33-2-b" → ("2", "b")). The hyphen form is gated to rules so
    an Iowa Code range like "sections 1-5" isn't misread."""
    start, end = span
    if text[start:end].rstrip().endswith(")"):
        m = _TRAILING_SUB.match(text, end)
        return (m.group(1),) if m else ()
    if allow_hyphen:
        out: list[str] = []
        pos = end
        while (m := _HYPHEN_SUB.match(text, pos)) is not None:
            out.append(m.group(1))
            pos = m.end()
        return tuple(out)
    return ()


def _check_form(text, span, citation, best, sources) -> FormResult:
    """Step 1 form check for one citation: render the canonical form and decide
    whether what the author wrote is proper, mis-styled (with a correction), or
    unresolvable (with a typo near-match where possible)."""
    written = written_citation(text, span)

    if best.node is not None:
        # Resolves (valid or repealed) — render the proper form and compare.
        subdivisions = getattr(citation, "subdivisions", ())
        # Recover trailing subdivisions the parser dropped ("6.101(1)b", or the
        # rules' hyphen chain "2.33-2-b" → "(2)(b)").
        trailing = _recover_trailing_subdivisions(
            text, span, allow_hyphen=best.node.source.slug == "iowa-court-rules"
        )
        if trailing:
            subdivisions = (*subdivisions, *trailing)
        canonical = canonical_citation(best.node, subdivisions)
        if trailing:
            return FormResult(
                "corrected", written, canonical,
                "Each subdivision should be parenthesized, e.g. (1)(b).",
            )
        user_letters = reporter_letters(written, best.node.path)
        canon_letters = reporter_letters(canonical, best.node.path)
        if user_letters and user_letters != canon_letters:
            return FormResult("corrected", written, canonical, "Nonstandard citation form.")
        return FormResult("ok", written, canonical, "")

    # Doesn't resolve — offer a typo near-match if we can find one.
    if citation is not None and citation.section is not None:
        for s in sources:
            nm = near_match(citation, s)
            if nm is not None:
                node, subs = nm
                canonical = canonical_citation(node, subs)
                return FormResult(
                    "unresolvable", written, canonical,
                    "No exact match — did you mean this?",
                )
    return FormResult("unresolvable", written, None, "No matching provision found.")


def _finalize(
    f: CitationFinding, scan_text: str, semantic: SemanticChecker | None
) -> None:
    """Run the per-citation semantic check (paraphrased cites only) and roll the
    finding up to its traffic-light status. Mutates ``f`` in place."""
    # Only paraphrase-grade valid cites that don't already carry a verbatim
    # quote — a quoted cite is handled by the deterministic path.
    if semantic is not None and f.grounding and not f.language_checks:
        claim = _claim_sentence(scan_text, f.span)
        if len(claim.split()) >= _MIN_CLAIM_WORDS:
            verdict = semantic.check_claims([claim], f.grounding)[0]
            if verdict.verdict != NO_CLAIM:  # neutral — a bare reference
                f.language_checks.append(
                    LanguageCheck(
                        claim_text=claim,
                        kind="paraphrase",
                        verdict=verdict.verdict,
                        match_score=0.0,
                        source_excerpt=verdict.evidence,
                        span=f.span,
                    )
                )
    f.status, f.detail = _rollup(f)


# ---------------------------------------------------------------------------
# Language checks (verbatim quotes)
# ---------------------------------------------------------------------------


def _attach_quote_checks(text: str, findings: list[CitationFinding]) -> None:
    """Pair each quoted passage with its nearest valid citation and record how
    it compares to that provision's text. Mutates ``findings`` in place."""
    gradable = [f for f in findings if f.grounding]
    if not gradable:
        return

    for m in _QUOTE_RE.finditer(text):
        grp = 1 if m.group(1) is not None else 2
        quote = m.group(grp).strip()
        if len(quote) < _QUOTE_MIN_LEN or _skip_quote(quote):
            continue
        span = (m.start(grp), m.end(grp))
        finding = _nearest_finding(gradable, span)
        if finding is None:
            continue  # not within a citation's window — not "language around" a cite
        status, score, passage = _match_quote_against_body(
            quote, finding.grounding, _QUOTE_FUZZY_THRESHOLD
        )
        verdict = {
            QUOTE_EXACT: "exact",
            QUOTE_FUZZY: "fuzzy",
            QUOTE_NOT_FOUND: "not_found",
        }[status]
        finding.language_checks.append(
            LanguageCheck(
                claim_text=quote,
                kind="quote",
                verdict=verdict,
                match_score=score,
                source_excerpt=passage,
                span=span,
            )
        )


# A sentence boundary is terminal punctuation followed by whitespace and a
# capitalized next word. The negative lookbehinds keep us from breaking on the
# dots inside reporter abbreviations ("Iowa R. Civ. P.", "App.", "Ct.") — which
# a naive split on every "." would treat as sentence ends, chopping a cite's
# sentence into a fragment.
#
# We do NOT guard against decimals with a digit-lookbehind: the required
# whitespace after the punctuation already excludes a real decimal point
# ("1.305" has no space after the dot), and a digit-lookbehind would WRONGLY
# refuse to split a sentence that *ends* in a citation number ("...rule 1.305.
# The Defendant...") — collapsing several sentences (and their distinct
# citations) into one blob.
_SENTENCE_END = re.compile(
    r"(?<![A-Z])"  # not a single-letter abbreviation (R. P. I. C.)
    r"(?<!Civ)(?<!Crim)(?<!App)(?<!Evid)(?<!Stat)(?<!Ann)"
    r"(?<!Rev)(?<!Sec)(?<!Art)(?<!Ct)(?<!Ch)(?<!No)"
    # Lowercase-ending abbreviations the single-letter/word guards miss — most
    # importantly "Ia." (Iowa), which precedes a reporter ("Ia. R. Civ. P.")
    # and was being mis-read as a sentence end, slicing a multi-citation
    # sentence in half.
    r"(?<!Ia)(?<!Va)(?<!Ga)(?<!La)(?<!Pa)(?<!Co)(?<!Inc)(?<!Corp)(?<!Ltd)"
    r"(?<!Mr)(?<!Mrs)(?<!Ms)(?<!Dr)(?<!Jr)(?<!Sr)(?<!St)(?<!vs)"
    # A list/heading separator after terminal punctuation ("...goods. - IV.
    # Breach of...") starts a new unit. Consuming the leading dash/bullet here
    # breaks the heading off, so a citation living inside it ("...(§ 554.2314)")
    # gets its OWN claim instead of inheriting the previous sentence's — which
    # otherwise reads as a contradiction.
    r"[.!?]+\s+(?:[-–—•*]\s+)?(?=[\"“'(]?[A-Z])"
)


def _claim_sentence(text: str, span: tuple[int, int]) -> str:
    """The sentence containing the citation at ``span`` — the unit we ask the
    semantic checker to judge."""
    s = span[0]
    # Sentence starts: index 0, then the char after each boundary match.
    starts = [0]
    for m in _SENTENCE_END.finditer(text):
        starts.append(m.end())
    starts.append(len(text))
    for i in range(len(starts) - 1):
        if starts[i] <= s < starts[i + 1]:
            return text[starts[i] : starts[i + 1]].strip()
    return text.strip()


def _skip_quote(quote: str) -> bool:
    """Fragments that aren't substantive verbatim claims worth grading. Same
    filter the chat gate applies: multi-line captures (markdown artifacts),
    author-signalled non-verbatim (ellipsis / [brackets]), and <4-word spans
    (terms of art / headings, not quotations)."""
    return (
        "\n" in quote
        or "…" in quote
        or "..." in quote
        or "[" in quote
        or len(quote.split()) < 4
    )


def _nearest_finding(
    findings: list[CitationFinding], qspan: tuple[int, int]
) -> CitationFinding | None:
    """Closest finding whose span is within ``_QUOTE_CITATION_WINDOW`` of the
    quote, or None if no citation is near enough to own the quote."""
    qs, qe = qspan
    best: CitationFinding | None = None
    best_dist: int | None = None
    for f in findings:
        cs, ce = f.span
        if ce < qs:
            dist = qs - ce
        elif cs > qe:
            dist = cs - qe
        else:
            dist = 0
        if dist <= _QUOTE_CITATION_WINDOW and (best_dist is None or dist < best_dist):
            best, best_dist = f, dist
    return best


# ---------------------------------------------------------------------------
# Rollup
# ---------------------------------------------------------------------------


def _rollup(f: CitationFinding) -> tuple[str, str]:
    """Collapse a finding's resolution + language checks to one traffic-light
    status (worst-wins) plus a human-readable reason."""
    if f.resolution == VALIDATION_PARSE_ERROR:
        return RED, "Citation format not recognized."
    if f.resolution == VALIDATION_NOT_FOUND:
        return RED, "Citation could not be found in any loaded source."
    if f.resolution == VALIDATION_REPEALED:
        return YELLOW, "Citation resolves but the provision appears repealed or superseded."

    # resolution == valid: status is driven by the attributed language.
    verdicts = [lc.verdict for lc in f.language_checks]
    if any(v in ("not_found", "contradicted") for v in verdicts):
        return RED, "Cited language was not found in or is contradicted by the source."
    if any(v in ("fuzzy", "partial") for v in verdicts):
        return YELLOW, "Cited language only partially matches the source."
    if any(v == "unverified" for v in verdicts):
        return YELLOW, "A claim about this provision could not be automatically verified."
    if verdicts:
        return GREEN, "Citation valid and cited language is supported by the source."
    return GREEN, "Citation format valid and resolves to a current provision."
