"""Citation *form* helpers for Verify Document — Step 1 of the two-step check.

Where the rest of the verifier asks "does the source say what the document
claims?", this asks "is the citation written correctly, and if not, what is the
right form?". It is fully deterministic — no LLM — because the lenient parser
already normalizes messy input to a canonical ``Citation`` + resolved ``Node``,
and the corpus knows the canonical abbreviation/path. So the pattern is:

    lenient-parse → resolve → render the canonical form → diff vs what was
    written → suggest the correction.

Scope is "correct Iowa citation form" (reporter/code abbreviation, § symbol,
subdivision nesting) plus a typo near-match — NOT full Bluebook style (year
parentheticals, signals, short forms), which is a separate, fuzzier phase.
"""

from __future__ import annotations

import re

from apps.citations.parser import Citation, _SIGIL_TOKEN_RE
from apps.corpus.models import Node, Source

# Iowa court-rule reporters are keyed by chapter (ch.1 = Civil Procedure,
# ch.6 = Appellate Procedure, ...). The chapter Node's heading names the
# reporter; map it to the standard abbreviation.
_REPORTER_BY_HEADING = (
    ("civil procedure", "Iowa R. Civ. P."),
    ("criminal procedure", "Iowa R. Crim. P."),
    ("appellate procedure", "Iowa R. App. P."),
    ("professional conduct", "Iowa R. Prof'l Conduct"),
    ("evidence", "Iowa R. Evid."),
)


def _subs(subdivisions: tuple[str, ...]) -> str:
    return "".join(f"({s})" for s in subdivisions)


def _reporter_for_chapter(source: Source, chapter_key: str) -> str | None:
    """Standard reporter abbreviation for a court-rule chapter, via the chapter
    Node's heading. None if we can't determine it (caller falls back)."""
    chap = Node.objects.filter(source=source, path=chapter_key).first()
    if chap and chap.heading:
        h = chap.heading.lower()
        for needle, abbrev in _REPORTER_BY_HEADING:
            if needle in h:
                return abbrev
    return None


def canonical_citation(node: Node, subdivisions: tuple[str, ...]) -> str:
    """The properly-formatted citation for a resolved node.

    Iowa Code → ``Iowa Code § 714.16(2)(a)`` / ``Iowa Code ch. 714``.
    Court rules → ``Iowa R. Civ. P. 1.305(1)`` (reporter from the chapter).
    """
    subs = _subs(subdivisions)
    if node.source.slug == "iowa-code":
        if node.parent_id is None:  # chapter node — no section number
            return f"Iowa Code ch. {node.path}"
        return f"Iowa Code § {node.path}{subs}"

    # Court rules: derive the reporter from the chapter (path before . or :).
    chapter_key = re.split(r"[.:]", node.path)[0]
    reporter = _reporter_for_chapter(node.source, chapter_key)
    if reporter:
        return f"{reporter} {node.path}{subs}"
    return f"{node.source.citation_abbreviation} {node.path}{subs}".strip()


# Words that are interchangeable / optional in a citation and must NOT count as
# reporter differences (so "Iowa Code section 537A.1" is not flagged against
# "Iowa Code § 537A.1").
_SIGIL_WORDS = re.compile(
    r"\b(?:section|sections|sec|secs|chapter|chapters|chap|ch|rule|rules)\b",
    re.IGNORECASE,
)


def reporter_letters(citation_text: str, number: str) -> str:
    """The reporter/jurisdiction letters a citation uses, normalized for
    comparison: the alphabetic content of everything before the number, minus
    interchangeable sigil words. ``"IA. R. Civ. P. 1.305"`` → ``"iarcivp"``;
    ``"Iowa Code section 537A.1"`` → ``"iowacode"``."""
    idx = citation_text.find(number)
    prefix = citation_text[:idx] if idx > 0 else ""
    prefix = _SIGIL_WORDS.sub("", prefix)
    return re.sub(r"[^a-z]", "", prefix.lower())


def written_citation(text: str, span: tuple[int, int]) -> str:
    """Reconstruct the full citation the author actually wrote, by extending the
    matched number span left to absorb an immediately-preceding reporter/sigil.

    The iteration regex matches only the minimal number ("1.305"), so the
    reporter the author typed ("Iowa R.Civ.P.") lives in the surrounding text;
    we need it to judge the *form*."""
    start, end = span
    number = text[start:end]
    window = text[max(0, start - 45) : start]
    best = None
    for m in _SIGIL_TOKEN_RE.finditer(window):
        if m.end() == len(window):  # sigil sits right before the number
            best = m
    prefix = window[best.start():] if best else ""
    return (prefix + number).strip()


# A sigil word may sit between the reporter and the number ("Iowa Code section
# 2.19", "Iowa R. Crim. P. rule 2.19"); allow it before the end anchor.
_HINT_TAIL = r"(?:\s+(?:section|sections|sec|secs|§|chapter|chapters|ch|rule|rules))?\.?\s*$"

