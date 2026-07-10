"""Iowa Administrative Code probe-JSON → structured node tree.

Pure: no DB, no I/O. Same JSON in always produces the same tree out, so the
parser is golden-file testable. Push side effects into the writer.

Mirrors ``apps.ingestion_iowa_rules.parser`` but for the IAC's **three-level**
hierarchy — ``agency`` → ``chapter`` → ``rule`` — instead of the Court Rules'
two levels. Subrules and paragraphs ride inside the rule body (like Iowa Code
subsections), not as their own node level. The enabling-statute chapter(s) in a
rule's parenthetical (``441—65.2(234)`` → Iowa Code ch. 234) are carried as
metadata for the statute↔regulation cross-reference backfill (Phase 3).

Path convention (``Node.path``, the citation key):

    agency   "441"
    chapter  "441—65"      (agency, em dash, chapter number)
    rule     "441—65.2"    (chapter, dot, rule number) == the IAC rule citation

The probe JSON shape we accept (subset of fields used):

    {
      "pub_date": "2026-07-08",
      "agencies": [
        {
          "agency": "441",
          "agency_name": "Health and Human Services Department",
          "chapters": [
            {
              "chapter": "65",
              "chapter_title": "SNAP ADMINISTRATION",
              "reserved": false,
              "chapter_docx_url": "...", "chapter_pdf_url": "...",
              "prior_agencies": ["Prior to 7/1/83, Social Services[770] Ch 65"],
              "parse_notes": [],
              "rules": [
                {
                  "number": "65.2",
                  "heading": "Administration of program",
                  "enabling_statutes": ["234"],
                  "body_text": "...(includes subrules)...",
                  "subrules": ["65.2(1)"],
                  "history_brackets": ["[ARC 9310C, IAB 5/28/25, effective 8/1/25]"],
                  "effective_from": "2025-08-01",
                  "reserved": false
                }
              ]
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

EM_DASH = "—"
HEADING_MAX = 500  # Node.heading is varchar(500)

# A rule number is "chapter.rule": the integer chapter, a dot, the rule number
# (which may itself carry a letter suffix in rare cases). "65.2", "75.85", "1.10".
_RULE_NUMBER_RE = re.compile(r"^(?P<chapter>\d+)\.(?P<rule>\d+[A-Za-z]?)$")
# Agency id: digits with an optional letter suffix ("441", "193A").
_AGENCY_RE = re.compile(r"^\d+[A-Za-z]?$")
_CHAPTER_NUMBER_RE = re.compile(r"^\d+$")


class ParseError(ValueError):
    """Raised when probe JSON deviates from the expected shape."""


@dataclass(frozen=True)
class ParsedRule:
    """A single administrative rule, ready to become a Node + NodeVersion."""

    agency: str
    chapter: str  # the chapter number, e.g. "65"
    number: str  # "65.2" (chapter.rule)
    heading: str
    enabling_statutes: tuple[str, ...]  # Iowa Code chapters, e.g. ("234",)
    body_text: str  # rule prose incl. subrules/paragraphs
    history_brackets: tuple[str, ...]
    effective_from: dt.date | None

    @property
    def path(self) -> str:
        return f"{self.agency}{EM_DASH}{self.number}"

    @property
    def chapter_path(self) -> str:
        return f"{self.agency}{EM_DASH}{self.chapter}"

    @property
    def ordinal(self) -> str:
        return self.number

    @property
    def content_hash(self) -> str:
        """Hash of the *normalized body only*. Heading, enabling statutes and
        history are excluded by design — a heading fix or a new ARC bracket
        must not invalidate the embedding."""
        return _hash(_normalize_body(self.body_text))


@dataclass(frozen=True)
class ParsedChapter:
    agency: str
    number: str  # "65"
    title: str
    reserved: bool
    chapter_docx_url: str
    chapter_pdf_url: str
    prior_agencies: tuple[str, ...]
    parse_notes: tuple[str, ...]
    rules: tuple[ParsedRule, ...] = field(default_factory=tuple)

    @property
    def path(self) -> str:
        return f"{self.agency}{EM_DASH}{self.number}"


@dataclass(frozen=True)
class ParsedAgency:
    agency: str  # "441"
    name: str
    chapters: tuple[ParsedChapter, ...] = field(default_factory=tuple)

    @property
    def path(self) -> str:
        return self.agency


@dataclass(frozen=True)
class SkippedRule:
    agency: str
    chapter: str
    number: str
    reason: str
    heading: str = ""


@dataclass(frozen=True)
class ParseResult:
    pub_date: dt.date
    agencies: tuple[ParsedAgency, ...]
    skipped_rules: tuple[SkippedRule, ...] = field(default_factory=tuple)

    @property
    def edition_year(self) -> int:
        return self.pub_date.year

    def iter_chapters(self) -> Iterable[ParsedChapter]:
        for ag in self.agencies:
            yield from ag.chapters

    def iter_rules(self) -> Iterable[ParsedRule]:
        for ch in self.iter_chapters():
            yield from ch.rules


def parse_probe_json(payload: dict[str, Any]) -> ParseResult:
    """Convert an IAC probe-JSON payload into a deterministic ParseResult.
    Order of agencies, chapters and rules is preserved from the input."""

    if not isinstance(payload, dict):
        raise ParseError("probe payload must be a JSON object")

    pub_date = _parse_date(payload.get("pub_date"), "pub_date")

    agencies_raw = payload.get("agencies")
    if not isinstance(agencies_raw, list):
        raise ParseError("agencies must be a list")

    agencies: list[ParsedAgency] = []
    skipped: list[SkippedRule] = []
    for raw_agency in agencies_raw:
        agency, agency_skipped = _parse_agency(raw_agency)
        agencies.append(agency)
        skipped.extend(agency_skipped)

    return ParseResult(
        pub_date=pub_date,
        agencies=tuple(agencies),
        skipped_rules=tuple(skipped),
    )


def _parse_agency(raw: dict[str, Any]) -> tuple[ParsedAgency, list[SkippedRule]]:
    if not isinstance(raw, dict):
        raise ParseError("each agency must be a JSON object")

    agency_id = _require_str(raw, "agency")
    if not _AGENCY_RE.match(agency_id):
        raise ParseError(f"unexpected agency id: {agency_id!r}")

    chapters_raw = raw.get("chapters", [])
    if not isinstance(chapters_raw, list):
        raise ParseError(f"chapters for agency {agency_id} must be a list")

    chapters: list[ParsedChapter] = []
    skipped: list[SkippedRule] = []
    for raw_chapter in chapters_raw:
        chapter, chapter_skipped = _parse_chapter(raw_chapter, agency_id)
        chapters.append(chapter)
        skipped.extend(chapter_skipped)

    return (
        ParsedAgency(
            agency=agency_id,
            name=str(raw.get("agency_name", "")).strip(),
            chapters=tuple(chapters),
        ),
        skipped,
    )


def _parse_chapter(
    raw: dict[str, Any], agency_id: str
) -> tuple[ParsedChapter, list[SkippedRule]]:
    if not isinstance(raw, dict):
        raise ParseError("each chapter must be a JSON object")

    chapter_number = _require_str(raw, "chapter")
    if not _CHAPTER_NUMBER_RE.match(chapter_number):
        raise ParseError(f"unexpected chapter number: {chapter_number!r}")

    reserved = bool(raw.get("reserved", False))
    rules_raw = raw.get("rules", [])
    if not isinstance(rules_raw, list):
        raise ParseError(
            f"rules for chapter {agency_id}-{chapter_number} must be a list"
        )

    rules: list[ParsedRule] = []
    skipped: list[SkippedRule] = []
    for raw_rule in rules_raw:
        result = _parse_rule(raw_rule, agency_id, chapter_number)
        if isinstance(result, SkippedRule):
            log.info(
                "skipping rule %r in %s-%s: %s",
                result.number, agency_id, chapter_number, result.reason,
            )
            skipped.append(result)
        else:
            rules.append(result)

    chapter = ParsedChapter(
        agency=agency_id,
        number=chapter_number,
        title=str(raw.get("chapter_title", "")).strip(),
        reserved=reserved,
        chapter_docx_url=str(raw.get("chapter_docx_url", "")),
        chapter_pdf_url=str(raw.get("chapter_pdf_url", "")),
        prior_agencies=_tuple_of_str(raw.get("prior_agencies")),
        parse_notes=_tuple_of_str(raw.get("parse_notes")),
        rules=tuple(rules),
    )
    return chapter, skipped


def _parse_rule(
    raw: dict[str, Any], agency_id: str, chapter_number: str
) -> ParsedRule | SkippedRule:
    if not isinstance(raw, dict):
        raise ParseError(f"rule in {agency_id}-{chapter_number} must be an object")

    number = str(raw.get("number", "")).strip()
    heading = str(raw.get("heading", "")).strip()

    if raw.get("reserved", False):
        return SkippedRule(
            agency=agency_id, chapter=chapter_number, number=number,
            reason="reserved rule placeholder — no content", heading=heading,
        )

    match = _RULE_NUMBER_RE.match(number)
    if not match:
        return SkippedRule(
            agency=agency_id, chapter=chapter_number, number=number,
            reason="rule number does not match expected format", heading=heading,
        )
    if match["chapter"] != chapter_number:
        return SkippedRule(
            agency=agency_id, chapter=chapter_number, number=number,
            reason=(
                f"rule chapter prefix {match['chapter']!r} does not match "
                f"declared chapter {chapter_number!r}"
            ),
            heading=heading,
        )
    if not heading:
        return SkippedRule(
            agency=agency_id, chapter=chapter_number, number=number,
            reason="rule missing heading", heading="",
        )

    body_text = _normalize_body(str(raw.get("body_text", "")))
    heading = heading[:HEADING_MAX].rstrip()

    return ParsedRule(
        agency=agency_id,
        chapter=chapter_number,
        number=number,
        heading=heading,
        enabling_statutes=_tuple_of_str(raw.get("enabling_statutes")),
        body_text=body_text,
        history_brackets=_tuple_of_str(raw.get("history_brackets")),
        effective_from=_parse_date(raw.get("effective_from"), "effective_from", optional=True),
    )


def _parse_date(value: Any, field_name: str, *, optional: bool = False) -> dt.date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if optional:
            return None
        raise ParseError(f"{field_name} must be an ISO date string")
    if not isinstance(value, str):
        raise ParseError(f"{field_name} must be a string")
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError as e:
        if optional:
            return None
        raise ParseError(f"{field_name} is not a valid ISO date: {value!r}") from e


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
    """Collapse CRLF and trailing whitespace. Interior whitespace (subrule
    indentation, \\n\\n paragraph breaks) is meaningful and preserved."""
    return body.replace("\r\n", "\n").rstrip()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
