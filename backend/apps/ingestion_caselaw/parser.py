"""JSONL record → structured caselaw node data.

Pure: no DB, no I/O. A JSONL record dict in always produces the same dataclass
out, so the parser is golden-file testable. Side effects live in the writer.

Two record kinds, mirroring the 2-level model (decision → opinion):

- ``parse_decision`` turns a ``clusters.jsonl`` record (plus its joined
  ``docket_number`` and parallel citation strings) into a ``ParsedDecision``
  (the case container + optional head-matter text).
- ``parse_opinion`` turns an ``opinions.jsonl`` record into a ``ParsedOpinion``
  (one lead/concurrence/dissent body), selecting the best text column and
  stripping markup.

Decisions and opinions are parsed independently (not nested) because the
opinions artifact is multi-GB and is streamed one row at a time; the writer
re-links each opinion to its already-written decision node by cluster id.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

# Opinion text-column preference (richest markup first; OCR plain_text last).
# All are NOT NULL DEFAULT '' in CourtListener, so we test for empty string.
_TEXT_FIELDS = (
    "html_with_citations",
    "html_columbia",
    "html_lawbox",
    "xml_harvard",
    "html_anon_2020",
    "html",
    "plain_text",
)

# Opinion ``type`` codes carry a numeric prefix (lead-first ordering) and a
# label, e.g. "020lead", "030concurrence". Map the prefix to a display label.
_OPINION_TYPE_LABELS = {
    "010": "Opinion",
    "015": "Opinion",  # CL stores "015unamimous" (sic)
    "020": "Lead Opinion",
    "025": "Plurality Opinion",
    "030": "Concurrence",
    "035": "In Part",
    "040": "Dissent",
    "050": "Addendum",
    "060": "Remittitur",
    "070": "Rehearing",
    "080": "On the Merits",
    "090": "On Motion to Strike",
}
_TYPE_PREFIX_RE = re.compile(r"^(\d{3})")

# corpus.Node.heading is varchar(500). Case names — especially CourtListener
# ``case_name_full`` party lists — can exceed that and would otherwise crash the
# write with a StringDataRightTruncation. The display heading is capped here; the
# untruncated case name is preserved in ``ParsedDecision.source_metadata``.
MAX_HEADING_LEN = 500


def _cap_heading(value: str) -> str:
    if len(value) <= MAX_HEADING_LEN:
        return value
    return value[: MAX_HEADING_LEN - 1] + "…"


# ---------------------------------------------------------------------------
# Text cleaning (pure)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize newlines, collapse whitespace runs to at most one blank line
    between paragraphs, and strip leading/trailing whitespace."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _TextExtractor(HTMLParser):
    """Collect text content from HTML/XML, dropping tags and script/style
    bodies, with entities resolved. A real parser (not a ``<[^>]+>`` regex) so a
    bare ``<`` in opinion text — e.g. ``if (x < 5)`` — is not mistaken for a tag
    and does not eat surrounding content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _strip_markup(value: str) -> str:
    """Strip HTML/XML tags and resolve entities, then normalize."""
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return _normalize(parser.text())


def _clean_field(field: str, value: str) -> str:
    """plain_text is already text; everything else carries markup to strip."""
    if field == "plain_text":
        return _normalize(value)
    return _strip_markup(value)


def select_body(record: dict[str, Any]) -> str:
    """Return the first non-empty opinion text column (by preference), cleaned.
    Empty string if the opinion has no text in any column."""
    for field in _TEXT_FIELDS:
        value = record.get(field) or ""
        if value.strip():
            return _clean_field(field, value)
    return ""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Opinion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedOpinion:
    """One opinion (lead/concurrence/dissent), ready to become a Node +
    NodeVersion under its decision node."""

    cl_opinion_id: int
    cl_cluster_id: int
    path: str  # "cl-cluster-<cid>/op-<oid>"
    op_type: str
    author_str: str
    author_id: int | None
    per_curiam: bool | None
    joined_by_str: str
    page_count: int | None
    download_url: str
    extracted_by_ocr: bool | None
    sha1: str
    body_text: str  # already selected + markup-stripped + normalized

    @property
    def type_prefix(self) -> str:
        m = _TYPE_PREFIX_RE.match(self.op_type or "")
        return m.group(1) if m else "999"

    @property
    def ordinal(self) -> str:
        return self.type_prefix

    @property
    def heading(self) -> str:
        label = _OPINION_TYPE_LABELS.get(self.type_prefix, "Opinion")
        if self.per_curiam:
            label = f"{label} (Per Curiam)"
        elif self.author_str.strip():
            label = f"{label} ({self.author_str.strip()})"
        return _cap_heading(label)

    @property
    def content_hash(self) -> str:
        """Hash of the normalized body only (heading/metadata excluded, as in
        the Iowa Code parser — a heading tweak must not churn the embedding)."""
        return _hash(self.body_text)

    @property
    def source_metadata(self) -> dict:
        return {
            "cl_opinion_id": self.cl_opinion_id,
            "type": self.op_type,
            "author_str": self.author_str,
            "author_id": self.author_id,
            "per_curiam": self.per_curiam,
            "joined_by_str": self.joined_by_str,
            "page_count": self.page_count,
            "download_url": self.download_url,
            "extracted_by_ocr": self.extracted_by_ocr,
            "sha1": self.sha1,
        }


