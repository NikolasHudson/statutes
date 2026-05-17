"""Iowa Court Rules PDF → probe JSON.

Reads chapter PDFs from ``pdfs/`` and emits ``probe.json`` in roughly the
same shape the Iowa Code probe uses, so the future
``apps/ingestion_iowa_rules`` parser can consume a stable intermediate
artifact instead of fighting PDF text on every run.

The extraction strategy:

1.  Pull text with ``pdfplumber`` at ``x_tolerance=1.5``. The court rules
    PDFs are typeset with positional text where the default tolerance of 3
    glues adjacent words together ("PREAMBLEANDSCOPE"); 1.5 keeps word
    boundaries intact across every chapter spot-checked so far.

2.  Strip the page-header band that repeats on every page (e.g.
    ``December 2020 RULES OF PROFESSIONAL CONDUCT Ch 32, p.5`` or the
    mirrored form ``Ch 32, p.5 RULES OF PROFESSIONAL CONDUCT December
    2020``). The header always carries ``Ch <N>,`` so a simple regex
    catches both orientations.

3.  Split into a header block (chapter title + table of contents) and a
    body block. The TOC is the contiguous run of ``Rule N…`` lines at the
    start of the document; the body begins at the first rule that is
    immediately followed by paragraph text rather than another ``Rule``
    line. Every body rule we collect is required to also appear in the
    TOC — that's how we recover the rule's display heading even when the
    body's heading is wrapped across two lines.

4.  Inside the body, walk forward rule by rule and split each rule into
    ``body_text`` (text before the first ``Comment`` marker), zero-or-more
    ``comments`` blocks (each with an optional label and numbered
    paragraphs), and ``history_brackets`` (the bracketed ``[Court Order
    …]`` lines that close every rule and ground the effective date).

Chapter-specific quirks we've seen:

* Chapter 32 (Prof. Conduct) uses ``Rule 32:1.1`` with a colon between
  chapter and rule; most other chapters use ``Rule 1.402`` (no colon).
* Reserved rules render as ``Rule 32:2.2 Reserved`` with no body — we
  keep them in the output so citations still resolve.
* Chapter 23 sprinkles ``— Form 1: …`` annexes after numbered rules; for
  now they're swallowed into the preceding rule's body.

This script is intentionally a one-file probe. Once the JSON shape is
stable we'll move the parser into ``apps/ingestion_iowa_rules/parser.py``
and the JSON becomes the cached intermediate that the Django writer
consumes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber missing. install with: pip install pdfplumber")


HERE = Path(__file__).resolve().parent
PDFS = HERE / "pdfs"

# The edition date is encoded in the source URL. Keep it as a constant for
# this probe; the production scraper will read it from the listings page.
EDITION_DATE_ISO = "2026-02-27"
EDITION_DATE_URL = "02-27-2026"
SOURCE_BASE_URL = (
    "https://www.legis.iowa.gov/docs/ACO/CR/LINC/"
    f"{EDITION_DATE_URL}.chapter.{{chapter}}.pdf"
)

# Chapter titles harvested from courtRulesListings; reserved chapters are
# the ones whose first-page PDF text is just "CHAPTER N Reserved".
CHAPTER_TITLES: dict[int, str] = {
    1: "Rules of Civil Procedure",
    2: "Rules of Criminal Procedure",
    3: "Standard Forms of Pleadings for Small Claims Actions",
    4: "Protective and No Contact Orders",
    5: "Rules of Evidence",
    6: "Rules of Appellate Procedure",
    7: "Rules of Probate Procedure",
    8: "Rules of Juvenile Procedure",
    9: "Child Support Guidelines",
    10: "Guidelines for Bond Forfeiture and Restoration",
    11: "Standards of Conduct for Mediators",
    12: "Rules for Involuntary Hospitalization of Mentally Ill Persons",
    13: "Rules for Involuntary Commitment or Treatment of Substance Use Disorders",
    14: "Iowa Rules of Electronic Search Warrant Procedure",
    15: "Iowa Rules of Remote Procedure",
    16: "Iowa Rules of Electronic Procedure",
    17: "Forms for Self-Represented Litigants",
    18: "Reserved",
    19: "Reserved",
    20: "Court Records",
    21: "Organization and Procedures of Appellate Courts",
    22: "Judicial Administration",
    23: "Time Standards for Case Processing",
    24: "Reserved",
    25: "Rules for Expanded News Media Coverage",
    26: "Rules for Installment Payment Plans and Court Collection",
    27: "Reserved",
    28: "Reserved",
    29: "Reserved",
    30: "Reserved",
    31: "Admission to the Bar",
    32: "Iowa Rules of Professional Conduct",
    33: "Standards for Professional Conduct",
    34: "Administrative and General Provisions of the Grievance Commission and Attorney Disciplinary Board",
    35: "Iowa Supreme Court Attorney Disciplinary Board Rules of Procedure",
    36: "Grievance Commission Rules of Procedure",
    37: "Commission on the Unauthorized Practice of Law",
    38: "Rules of Procedure of the Commission on the Unauthorized Practice of Law",
    39: "Client Security Commission",
    40: "Regulations of the Client Security Commission",
    41: "Continuing Legal Education for Lawyers",
    42: "Regulations of the Commission on Continuing Legal Education",
    43: "Lawyer Trust Account Commission",
    44: "Lawyer Trust Account Commission Grant Criteria and Guidelines",
    45: "Client Trust Account Rules",
    46: "Rules of the Board of Examiners of Shorthand Reporters",
    47: "Court Interpreter and Translator Rules",
    48: "Code of Professional Conduct for Court Interpreters and Translators",
    49: "Office of Professional Regulation",
    50: "Reserved",
    51: "Iowa Code of Judicial Conduct",
    52: "Rules of Procedure of the State of Iowa Commission on Judicial Qualifications",
    53: "Reserved",
    54: "Reserved",
    55: "Reserved",
    56: "Reserved",
    57: "Reserved",
    58: "Reserved",
    59: "Reserved",
    60: "Reserved",
    61: "Iowa Standards of Practice for Attorneys Representing Parents in Juvenile Court",
    62: "Iowa Standards of Practice for Lawyers Representing Children in Custody Cases",
    63: "Iowa Standards of Practice for Child and Family Reporters in Child Custody Cases",
    64: "Reserved",
    65: "Reserved",
    66: "Reserved",
    67: "Reserved",
    68: "Reserved",
    69: "Reserved",
    70: "Iowa Rules of Juvenile Court Services Directed Programs",
}

# Matches both header orientations: page-top "<Month> <Year> <TITLE> Ch
# 32, p.5" and the mirrored "Ch 32, p.5 <TITLE> <Month> <Year>".
PAGE_HEADER_RE = re.compile(r"^.*Ch\s+\d+[A-Z]?,\s*p\.[ivx\d]+.*$", re.IGNORECASE)

# Rule header: "Rule <chapter>[:.<rest>] <HEADING>". chapter may carry a
# trailing letter (no court-rules chapters do today, but cheap to allow).
# We allow an optional trailing punctuation char after the rule number —
# some chapters' body headings render as ``Rule 1.500.`` or
# ``Rule 51:1.1:`` while the TOC entry omits the trailing punctuation,
# and the rule number must compare equal across the two.
RULE_RE = re.compile(
    r"^Rule\s+(?P<chapter>\d+[A-Z]?)(?P<sep>[:.])(?P<rest>\d[\w.]*?)"
    r"[.:]?(?:\s+(?P<heading>.*))?$"
)


def _normalize_rule_number(chapter: str, sep: str, rest: str) -> str:
    """Strip stray trailing punctuation from the rest segment so the
    same rule rendered as ``1.500`` and ``1.500.`` reconciles to one
    canonical number."""

    return f"{chapter}{sep}{rest.rstrip('.:')}"


# Sentence break inside a rule's heading text: e.g. ch 1 typesets header
# and first body sentence on one line:
#   "Rule 1.101 Applicability; statutes affected. The rules in this chapter..."
# We split at the first period-followed-by-capital, so the heading captures
# just "Applicability; statutes affected" and the body prefix carries the
# rest forward as the first body line.
_HEADING_SENTENCE_BREAK_RE = re.compile(r"^(?P<heading>.+?)\.\s+(?P<body>[A-Z].*)$")


def _split_heading_and_body_prefix(raw_heading: str) -> tuple[str, str]:
    """Return ``(heading, body_prefix)``. If the heading captured from the
    rule header line contains an internal sentence break, the body prefix
    is the trailing sentence; otherwise it's empty."""

    raw_heading = raw_heading.strip()
    if not raw_heading:
        return ("", "")
    m = _HEADING_SENTENCE_BREAK_RE.match(raw_heading)
    if m:
        return (m["heading"].strip(), m["body"].strip())
    return (raw_heading, "")

