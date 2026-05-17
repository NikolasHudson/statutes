"""Iowa Code RTF scraper.

The pipeline:

    1. Walk the 16 Title index pages on legis.iowa.gov and extract every
       chapter slug (e.g. "1", "12C", "455B").
    2. Fetch each chapter's RTF, cache the raw bytes locally so re-runs are
       cheap and the data is auditable.
    3. Strip RTF to text and slice into sections via the same regex shape
       the original probe used (proven on chapters 1, 4, 12C, 29C, 97B,
       232, 257, 455B, 600, 709, 902).
    4. Emit a JSON document in the shape ``ingest_iowa_code`` already knows
       how to consume.

Politeness: a single global rate-limit gates network requests. A custom
User-Agent identifies the scraper. Failures are recorded but don't stop
the run; they show up in the output summary so we can re-run just the
failing chapters.

Pure where possible: parsing is a pure function of the RTF bytes, so the
section-extraction logic is unit-testable without hitting the network.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from striprtf.striprtf import rtf_to_text


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


TITLE_NUMERALS = (
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII",
    "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
)

TITLE_INDEX_URL = (
    "https://www.legis.iowa.gov/law/iowaCode/chapters?title={title}&year={year}"
)
CHAPTER_RTF_URL = "https://www.legis.iowa.gov/docs/code/{year}/{slug}.rtf"
CHAPTER_PDF_URL = "https://www.legis.iowa.gov/docs/code/{year}/{slug}.pdf"
CHAPTER_HTML_URL = "https://www.legis.iowa.gov/docs/code/{year}/{slug}.html"
SECTION_PDF_URL = "https://www.legis.iowa.gov/docs/ico/section/{year}/{slug}.pdf"
SECTION_HTML_URL = "https://www.legis.iowa.gov/docs/ico/section/{year}/{slug}.html"
SECTION_RTF_URL = "https://www.legis.iowa.gov/docs/ico/section/{year}/{slug}.rtf"

DEFAULT_USER_AGENT = (
    "iowa-corpus-scraper/0.1 (Iowa Legal Corpus project; nick@nickhudson.me)"
)

# Slug pattern: digits, optional letter suffix. Covers "1", "12C", "455B".
_CHAPTER_SLUG_RE = re.compile(r"^\d+[A-Z]?$")
_CHAPTER_RTF_LINK_RE = re.compile(
    r"/docs/code/\d+/(?P<slug>\d+[A-Z]?)\.rtf", re.IGNORECASE
)

# Section regexes — same as the probe. See probe_iowa_rtf.py for provenance.
_CHAPTER_HEAD_RE = re.compile(r"CHAPTER\s+([0-9]+[A-Z]*)\s*\n\s*([^\n]+)")
_SECTION_HEAD_RE = re.compile(
    r"^(?P<num>\d+[A-Z]*\.\d+[A-Z]*)\s{1,3}(?P<heading>[^\n]+?)\.\s*$",
    re.MULTILINE,
)
_HISTORY_RE = re.compile(r"\[([^\]]+)\]")
_ACTS_RE = re.compile(
    r"\b(\d{4})\s+Acts?,\s*ch\s*\d+[A-Z]?(?:,\s*§[0-9A-Z\-,\s]+)?"
)
_XREF_RE = re.compile(r"Referred to in\s+([§0-9A-Z\.,\s\-]+?)(?=\n|$)")


# ---------------------------------------------------------------------------
# Data classes — match the probe-JSON shape consumed by parser.parse_probe_json
# ---------------------------------------------------------------------------


@dataclass
class ScrapedSection:
    number: str
    heading: str
    body_text: str
    history_brackets: list[str]
    acts_citations: list[str]
    referred_to_in: list[str]
    citation_pdf_url: str
    citation_html_url: str
    source_rtf_url: str

    @property
    def body_chars(self) -> int:
        return len(self.body_text)

    def to_json(self) -> dict:
        d = dataclasses.asdict(self)
        d["body_chars"] = self.body_chars
        return d


@dataclass
class ScrapedChapter:
    chapter: str
    chapter_title: str
    url: str  # chapter HTML URL
    citation_pdf_url: str
    citation_html_url: str
    source_rtf_url: str
    rtf_bytes: int
    text_chars: int
    sections: list[ScrapedSection] = field(default_factory=list)

    @property
    def section_count(self) -> int:
        return len(self.sections)

    def to_json(self) -> dict:
        return {
            "chapter": self.chapter,
            "chapter_title": self.chapter_title,
            "rtf_bytes": self.rtf_bytes,
            "text_chars": self.text_chars,
            "section_count": self.section_count,
            "sections": [s.to_json() for s in self.sections],
            "url": self.url,
            "citation_html_url": self.citation_html_url,
            "citation_pdf_url": self.citation_pdf_url,
            "source_rtf_url": self.source_rtf_url,
        }


@dataclass
class ScrapeResult:
    code_year: int
    chapters: list[ScrapedChapter] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        total_sections = sum(c.section_count for c in self.chapters)
        return {
            "code_year": self.code_year,
            "source_base_url": CHAPTER_RTF_URL,
            "samples": [c.to_json() for c in self.chapters],
            "summary": {
                "chapters_scraped": len(self.chapters),
                "chapters_failed": len(self.failures),
                "total_sections": total_sections,
            },
            "failures": self.failures,
        }


# ---------------------------------------------------------------------------
# HTTP layer with rate limiting + caching
# ---------------------------------------------------------------------------


@dataclass
class Fetcher:
    """Polite HTTP fetcher with on-disk caching.

    Cache key is sha256 of the URL; raw bytes land in ``cache_dir/<sha>.bin``.
    Re-runs reuse the cache transparently — the network is touched only for
    URLs not yet seen. Set ``force_refresh=True`` to bypass the cache."""

    cache_dir: Path
    user_agent: str = DEFAULT_USER_AGENT
    rate_limit_seconds: float = 1.0
    timeout_seconds: float = 30.0
    max_retries: int = 3
    force_refresh: bool = False
    _last_request_at: float = 0.0

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, url: str) -> bytes:
        cache_path = self.cache_dir / f"{_url_hash(url)}.bin"
        if not self.force_refresh and cache_path.exists():
            return cache_path.read_bytes()

        self._throttle()
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as r:
                    body = r.read()
                cache_path.write_bytes(body)
                return body
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                # Exponential backoff: 1s, 2s, 4s
                wait = 2 ** (attempt - 1)
                log.warning(
                    "fetch %s attempt %d/%d failed: %s — sleeping %ss",
                    url, attempt, self.max_retries, e, wait,
                )
                time.sleep(wait)
        assert last_err is not None
        raise last_err

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_at = time.monotonic()


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Title-page enumeration
# ---------------------------------------------------------------------------


def enumerate_chapter_slugs(
    fetcher: Fetcher, *, year: int, titles: Iterable[str] = TITLE_NUMERALS,
) -> list[str]:
    """Walk the 16 Title index pages and return every distinct chapter slug
    in document order. Iowa publishes some chapters under multiple Titles
    (rare); we de-dupe on first appearance."""
    seen: set[str] = set()
    ordered: list[str] = []
    for title in titles:
        url = TITLE_INDEX_URL.format(title=title, year=year)
        log.info("enumerating Title %s", title)
        html = fetcher.fetch(url).decode("utf-8", errors="replace")
        for m in _CHAPTER_RTF_LINK_RE.finditer(html):
            slug = m.group("slug")
            if slug not in seen and _CHAPTER_SLUG_RE.match(slug):
                seen.add(slug)
                ordered.append(slug)
    return ordered


# ---------------------------------------------------------------------------
# Chapter-RTF parsing — pure function over RTF bytes
# ---------------------------------------------------------------------------


def parse_chapter_rtf(slug: str, rtf_bytes: bytes, *, year: int) -> ScrapedChapter:
    """Strip the RTF and slice into sections. Pure: no I/O."""
    text = rtf_to_text(
        rtf_bytes.decode("latin-1", errors="replace"), errors="ignore"
    )

    chap_match = _CHAPTER_HEAD_RE.search(text)
    chapter_num = chap_match.group(1) if chap_match else slug
    chapter_title = chap_match.group(2).strip() if chap_match else ""

    sections = list(_extract_sections(text, year=year))

    return ScrapedChapter(
        chapter=chapter_num,
        chapter_title=chapter_title,
        url=CHAPTER_HTML_URL.format(year=year, slug=slug),
        citation_html_url=CHAPTER_HTML_URL.format(year=year, slug=slug),
        citation_pdf_url=CHAPTER_PDF_URL.format(year=year, slug=slug),
        source_rtf_url=CHAPTER_RTF_URL.format(year=year, slug=slug),
        rtf_bytes=len(rtf_bytes),
        text_chars=len(text),
        sections=sections,
    )


def _extract_sections(text: str, *, year: int) -> Iterator[ScrapedSection]:
    matches = list(_SECTION_HEAD_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()

        history = _HISTORY_RE.findall(body)
        acts = [a.group(0) for a in _ACTS_RE.finditer(body)]
        xrefs_raw = _XREF_RE.findall(body)
        xrefs: list[str] = []
        for chunk in xrefs_raw:
            for piece in re.split(r"[,;]", chunk):
                p = piece.strip().lstrip("§").strip()
                if p:
                    xrefs.append(p)

        operative = body
        for pat in (_HISTORY_RE, _ACTS_RE, _XREF_RE):
            operative = pat.sub("", operative)
        operative = re.sub(r"\n\s*\n+", "\n\n", operative).strip()

        section_slug = m.group("num")
        yield ScrapedSection(
            number=section_slug,
            heading=m.group("heading").strip(),
            body_text=operative,
            history_brackets=history,
            acts_citations=acts,
            referred_to_in=xrefs,
            citation_pdf_url=SECTION_PDF_URL.format(year=year, slug=section_slug),
            citation_html_url=SECTION_HTML_URL.format(year=year, slug=section_slug),
            source_rtf_url=SECTION_RTF_URL.format(year=year, slug=section_slug),
        )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def scrape_iowa_code(
    *,
    year: int,
    cache_dir: Path,
    titles: Iterable[str] = TITLE_NUMERALS,
    rate_limit_seconds: float = 1.0,
    user_agent: str = DEFAULT_USER_AGENT,
    only_slugs: Iterable[str] | None = None,
    progress: callable | None = None,
) -> ScrapeResult:
    """Top-level scrape: enumerate, fetch, parse, return structured result.

    ``progress`` is a callback ``(slug, idx, total, ScrapedChapter | None,
    error_str | None) -> None`` — used by the management command for live
    output. Pass None to run silently.
    """
    fetcher = Fetcher(
        cache_dir=cache_dir,
        rate_limit_seconds=rate_limit_seconds,
        user_agent=user_agent,
    )

    if only_slugs is not None:
        slugs = list(only_slugs)
    else:
        slugs = enumerate_chapter_slugs(fetcher, year=year, titles=titles)

    result = ScrapeResult(code_year=year)
    total = len(slugs)
    for idx, slug in enumerate(slugs, start=1):
        url = CHAPTER_RTF_URL.format(year=year, slug=slug)
        try:
            rtf = fetcher.fetch(url)
            chapter = parse_chapter_rtf(slug, rtf, year=year)
            result.chapters.append(chapter)
            if progress:
                progress(slug, idx, total, chapter, None)
        except Exception as e:  # noqa: BLE001 — record + continue
            result.failures.append({"slug": slug, "url": url, "error": str(e)})
            if progress:
                progress(slug, idx, total, None, str(e))
    return result