def parse_opinion(record: dict[str, Any]) -> ParsedOpinion:
    return ParsedOpinion(
        cl_opinion_id=int(record["cl_opinion_id"]),
        cl_cluster_id=int(record["cl_cluster_id"]),
        path=str(record["node_path"]),
        op_type=str(record.get("type") or ""),
        author_str=str(record.get("author_str") or ""),
        author_id=record.get("author_id"),
        per_curiam=record.get("per_curiam"),
        joined_by_str=str(record.get("joined_by_str") or ""),
        page_count=record.get("page_count"),
        download_url=str(record.get("download_url") or ""),
        extracted_by_ocr=record.get("extracted_by_ocr"),
        sha1=str(record.get("sha1") or ""),
        body_text=select_body(record),
    )


# ---------------------------------------------------------------------------
# Decision (cluster)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedDecision:
    """One decision / opinion-cluster — the case container, plus optional
    head-matter (syllabus/headnotes/summary) text for an optional NodeVersion
    on the decision node itself."""

    cl_cluster_id: int
    path: str  # "cl-cluster-<cid>"
    court_id: str
    court_name: str
    case_name: str
    case_name_short: str
    case_name_full: str
    date_filed_raw: str
    precedential_status: str
    judges: str
    citations: tuple[str, ...]
    citation_count: int | None
    scdb_id: str
    slug: str
    docket_number: str
    syllabus: str
    headnotes: str
    summary: str
    disposition: str
    posture: str
    nature_of_suit: str

    @property
    def date_filed(self) -> dt.date | None:
        raw = (self.date_filed_raw or "")[:10]
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            return None

    @property
    def heading(self) -> str:
        return _cap_heading(
            self.case_name or self.case_name_short or self.case_name_full or self.path
        )

    @property
    def head_matter_text(self) -> str:
        parts = []
        for label, value in (
            ("Syllabus", self.syllabus),
            ("Headnotes", self.headnotes),
            ("Summary", self.summary),
        ):
            cleaned = _strip_markup(value or "")
            if cleaned:
                parts.append(f"{label}\n\n{cleaned}")
        return "\n\n".join(parts)

    @property
    def has_head_matter(self) -> bool:
        return bool(self.head_matter_text)

    @property
    def head_matter_content_hash(self) -> str:
        return _hash(self.head_matter_text)

    @property
    def source_metadata(self) -> dict:
        return {
            "cl_cluster_id": self.cl_cluster_id,
            "case_name": self.case_name,
            "case_name_short": self.case_name_short,
            "case_name_full": self.case_name_full,
            "court_id": self.court_id,
            "court_name": self.court_name,
            "date_filed": self.date_filed_raw,
            "precedential_status": self.precedential_status,
            "judges": self.judges,
            "docket_number": self.docket_number,
            "citations": list(self.citations),
            "citation_count": self.citation_count,
            "scdb_id": self.scdb_id,
            "slug": self.slug,
            "disposition": self.disposition,
            "posture": self.posture,
            "nature_of_suit": self.nature_of_suit,
        }


def parse_decision(
    record: dict[str, Any],
    *,
    docket_number: str = "",
    citations: tuple[str, ...] = (),
) -> ParsedDecision:
    return ParsedDecision(
        cl_cluster_id=int(record["cl_cluster_id"]),
        path=str(record["node_path"]),
        court_id=str(record.get("court_id") or ""),
        court_name=str(record.get("court_name") or ""),
        case_name=str(record.get("case_name") or ""),
        case_name_short=str(record.get("case_name_short") or ""),
        case_name_full=str(record.get("case_name_full") or ""),
        date_filed_raw=str(record.get("date_filed") or ""),
        precedential_status=str(record.get("precedential_status") or ""),
        judges=str(record.get("judges") or ""),
        citations=tuple(citations),
        citation_count=record.get("citation_count"),
        scdb_id=str(record.get("scdb_id") or ""),
        slug=str(record.get("slug") or ""),
        docket_number=docket_number,
        syllabus=str(record.get("syllabus") or ""),
        headnotes=str(record.get("headnotes") or ""),
        summary=str(record.get("summary") or ""),
        disposition=str(record.get("disposition") or ""),
        posture=str(record.get("posture") or ""),
        nature_of_suit=str(record.get("nature_of_suit") or ""),
    )