# Numbered comment paragraphs within a rule: "[1] ..." through "[99] ..."
COMMENT_PARA_RE = re.compile(r"^\[(?P<n>\d+)\]\s+(?P<rest>.+)$")

# History bracket line — closes a rule. Multi-line history brackets are
# joined back together when we extract them.
HISTORY_START_RE = re.compile(r"^\[(?:Court\s+Order|Report|Administrative\s+Directive|Adopted|Amended|Effective)", re.IGNORECASE)


@dataclass
class Rule:
    number: str  # e.g. "32:1.1" or "1.402"
    heading: str
    division: str  # subdivision banner above the rule, "" if none
    body_text: str
    comment_text: str  # Everything between "Comment" line and history brackets
    history_brackets: list[str]
    reserved: bool


@dataclass
class Chapter:
    chapter: str
    chapter_title: str
    reserved: bool
    chapter_pdf_url: str
    page_count: int
    rules: list[Rule] = field(default_factory=list)
    parse_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(pdf_path: Path) -> tuple[str, int]:
    """Return (cleaned text, page count). Cleaned = page-header lines
    dropped and the text from successive pages joined with single newlines."""

    cleaned_pages: list[str] = []
    with pdfplumber.open(pdf_path) as p:
        for page in p.pages:
            raw = page.extract_text(x_tolerance=1.5) or ""
            kept = [
                line for line in raw.splitlines()
                if line.strip() and not PAGE_HEADER_RE.match(line.strip())
            ]
            cleaned_pages.append("\n".join(kept))
        return "\n".join(cleaned_pages), len(p.pages)


