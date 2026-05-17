"""Court-Rules probe-JSON → structured node tree.

Pure: no DB, no I/O. Same JSON in always produces the same tree out, so the
parser is golden-file testable. Keep it that way — push side effects into the
writer.

Mirrors ``apps.ingestion_iowa_code.parser`` but for the Court Rules hierarchy,
which is two levels deep — ``chapter`` → ``rule`` — instead of the Code's
title/chapter/section. Divisions ("DIVISION I", "CANON 2", "PREAMBLE AND
SCOPE") are best-effort categorization in the source, not authoritative
structure, so they ride along as rule metadata rather than a node level.

The probe JSON shape we accept (subset of fields used):

    {
      "edition_date": "2026-02-27",
      "source_base_url": "...chapter.{chapter}.pdf",
      "samples": [
        {
          "chapter": "32",
          "chapter_title": "Iowa Rules of Professional Conduct",
          "reserved": false,
          "chapter_pdf_url": "...",
          "page_count": 89,
          "rule_count": 59,
          "parse_notes": [],
          "rules": [
            {
              "number": "32:1.0",
              "heading": "Terminology",
              "division": "PREAMBLE AND SCOPE",
              "body_text": "...",
              "comment_text": "...",
              "history_brackets": ["[Court Order ...]"],
              "reserved": false
            }
          ]
        }
      ]
    }
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

log = logging.getLogger(__name__)

# Header the probe inserts between rule prose and official commentary. Kept in
# the combined body so commentary is searchable and version-tracked; a change
# to a Comment is a real amendment of the rule's authority.
COMMENT_SEPARATOR = "\n\nComment\n\n"

# Node.heading is varchar(500). A handful of "Forms" rules have a TOC entry
# that concatenates the whole form list into one line ("Forms Form 1: ...
# Form 2: ..."). Split that at the first form item: the prefix is the real
# heading, the form list is content that belongs in the body.
HEADING_MAX = 500
_FORM_LIST_RE = re.compile(r"\s+(?=Form\s+(?:1|A|I)\b)")


@dataclass(frozen=True)
class ParsedRule:
    """A single Court Rule, ready to become a Node + NodeVersion."""

    chapter: str
    number: str  # normalized: "32:1.0", "1.402", "4.100"
    heading: str
    division: str
    body_text: str  # rule prose only
    comment_text: str  # official commentary, may be ""
    history_brackets: tuple[str, ...]

    @property
    def path(self) -> str:
        """Materialized path for fast lookup. The rule number already encodes
        the chapter as the prefix before the first ':' or '.'."""
        return self.number

    @property
    def ordinal(self) -> str:
        """The portion of the number after the chapter prefix."""
        return _RULE_NUMBER_RE.match(self.number)["rest"]

    @property
    def combined_text(self) -> str:
        """What lands in NodeVersion.body_text: prose, then commentary under a
        ``Comment`` banner so retrieval and embeddings cover both."""
        if self.comment_text.strip():
            return f"{self.body_text}{COMMENT_SEPARATOR}{self.comment_text}".strip()
        return self.body_text

    @property
    def content_hash(self) -> str:
        """Hash of the *normalized* combined text. Heading, division and
        history are excluded by design — a heading typo fix or a new history
        bracket should not invalidate the embedding."""
        return _hash(_normalize_body(self.combined_text))


@dataclass(frozen=True)
class ParsedChapter:
    number: str  # "1" .. "70"
    title: str
    chapter_pdf_url: str
    reserved: bool
    page_count: int
    parse_notes: tuple[str, ...]
    rules: tuple[ParsedRule, ...] = field(default_factory=tuple)

    @property
    def path(self) -> str:
        return self.number


@dataclass(frozen=True)
class SkippedRule:
    """A rule dropped during parsing. The common case is a
    ``Rule N.M Reserved`` placeholder with no body — a real gap in the
    numbering, not content. Recorded so the ingest run can surface a count."""

    chapter: str
    number: str
    reason: str
    heading: str = ""


@dataclass(frozen=True)
class ParseResult:
    edition_date: dt.date
    chapters: tuple[ParsedChapter, ...]
    skipped_rules: tuple[SkippedRule, ...] = field(default_factory=tuple)

    @property
    def edition_year(self) -> int:
        return self.edition_date.year

    def iter_rules(self) -> Iterable[ParsedRule]:
        for ch in self.chapters:
            yield from ch.rules


# Rule number: chapter prefix is plain digits; the separator is ':' (ch 32
# Prof. Conduct) or '.'; the rest is whatever follows. Covers "32:1.0",
# "1.402", "4.100".
_RULE_NUMBER_RE = re.compile(r"^(?P<chapter>\d+)[:.](?P<rest>[\w.:()-]+)$")
_CHAPTER_NUMBER_RE = re.compile(r"^\d+$")


class ParseError(ValueError):
    """Raised when probe JSON deviates from the expected shape."""


def parse_probe_json(payload: dict[str, Any]) -> ParseResult:
    """Convert a Court-Rules probe-JSON payload into a deterministic
    ParseResult. Order of chapters and rules is preserved from the input."""

    if not isinstance(payload, dict):
        raise ParseError("probe payload must be a JSON object")

    edition_date = _parse_edition_date(payload.get("edition_date"))

    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ParseError("samples must be a list")

    chapters: list[ParsedChapter] = []
    skipped: list[SkippedRule] = []
    for raw_chapter in samples:
        chapter, chapter_skipped = _parse_chapter(raw_chapter)
        chapters.append(chapter)
        skipped.extend(chapter_skipped)

    return ParseResult(
        edition_date=edition_date,
        chapters=tuple(chapters),
        skipped_rules=tuple(skipped),
    )


def _parse_edition_date(value: Any) -> dt.date:
    if not isinstance(value, str) or not value.strip():
        raise ParseError("edition_date must be an ISO date string")
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError as e:
        raise ParseError(f"edition_date is not a valid ISO date: {value!r}") from e


def _parse_chapter(raw: dict[str, Any]) -> tuple[ParsedChapter, list[SkippedRule]]:
    if not isinstance(raw, dict):
        raise ParseError("each sample must be a JSON object")

    chapter_number = _require_str(raw, "chapter")
    if not _CHAPTER_NUMBER_RE.match(chapter_number):
        raise ParseError(f"unexpected chapter number: {chapter_number!r}")

    reserved = bool(raw.get("reserved", False))
    parse_notes = _tuple_of_str(raw.get("parse_notes"))

    rules_raw = raw.get("rules", [])
    if not isinstance(rules_raw, list):
        raise ParseError(f"rules for chapter {chapter_number} must be a list")

    rules: list[ParsedRule] = []
    skipped: list[SkippedRule] = []
    for raw_rule in rules_raw:
        result = _parse_rule(raw_rule, chapter_number)
        if isinstance(result, SkippedRule):
            log.info(
                "skipping rule %r in chapter %s: %s",
                result.number, chapter_number, result.reason,
            )
            skipped.append(result)
        else:
            rules.append(result)

    chapter = ParsedChapter(
        number=chapter_number,
        title=str(raw.get("chapter_title", "")).strip(),
        chapter_pdf_url=str(raw.get("chapter_pdf_url", "")),
        reserved=reserved,
        page_count=int(raw.get("page_count", 0) or 0),
        parse_notes=parse_notes,
        rules=tuple(rules),
    )
    return chapter, skipped


def _parse_rule(raw: dict[str, Any], chapter_number: str) -> ParsedRule | SkippedRule:
    if not isinstance(raw, dict):
        raise ParseError(f"rule in chapter {chapter_number} must be a JSON object")

    number = _normalize_number(_require_str(raw, "number"))
    heading = str(raw.get("heading", "")).strip()

    if raw.get("reserved", False):
        return SkippedRule(
            chapter=chapter_number,
            number=number,
            reason="reserved rule placeholder — no content",
            heading=heading,
        )

    match = _RULE_NUMBER_RE.match(number)
    if not match:
        return SkippedRule(
            chapter=chapter_number,
            number=number,
            reason="rule number does not match expected format",
            heading=heading,
        )
    if match["chapter"] != chapter_number:
        return SkippedRule(
            chapter=chapter_number,
            number=number,
            reason=(
                f"rule number prefix {match['chapter']!r} does not match "
                f"declared chapter {chapter_number!r}"
            ),
            heading=heading,
        )

    if not heading:
        raise ParseError(f"rule {number} missing heading")

    body_text = _normalize_body(str(raw.get("body_text", "")))
    heading, body_text = _split_overlong_heading(heading, body_text)

    return ParsedRule(
        chapter=chapter_number,
        number=number,
        heading=heading,
        division=str(raw.get("division", "")).strip(),
        body_text=body_text,
        comment_text=_normalize_body(str(raw.get("comment_text", ""))),
        history_brackets=_tuple_of_str(raw.get("history_brackets")),
    )


def _split_overlong_heading(heading: str, body_text: str) -> tuple[str, str]:
    """Keep ``heading`` within Node.heading's column width.

    The only over-length headings in the corpus are "Forms" rules whose TOC
    line absorbed the entire form list. Split at the first form item, keep the
    prefix as the heading, and prepend the form list to the body so nothing is
    lost. Falls back to a hard truncation if no form boundary is found."""
    if len(heading) <= HEADING_MAX:
        return heading, body_text

    match = _FORM_LIST_RE.search(heading)
    if match and match.start() <= HEADING_MAX:
        clean = heading[: match.start()].strip()
        form_list = heading[match.start():].strip()
        body_text = f"{form_list}\n\n{body_text}".strip()
        return clean, body_text

    return heading[:HEADING_MAX].rstrip(), body_text


def _normalize_number(number: str) -> str:
    """Strip stray trailing punctuation the PDF extractor sometimes leaves."""
    return number.strip().rstrip(".:").strip()


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ParseError(f"missing or empty {key!r}")
    return value.strip()


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ParseError(f"expected list, got {type(value).__name__}")
    return tuple(str(v).strip() for v in value if str(v).strip())


def _normalize_body(body: str) -> str:
    """Collapse CRLF and trailing whitespace. Interior whitespace is preserved
    — rule body indentation and the \\n\\n paragraph breaks are meaningful."""
    return body.replace("\r\n", "\n").rstrip()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