def format_citation(record: dict[str, Any]) -> str:
    """Build a reporter citation display string, e.g. '987 N.W.2d 123'."""
    parts = [
        str(record.get("volume") or "").strip(),
        str(record.get("reporter") or "").strip(),
        str(record.get("page") or "").strip(),
    ]
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Inline citation links (pure) — the in-text citation graph
# ---------------------------------------------------------------------------
#
# CourtListener's ``html_with_citations`` wraps every recognized citation in an
# <a> whose href is one of two forms (counts from a 20k-opinion scan):
#   /opinion/<cl_opinion_id>/<slug>/   ~97% — the case's CL opinion id (primary
#                                      resolver: cl_opinion_id -> opinion Node)
#   /c/<reporter>/<volume>/<page>/     ~1%  — a reporter cite (resolver fallback
#                                      via the ReporterCitation table)
# These links carry the in-text citation graph; ``select_body`` strips them, so
# they must be read from the RAW html before stripping. The reporter segment is
# URL-percent-encoded ("Colo.%20App."), so it is unquoted. Intra-document
# fragments (#fn..., #p...) and any other href are ignored. ``data-id`` on the
# wrapping span is deliberately NOT used — it disagrees with the href id ~64% of
# the time; the href path id is authoritative.


@dataclass(frozen=True)
class ParsedLink:
    """One inline citation hyperlink lifted from html_with_citations."""

    kind: str  # "opinion" | "reporter"
    cl_opinion_id: int | None  # set when kind == "opinion"
    reporter: str  # set when kind == "reporter"
    volume: str
    page: str
    display: str  # anchor visible text, e.g. "759 N.W.2d 3" — the external_text payload


class _LinkExtractor(HTMLParser):
    """Collect <a href> targets plus their visible text. Uses the stdlib parser
    (not a tag regex) for the same reason ``_TextExtractor`` does — a bare ``<``
    in opinion text must not be mistaken for a tag.

    Anchor text is capped at ``_MAX_DISPLAY`` chars: a malformed/unclosed ``<a>``
    would otherwise accumulate the rest of the document into one display string
    (and, downstream, into an ``external_text`` that overflows the unique
    index's btree row-size limit). The cap bounds both."""

    _OPN = re.compile(r"^/opinion/(\d+)/")
    _C = re.compile(r"^/c/([^/]+)/([^/]+)/([^/]+)/?$")
    _MAX_DISPLAY = 400

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._links: list[tuple[str, list[str]]] = []  # (href, text-parts)
        self._in_anchor = False
        self._cur_len = 0

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href is not None:
                self._links.append((href, []))
                self._in_anchor = True
                self._cur_len = 0

    def handle_data(self, data):
        if self._in_anchor and self._links and self._cur_len < self._MAX_DISPLAY:
            chunk = data[: self._MAX_DISPLAY - self._cur_len]
            self._links[-1][1].append(chunk)
            self._cur_len += len(chunk)

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_anchor = False

    def results(self) -> list[tuple[str, str]]:
        return [(href, "".join(parts).strip()) for href, parts in self._links]


def extract_citation_links(html: str) -> tuple[ParsedLink, ...]:
    """Pure: pull cited-case hyperlinks out of raw ``html_with_citations``.

    De-dupes by resolution target, preserving first-seen document order. Never
    folded into ``content_hash`` or ``source_metadata`` — links are consumed by
    the cross-reference backfill, not the version writer, so an unchanged
    opinion stays a no-op on re-ingest."""
    if not html:
        return ()
    p = _LinkExtractor()
    p.feed(html)
    p.close()
    out: list[ParsedLink] = []
    seen: set[tuple] = set()
    for href, text in p.results():
        m = _LinkExtractor._OPN.match(href)
        if m:
            oid = int(m.group(1))
            key = ("opinion", oid)
            if key in seen:
                continue
            seen.add(key)
            out.append(ParsedLink("opinion", oid, "", "", "", text))
            continue
        m = _LinkExtractor._C.match(href)
        if m:
            # All three segments are percent-decoded ("Colo.%20App." -> "Colo. App.").
            reporter = urllib.parse.unquote(m.group(1))
            volume = urllib.parse.unquote(m.group(2))
            page = urllib.parse.unquote(m.group(3))
            key = ("reporter", reporter, volume, page)
            if key in seen:
                continue
            seen.add(key)
            out.append(ParsedLink("reporter", None, reporter, volume, page, text))
            continue
        # Intra-document fragments (#...) and everything else: skip.
    return tuple(out)