# ---------------------------------------------------------------------------
# Rule extraction
# ---------------------------------------------------------------------------


def _rule_match(line: str) -> re.Match[str] | None:
    """Return a RULE_RE match for a line that starts with a rule header,
    else None. We require the line to start with "Rule " so prose like
    "see rule 32:1.4" never matches."""

    line = line.strip()
    if not line.startswith("Rule "):
        return None
    return RULE_RE.match(line)


def _is_all_caps_heading(line: str) -> bool:
    """Subdivision banners and ALL-CAPS rule headings are recognized by
    having no lowercase letters but at least three letters total."""

    letters = [c for c in line if c.isalpha()]
    return bool(letters) and len(letters) >= 3 and all(c.isupper() for c in letters)


def _index_rules(
    lines: list[str], chapter_number: str
) -> tuple[
    list[tuple[int, str, str, str]],  # toc_entries: (line_idx, number, heading, division)
    list[tuple[int, str, str]],        # body_entries: (line_idx, number, heading)
]:
    """Find every rule occurrence in the document and classify each as
    a TOC entry or a body entry.

    The court rules PDFs follow a consistent pattern: every rule appears
    twice — once in the chapter's table of contents (a one-line "Rule
    N.M Heading" entry, optionally with a heading-continuation line), and
    once in the body (the rule's actual content). Trying to split the
    doc into "TOC region" and "body region" via a single boundary line
    is fragile because division banners and page-header strips can push
    the boundary around; rules can also have their TOC and body
    sections separated by long preamble blocks.

    More robust strategy: for each unique rule number, take its *first*
    occurrence as the TOC entry (which contributes the display heading
    and division) and its *last* occurrence as the body entry (which
    starts the rule's text). If a rule appears only once it's almost
    always a Reserved-rule placeholder in the body — those have no TOC
    entry because they have no real body either."""

    # Each occurrence is (line_idx, heading, body_prefix). body_prefix is
    # non-empty only when the rule header line carries body text after a
    # sentence break — typical for ch 1, 2, 5, 6 where header and first
    # sentence share a single typeset line.
    rule_positions: dict[str, list[tuple[int, str, str]]] = {}
    division_for_idx: list[tuple[int, str]] = []

    # Division-banner attribution: each ALL-CAPS contiguous block above a
    # rule is treated as a banner. We record the LAST line of the block
    # rather than the first because banners are sometimes split into a
    # generic prefix and a more specific subdivision name (e.g. ch 1:
    # "DIVISION II / ACTIONS, JOINDER OF ACTIONS AND PARTIES / A. PARTIES
    # GENERALLY; CAPACITY" — the last line is the most useful label).
    # The very first block typically holds the chapter title ("CHAPTER N
    # / <Title>"); if that's all it holds we skip it entirely.
    current_block: list[str] = []
    current_block_start = -1
    is_first_block = True

    def commit_block() -> None:
        nonlocal current_block, current_block_start, is_first_block
        if not current_block:
            return
        if is_first_block:
            is_first_block = False
            # Pure chapter title block (CHAPTER N + title line(s) only).
            # Recognize by the first line and skip if no obvious division
            # marker words appear within it.
            looks_like_title_only = (
                re.match(r"^CHAPTER\s+\d", current_block[0])
                and not any(
                    re.match(r"^(DIVISION|CANON|ARTICLE|TITLE|PART|PREAMBLE|SUBCHAPTER)", line)
                    for line in current_block[1:]
                )
            )
            if looks_like_title_only:
                current_block = []
                current_block_start = -1
                return
        division_for_idx.append((current_block_start, current_block[-1]))
        current_block = []
        current_block_start = -1

    for idx, line in enumerate(lines):
        stripped = line.strip()
        m = _rule_match(line)
        if m and m["chapter"] == chapter_number:
            commit_block()
            number = _normalize_rule_number(m["chapter"], m["sep"], m["rest"])
            raw_heading = (m["heading"] or "").strip()
            heading, body_prefix = _split_heading_and_body_prefix(raw_heading)
            rule_positions.setdefault(number, []).append((idx, heading, body_prefix))
        elif (
            stripped
            and _is_all_caps_heading(stripped)
            and not stripped.startswith("[")
        ):
            if not current_block:
                current_block_start = idx
            current_block.append(stripped)
        elif stripped:
            commit_block()

    commit_block()

    toc_entries: list[tuple[int, str, str, str]] = []
    # body_entries items: (line_idx, number, heading, body_prefix)
    body_entries: list[tuple[int, str, str, str]] = []

    def _looks_like_body(idx: int) -> bool:
        """True if the occurrence at ``idx`` looks like a body entry —
        the next 2 non-blank lines are prose, with no rule header or
        ``Rules X.YY Reserved`` range marker appearing among them.

        TOC entries are densely packed: another rule header sits within
        about 2 non-blank lines, possibly with a single wrapped heading
        continuation in between. Body entries have at least two lines of
        real content (very short rules like ch 51:1.1 have just one
        sentence + a history bracket before the next rule)."""

        non_blank_seen = 0
        for k in range(idx + 1, min(idx + 8, len(lines))):
            next_line = lines[k].strip()
            if not next_line:
                continue
            if _rule_match(next_line) or re.match(r"^Rules?\s+\d", next_line):
                return False
            # ALL-CAPS lines are division banners or wrapped TOC headings,
            # not body prose. Skip without counting — they don't prove
            # there's a real rule body here.
            if _is_all_caps_heading(next_line):
                continue
            non_blank_seen += 1
            if non_blank_seen >= 2:
                return True
        return non_blank_seen > 0

    for number, positions in rule_positions.items():
        # Court-rules PDFs are structured so each rule appears once in
        # the chapter TOC and once in the body. Some rules in chapter 1
        # have a third occurrence inside a Comments / amendment-notes
        # block (e.g. rule 1.500's commentary opens with "Rule 1.500.
        # The entirety of rule 1.500 is added…"). Treat them as:
        #   positions[0] = TOC entry
        #   positions[1] = body entry
        #   positions[2:] = commentary, ignored at the indexing layer
        if len(positions) >= 2:
            toc_idx, toc_heading, _ = positions[0]
            body_idx, body_heading, body_prefix = positions[1]
            toc_entries.append((toc_idx, number, toc_heading, ""))
            body_entries.append((body_idx, number, body_heading, body_prefix))
        else:
            # Single occurrence — chapter has no TOC, or the rule was
            # added/renumbered without updating the TOC. Use the prose
            # check to decide whether this is a body-only entry.
            idx, heading, body_prefix = positions[0]
            if _looks_like_body(idx):
                body_entries.append((idx, number, heading, body_prefix))
            else:
                toc_entries.append((idx, number, heading, ""))

    toc_entries.sort(key=lambda x: x[0])
    body_entries.sort(key=lambda x: x[0])

    # Attribute divisions. Walk the TOC entries in order; the current
    # division is whatever banner was last seen at or before this rule's
    # TOC line index.
    toc_with_divs: list[tuple[int, str, str, str]] = []
    div_iter = iter(division_for_idx)
    upcoming = next(div_iter, None)
    current_division = ""
    for line_idx, number, heading, _ in toc_entries:
        while upcoming and upcoming[0] < line_idx:
            current_division = upcoming[1]
            upcoming = next(div_iter, None)
        toc_with_divs.append((line_idx, number, heading, current_division))

    return toc_with_divs, body_entries


