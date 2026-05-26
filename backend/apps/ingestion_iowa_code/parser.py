"""Probe-JSON → structured node tree.

Pure: no DB, no I/O. The same JSON in always produces the same tree out, so
the parser is golden-file testable. Keep it that way — push side effects into
the writer.

The probe JSON shape we accept (subset of fields used):

    {
      "code_year": 2026,
      "source_base_url": "...",
      "samples": [
        {
          "chapter": "1",
          "chapter_title": "SOVEREIGNTY ...",
          "url": "...",                     # chapter URL (may be missing)
          "citation_pdf_url": "...",        # optional chapter URLs
          "sections": [
            {
              "number": "1.4",
              "heading": "Acquisition ...",
              "body_text": "...",
              "history_brackets": [...],
              "acts_citations": [...],
              "referred_to_in": ["1.8", "1.11"],
              "citation_pdf_url": "...",
              "citation_html_url": "...",
              "source_rtf_url": "..."
            }
          ]
        }
      ]
    }
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedSection:
    """A single Iowa Code section, ready to become a Node + NodeVersion."""

    chapter: str
    number: str  # "1.4", "714.16", etc.
    heading: str
    body_text: str
    history_brackets: tuple[str, ...]
    acts_citations: tuple[str, ...]
    referred_to_in: tuple[str, ...]
    citation_pdf_url: str
    citation_html_url: str
    source_rtf_url: str

    @property
    def path(self) -> str:
        """Materialized path for fast lookup. Same as the citation number for
        sections — chapter is encoded in the prefix before the dot."""
        return self.number

    @property
    def content_hash(self) -> str:
        """Hash of the *normalized* body text. Heading and metadata are
        excluded by design — a heading typo fix should not invalidate the
        embedding."""
        return _hash(_normalize_body(self.body_text))


@dataclass(frozen=True)
class ParsedChapter:
    number: str  # "1", "12C", "232"
    title: str
    chapter_html_url: str
    chapter_pdf_url: str
    sections: tuple[ParsedSection, ...] = field(default_factory=tuple)

    @property
    def path(self) -> str:
        return self.number


@dataclass(frozen=True)
class SkippedSection:
    """A section dropped during parsing because it didn't fit its chapter.

    These are RTF-scrape false positives (e.g. court-rule cross-references
    misread as section numbers, "Reserved" range markers). We record them so
    the ingest run can surface a count and operators can audit later."""

    chapter: str
    number: str
    reason: str
    heading: str = ""


@dataclass(frozen=True)
class ParseResult:
    code_year: int
    chapters: tuple[ParsedChapter, ...]
    skipped_sections: tuple[SkippedSection, ...] = field(default_factory=tuple)

    def iter_sections(self) -> Iterable[ParsedSection]:
        for ch in self.chapters:
            yield from ch.sections


# Section-number regex: chapter is digits-then-optional-letter-suffix; section
# is whatever follows the dot. Covers "1.4", "12C.3", "714.16".
_SECTION_NUMBER_RE = re.compile(r"^(?P<chapter>\d+[A-Z]?)\.(?P<rest>[\w.()-]+)$")

_CHAPTER_NUMBER_RE = re.compile(r"^\d+[A-Z]?$")


class ParseError(ValueError):
    """Raised when probe JSON deviates from the expected shape."""


def parse_probe_json(payload: dict[str, Any]) -> ParseResult:
    """Convert a probe-JSON payload into a deterministic ParseResult.

    Order of chapters and sections is preserved from the input."""

    if not isinstance(payload, dict):
        raise ParseError("probe payload must be a JSON object")

    code_year_raw = payload.get("code_year")
    if isinstance(code_year_raw, int):
        code_year = code_year_raw
    elif isinstance(code_year_raw, str) and code_year_raw.isdigit():
        code_year = int(code_year_raw)
    else:
        raise ParseError(
            f"code_year must be an int or numeric string, got {code_year_raw!r}"
        )

    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ParseError("samples must be a list")

    chapters: list[ParsedChapter] = []
    skipped: list[SkippedSection] = []
    for raw_chapter in samples:
        chapter, chapter_skipped = _parse_chapter(raw_chapter)
        chapters.append(chapter)
        skipped.extend(chapter_skipped)

    return ParseResult(
        code_year=code_year,
        chapters=tuple(chapters),
        skipped_sections=tuple(skipped),
    )


def _parse_chapter(raw: dict[str, Any]) -> tuple[ParsedChapter, list[SkippedSection]]:
    chapter_number = _require_str(raw, "chapter")
    if not _CHAPTER_NUMBER_RE.match(chapter_number):
        raise ParseError(f"unexpected chapter number: {chapter_number!r}")

    sections_raw = raw.get("sections", [])
    if not isinstance(sections_raw, list):
        raise ParseError(f"sections for chapter {chapter_number} must be a list")

    sections: list[ParsedSection] = []
    skipped: list[SkippedSection] = []
    for raw_section in sections_raw:
        result = _parse_section(raw_section, chapter_number)
        if isinstance(result, SkippedSection):
            log.warning(
                "skipping section %r in chapter %s: %s",
                result.number, chapter_number, result.reason,
            )
            skipped.append(result)
        else:
            sections.append(result)

    chapter = ParsedChapter(
        number=chapter_number,
        title=str(raw.get("chapter_title", "")).strip(),
        chapter_html_url=str(raw.get("url", "")),
        chapter_pdf_url=str(raw.get("citation_pdf_url", "")),
        sections=tuple(sections),
    )
    return chapter, skipped


def _parse_section(
    raw: dict[str, Any], chapter_number: str
) -> ParsedSection | SkippedSection:
    number = _require_str(raw, "number")
    heading = str(raw.get("heading", "")).strip()
    match = _SECTION_NUMBER_RE.match(number)
    if not match:
        return SkippedSection(
            chapter=chapter_number,
            number=number,
            reason="section number does not match expected format",
            heading=heading,
        )
    if match["chapter"] != chapter_number:
        return SkippedSection(
            chapter=chapter_number,
            number=number,
            reason=(
                f"section number prefix {match['chapter']!r} does not match "
                f"declared chapter {chapter_number!r} — likely a scraper "
                f"false positive (court-rule cross-reference or stray marker)"
            ),
            heading=heading,
        )

    if not heading:
        raise ParseError(f"section {number} missing heading")

    body = _normalize_body(str(raw.get("body_text", "")))

    return ParsedSection(
        chapter=chapter_number,
        number=number,
        heading=heading,
        body_text=body,
        history_brackets=_tuple_of_str(raw.get("history_brackets")),
        acts_citations=_tuple_of_str(raw.get("acts_citations")),
        referred_to_in=_tuple_of_str(raw.get("referred_to_in")),
        citation_pdf_url=str(raw.get("citation_pdf_url", "")),
        citation_html_url=str(raw.get("citation_html_url", "")),
        source_rtf_url=str(raw.get("source_rtf_url", "")),
    )


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


# The upstream RTF scrape drops the leading "R" from "Referred to in" and
# leaves stray "; " separators where the link markup used to be. It shows up
# two ways: as its own trailing line ("\n\neferred to in §1.2"), or spliced
# onto the end of the Acts-history line ("…§16; ; ; ; eferred to in §2.14, …"
# followed by a real "\nSee …" note). Match both: an optional run of stray
# semicolons OR a leading newline, then the truncated phrase to end of line.
_REFERRED_ARTIFACT_RE = re.compile(
    r"(?:\n\s*|\s*(?:;\s*)+)eferred to in [^\n]*"
)


def _normalize_body(body: str) -> str:
    """Collapse trailing whitespace and strip the truncated 'eferred to in ...'
    artifact some probe rows carry (see _REFERRED_ARTIFACT_RE). Whitespace
    inside the body is preserved because Iowa Code subsection indentation is
    meaningful."""
    text = body.replace("\r\n", "\n").rstrip()
    text = _REFERRED_ARTIFACT_RE.sub("", text)
    return text.rstrip()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