# Reporter/acronym → which corpus the author meant. Used to disambiguate a
# citation that resolves in more than one source (e.g. "2.19" exists as both
# Iowa Code § 2.19 and Iowa R. Crim. P. 2.19). Each pattern is anchored to the
# END of the text immediately before the number. Court-rule reporters — by
# name, by standard abbreviation, and by the colloquial run-together acronyms
# attorneys actually type (IRCP, IRCrP, IRAP, IRE, IRPC) — all point at the
# court-rules corpus.
_SOURCE_HINTS: tuple[tuple[re.Pattern, str], ...] = (
    (
        re.compile(
            r"(?<![A-Za-z])"  # don't match "ire" in "require", "ic" mid-word
            r"(?:i\.?r\.?cr\.?p\.?"
            r"|iowa\s+r\.?\s*crim\.?\s*p\.?"
            r"|iowa\s+rules?\s+of\s+criminal\s+procedure"
            r"|i\.?r\.?c\.?p\.?"
            r"|iowa\s+r\.?\s*civ\.?\s*p\.?"
            r"|iowa\s+rules?\s+of\s+civil\s+procedure"
            r"|i\.?r\.?a\.?p\.?"
            r"|iowa\s+r\.?\s*app\.?\s*p\.?"
            r"|iowa\s+rules?\s+of\s+appellate\s+procedure"
            r"|i\.?r\.?e\.?"
            r"|iowa\s+r\.?\s*evid\.?"
            r"|iowa\s+rules?\s+of\s+evidence"
            r"|i\.?r\.?p\.?c\.?"
            r"|iowa\s+r\.?\s*prof"
            r"|iowa\s+ct\.?\s*r\.?"
            r"|iowa\s+court\s+rules?"
            r"|ia\.?\s+r\.?\s*\w+"
            r"|rules?\s+of\s+(?:criminal|civil|appellate)\s+procedure)" + _HINT_TAIL,
            re.IGNORECASE,
        ),
        "iowa-court-rules",
    ),
    (
        re.compile(
            r"(?<![A-Za-z])(?:iowa\s+code|ia\.?\s+code|i\.?\s*c\.?)" + _HINT_TAIL,
            re.IGNORECASE,
        ),
        "iowa-code",
    ),
)


# Some authors separate chapter and section with a hyphen ("Ia. Code 321-218",
# "IRE 5-403", "321J-2") instead of a dot. The parser only accepts ".", so it
# splits these into two useless pieces and the citation is SILENTLY DROPPED.
# Normalize the chapter–section hyphen to a dot — but ONLY when it directly
# follows a citation reporter/sigil, so a date ("2020-2021"), a numeric range
# ("sections 1-5" — no reporter immediately on the number), or a dollar range is
# never touched. The "-" → "." swap is length-preserving, so spans stay aligned.
# Only NAMED reporters anchor the rewrite — NOT "section(s)", "§", or "rule(s)",
# which routinely introduce ranges ("sections 1-5", "§§ 1-5") that must stay
# hyphenated. The malformed citations attorneys actually type here always carry
# a named reporter ("Ia. Code 321-218", "IRE 5-403", "IRCrP 2.33-2").
_HYPHEN_CITE = re.compile(
    r"(?P<pre>(?<![A-Za-z])"
    r"(?:ia\.?\s+code|iowa\s+code|i\.?\s*c\.?"
    r"|ire|ircrp|ircp|irap|irpc"
    r"|iowa\s+r\.?\s*\w+\.?\s*p?\.?"
    r"|ia\.?\s+r\.?\s*\w+\.?\s*p?\.?)\s*)"
    r"(?P<chap>\d+[A-Z]?)-(?P<sec>\d+)",
    re.IGNORECASE,
)


def normalize_citation_hyphens(text: str) -> str:
    """Rewrite reporter-anchored "chapter-section" hyphens to dots so the parser
    can see the citation (e.g. "Ia. Code 321-218" → "Ia. Code 321.218"). A cite
    whose chapter–section is already dotted ("2.33-2-b") is untouched here — its
    trailing hyphen subsections are recovered separately."""
    return _HYPHEN_CITE.sub(
        lambda m: f"{m.group('pre')}{m.group('chap')}.{m.group('sec')}", text
    )


def source_hint(text: str, span: tuple[int, int]) -> str | None:
    """The source slug the author's reporter/acronym points at (e.g. "IRCrP" →
    iowa-court-rules), or None if no reporter precedes the number. Lets the
    verifier pick the right corpus when a number resolves in more than one."""
    prefix = text[max(0, span[0] - 45) : span[0]]
    for pattern, slug in _SOURCE_HINTS:
        if pattern.search(prefix):
            return slug
    return None


def near_match(
    citation: Citation, source: Source
) -> tuple[Node, tuple[str, ...]] | None:
    """For a section that doesn't resolve, try to recover the intended cite by
    dropping 1–2 trailing characters — catching a run-together subdivision like
    ``1.9042`` (= ``1.904`` + ``(2)``). The dropped chars become a subdivision.

    Deliberately conservative: only a 1–2 char drop counts as a plausible typo
    (so we don't trim ``1.9042`` all the way down to an unrelated ``1.9``), and
    the recovered prefix must resolve *in this source* (so a court-rule typo
    isn't "corrected" to a coincidental Iowa Code section)."""
    sec = citation.section
    if not sec:
        return None
    for drop in (1, 2):
        if len(sec) - drop <= len(citation.chapter):
            break
        prefix, suffix = sec[:-drop], sec[-drop:]
        if not suffix.isalnum():
            continue
        node = Node.objects.filter(source=source, path=prefix).first()
        if node is not None:
            return node, (*citation.subdivisions, suffix)
    return None