def _join_toc_headings(
    toc: list[tuple[int, str, str, str]], lines: list[str]
) -> dict[str, str]:
    """Build {rule_number → display heading} from the TOC. TOC entries
    sometimes wrap across multiple lines (a long rule title); any
    continuation line lives between the entry and the next entry — append
    it to the heading. Division banners (ALL CAPS short) are skipped."""

    headings: dict[str, str] = {}
    for i, (line_idx, number, heading, _division) in enumerate(toc):
        next_idx = toc[i + 1][0] if i + 1 < len(toc) else line_idx + 1
        chunks = [heading] if heading else []
        for j in range(line_idx + 1, next_idx):
            chunk = lines[j].strip()
            if not chunk:
                continue
            # Skip division banners (ALL CAPS, any length — judicial-conduct
            # canons run multi-line).
            if _is_all_caps_heading(chunk):
                continue
            # Skip range-reserved markers like "Rules 1.102 to 1.200 Reserved"
            # — they're TOC entries we deliberately don't capture as rules.
            if re.match(r"^Rules?\s+\d", chunk):
                continue
            chunks.append(chunk)
        headings[number] = " ".join(chunks).strip()
    return headings


def _slice_body_into_rules(
    lines: list[str],
    body_entries: list[tuple[int, str, str, str]],
) -> list[tuple[str, str, list[str]]]:
    """Slice each rule's body using explicit body-entry line indexes.

    For each rule, take the lines between its body line and the next
    rule's body line. Prepend any body_prefix that was sharing the rule
    header line, and strip trailing ALL-CAPS banner lines off the tail
    (those are the next rule's division header, not this rule's body)."""

    chunks: list[tuple[str, str, list[str]]] = []

    def peel_trailing_banners(body_lines: list[str]) -> None:
        while body_lines:
            tail = body_lines[-1].strip()
            if (
                tail
                and not tail.startswith("[")
                and _is_all_caps_heading(tail)
            ):
                body_lines.pop()
            else:
                break

    def peel_leading_banners(body_lines: list[str]) -> None:
        """Peel ALL-CAPS lines off the front of body_lines. Body rule
        headers sometimes wrap onto a second ALL-CAPS line (ch 32 rule
        32:1.2: ``Rule 32:1.2 SCOPE OF REPRESENTATION...`` then ``BETWEEN
        CLIENT AND LAWYER``) — that continuation belongs to the heading,
        not the body."""

        while body_lines:
            head = body_lines[0].strip()
            if (
                head
                and not head.startswith("[")
                and _is_all_caps_heading(head)
            ):
                body_lines.pop(0)
            else:
                break

    for i, (line_idx, number, body_heading, body_prefix) in enumerate(body_entries):
        end_idx = body_entries[i + 1][0] if i + 1 < len(body_entries) else len(lines)
        body_lines: list[str] = []
        if body_prefix:
            body_lines.append(body_prefix)
        for raw in lines[line_idx + 1 : end_idx]:
            if re.match(r"^Rules?\s+\d", raw.strip()):
                continue
            body_lines.append(raw)
        # Peel leading wrapped-heading lines (ALL CAPS) — only if no
        # body_prefix was captured from the header line, since a body
        # prefix already proves the heading didn't wrap.
        if not body_prefix:
            peel_leading_banners(body_lines)
        peel_trailing_banners(body_lines)
        chunks.append((number, body_heading, body_lines))

    return chunks


def _parse_rule_body(
    body_lines: list[str],
) -> tuple[str, str, list[str]]:
    """Split a single rule's body into (body_text, comment_text, history_brackets).

    The body section runs until the first standalone ``Comment`` line or
    the first history bracket. Comment text is everything after
    ``Comment`` up to the history brackets. We deliberately do *not* try
    to detect sub-labels inside the comments block ("Legal Knowledge and
    Skill" vs. continuation prose) — they're visually distinguished in
    the PDF by bold/italic that we can't recover from positional text,
    and a wrong split is worse than no split. Downstream callers that
    want the structure can re-parse comment_text by hunting for the
    ``[N]`` paragraph markers."""

    body_paras: list[str] = []
    comment_paras: list[str] = []
    history: list[str] = []
    history_buf: list[str] = []

    current_para: list[str] = []
    in_comments = False

    def flush():
        nonlocal current_para
        if not current_para:
            return
        joined = " ".join(s.strip() for s in current_para if s.strip()).strip()
        current_para = []
        if not joined:
            return
        (comment_paras if in_comments else body_paras).append(joined)

    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue

        # History bracket: drain whatever we have, accumulate until
        # bracket balance closes (rare 2-line history blocks exist).
        if HISTORY_START_RE.match(stripped) or history_buf:
            flush()
            history_buf.append(stripped)
            joined = " ".join(history_buf)
            if joined.count("[") <= joined.count("]"):
                history.append(joined)
                history_buf = []
            continue

        # Standalone "Comment" pivots us into the comment section.
        if stripped == "Comment" and not in_comments:
            flush()
            in_comments = True
            continue

        # Inside the comment section, a "[N]" line starts a new paragraph.
        if in_comments and COMMENT_PARA_RE.match(stripped):
            flush()
            current_para.append(stripped)
            continue

        current_para.append(stripped)

    flush()
    return (
        "\n\n".join(body_paras),
        "\n\n".join(comment_paras),
        history,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_chapter(chapter_number: int) -> Chapter:
    """Parse a single chapter PDF into a structured ``Chapter``."""

    pdf_path = PDFS / f"chapter-{chapter_number:02d}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    title = CHAPTER_TITLES.get(chapter_number, "")
    reserved_chapter = title == "Reserved"
    pdf_url = SOURCE_BASE_URL.format(chapter=chapter_number)

    text, page_count = extract_text(pdf_path)
    lines = text.splitlines()

    chapter = Chapter(
        chapter=str(chapter_number),
        chapter_title=title,
        reserved=reserved_chapter,
        chapter_pdf_url=pdf_url,
        page_count=page_count,
    )

    if reserved_chapter:
        # Reserved chapters carry a single placeholder line; nothing to parse.
        return chapter

    toc, body_entries = _index_rules(lines, str(chapter_number))
    headings_by_number = _join_toc_headings(toc, lines)
    divisions_by_number = {number: div for _, number, _, div in toc}

    if not toc and not body_entries:
        chapter.parse_notes.append(
            "no Rule N.M headers detected — chapter likely uses a "
            "non-Rule structure (Forms, Canons, Roman-numeral standards)"
        )
        return chapter

    body_chunks = _slice_body_into_rules(lines, body_entries)
    if not body_chunks:
        chapter.parse_notes.append("TOC found but no body rules parsed")
        return chapter

    for number, body_heading, body_lines in body_chunks:
        toc_heading = headings_by_number.get(number, "")
        display_heading = toc_heading or body_heading
        reserved_rule = body_heading.strip().lower() == "reserved" or not body_lines

        body_text, comment_text, history = _parse_rule_body(body_lines)

        chapter.rules.append(
            Rule(
                number=number,
                heading=display_heading,
                division=divisions_by_number.get(number, ""),
                body_text=body_text,
                comment_text=comment_text,
                history_brackets=history,
                reserved=reserved_rule,
            )
        )

    # Sanity check: every rule we parsed should appear in the TOC.
    toc_numbers = {n for _, n, _, _ in toc}
    body_numbers = {r.number for r in chapter.rules}
    missing_from_body = toc_numbers - body_numbers
    if missing_from_body:
        chapter.parse_notes.append(
            f"rules in TOC but not in body: {sorted(missing_from_body)}"
        )
    extra_in_body = body_numbers - toc_numbers
    if extra_in_body:
        chapter.parse_notes.append(
            f"rules in body but not in TOC: {sorted(extra_in_body)}"
        )

    return chapter


def build_payload(chapter_numbers: list[int]) -> dict:
    """Build the probe-JSON document covering the requested chapters."""

    samples = [parse_chapter(n) for n in chapter_numbers]
    total_rules = sum(len(c.rules) for c in samples)
    return {
        "edition_date": EDITION_DATE_ISO,
        "source_base_url": SOURCE_BASE_URL,
        "summary": {
            "chapters_probed": len(samples),
            "chapters_ok": sum(1 for c in samples if not c.parse_notes and not c.reserved),
            "total_rules": total_rules,
        },
        "samples": [_chapter_to_dict(c) for c in samples],
    }


def _chapter_to_dict(c: Chapter) -> dict:
    return {
        "chapter": c.chapter,
        "chapter_title": c.chapter_title,
        "reserved": c.reserved,
        "chapter_pdf_url": c.chapter_pdf_url,
        "page_count": c.page_count,
        "rule_count": len(c.rules),
        "rules": [
            {
                "number": r.number,
                "heading": r.heading,
                "division": r.division,
                "body_text": r.body_text,
                "body_chars": len(r.body_text),
                "comment_text": r.comment_text,
                "comment_chars": len(r.comment_text),
                "history_brackets": r.history_brackets,
                "reserved": r.reserved,
            }
            for r in c.rules
        ],
        "parse_notes": c.parse_notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "chapters",
        nargs="*",
        type=int,
        help="Chapter numbers to probe (default: 32 — Prof. Conduct)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=HERE / "probe.json",
        help="Output JSON path (default: ./probe.json)",
    )
    args = parser.parse_args()
    chapter_numbers = args.chapters or [32]
    payload = build_payload(chapter_numbers)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    print(f"Wrote {args.output}")
    print(f"  chapters: {payload['summary']['chapters_probed']}")
    print(f"  rules:    {payload['summary']['total_rules']}")
    for ch in payload["samples"]:
        notes = "; ".join(ch["parse_notes"]) if ch["parse_notes"] else "ok"
        print(f"  ch {ch['chapter']:>3} ({ch['rule_count']:>3} rules): {notes}")


if __name__ == "__main__":
    main()
