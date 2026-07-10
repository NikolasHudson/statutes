"""Iowa Administrative Code scraper.

The pipeline:

    1. Read the agency index (~85 agencies) and the current biweekly pubDate.
    2. For each agency, read its chapter list and collect the chapters that
       publish an editable chapter file.
    3. Fetch each chapter file and split it into rules. NB the site's ``.rtf``
       links are almost all actually **DOCX** (Word 2007+ / OOXML zip), so we
       extract text from ``word/document.xml`` (zipfile + ElementTree, no
       python-docx). A handful of legacy chapters (141 ch. 5/6, 261 ch. 417 as
       of 07-2026) really are RTF; those fall back to striprtf.
    4. Emit probe JSON in the shape ``ingest_iowa_admin_code`` consumes.

Politeness: reuses the Iowa Code ``Fetcher`` (global rate-limit, custom
User-Agent, on-disk cache, backoff). Parsing is a pure function of the DOCX
bytes, so it is unit-testable without the network.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Callable, Iterable

from striprtf.striprtf import rtf_to_text

from apps.ingestion_iowa_code.scraper import Fetcher

log = logging.getLogger(__name__)

AGENCIES_URL = "https://www.legis.iowa.gov/law/administrativeRules/agencies"
CHAPTERS_URL = (
    "https://www.legis.iowa.gov/law/administrativerules/chapters"
    "?agency={agency}&pubDate={pub_date}"
)
# Chapter document (editable). Despite the ``.rtf`` extension this is DOCX.
CHAPTER_DOCX_URL = (
    "https://www.legis.iowa.gov/docs/iac/chapter/{pub_date}.{agency}.{chapter}.rtf"
)
CHAPTER_PDF_URL = (
    "https://www.legis.iowa.gov/docs/iac/chapter/{pub_date}.{agency}.{chapter}.pdf"
)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Index-page regexes.
_AGENCY_NAME_RE = re.compile(r">([^<>]{2,90}?)\s*\[(\d+[A-Za-z]?)\]")
_PUBDATE_RE = re.compile(
    r"chapters\?agency=[0-9A-Za-z]+&pubDate=(\d\d-\d\d-\d{4})", re.I
)
_CHAPTER_LINK_RE = re.compile(
    r"/docs/iac/chapter/[0-9-]+\.(?P<agency>\d+[A-Za-z]?)\.(?P<chapter>\d+)\.rtf",
    re.I,
)

# Chapter-DOCX text regexes (validated against 441 ch. 1/8/65/75, 191 ch. 1).
_DASH = "[‒–—―-]"
_RULE_HEAD_RE = re.compile(
    rf"^(?P<agency>\d+[A-Za-z]?){_DASH}(?P<chap>\d+)\.(?P<rule>\d+[A-Za-z]?)"
    r"\((?P<enabling>[^)]*)\)\s*(?P<rest>.*)$"
)
_SUBRULE_RE = re.compile(r"^(?P<chap>\d+)\.(?P<rule>\d+[A-Za-z]?)\((?P<sub>\d+)\)\s")
_CHAPTER_HEAD_RE = re.compile(r"^CHAPTER\s+[0-9A-Za-z]+\s*$", re.I)
_PRIOR_RE = re.compile(r"^\[Prior to", re.I)
_EFF_RE = re.compile(r"effective\s+(\d{1,2})/(\d{1,2})/(\d{2,4})", re.I)


# ---------------------------------------------------------------------------
# Index enumeration
# ---------------------------------------------------------------------------


def current_pub_date(fetcher: Fetcher) -> str:
    """The biweekly publication date used by the live chapter links, ``MM-DD-YYYY``."""
    html = fetcher.fetch(AGENCIES_URL).decode("utf-8", errors="replace")
    dates = _PUBDATE_RE.findall(html)
    if not dates:
        raise RuntimeError("could not find a current pubDate on the agency index")
    # The live links all share one pubDate; the historical dropdown adds others.
    return max(dates, key=dates.count)


def enumerate_agencies(fetcher: Fetcher) -> list[tuple[str, str]]:
    """(agency_id, agency_name) pairs in document order, de-duped."""
    html = fetcher.fetch(AGENCIES_URL).decode("utf-8", errors="replace")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name, agency_id in _AGENCY_NAME_RE.findall(html):
        if agency_id not in seen:
            seen.add(agency_id)
            out.append((agency_id, name.strip()))
    return out


def enumerate_chapters(fetcher: Fetcher, agency: str, pub_date: str) -> list[str]:
    """Chapter numbers for ``agency`` that publish a chapter DOCX (reserved
    chapters have no link and are skipped)."""
    url = CHAPTERS_URL.format(agency=agency, pub_date=pub_date)
    html = fetcher.fetch(url).decode("utf-8", errors="replace")
    seen: set[str] = set()
    ordered: list[str] = []
    for m in _CHAPTER_LINK_RE.finditer(html):
        if m.group("agency") != agency:
            continue
        chapter = m.group("chapter")
        if chapter not in seen:
            seen.add(chapter)
            ordered.append(chapter)
    return sorted(ordered, key=int)


# ---------------------------------------------------------------------------
# DOCX/RTF text extraction + rule splitting — pure over bytes
# ---------------------------------------------------------------------------


def chapter_paragraphs(data: bytes) -> list[str]:
    """Paragraph text from a chapter download — DOCX (the norm) or legacy RTF."""
    if data[:5] == b"{\\rtf":
        return rtf_paragraphs(data)
    return docx_paragraphs(data)


def rtf_paragraphs(rtf_bytes: bytes) -> list[str]:
    # cp1252 per the files' ``\ansicpg1252``; the em dash in rule heads is a
    # raw 0x97 byte, which latin-1 would turn into a C1 control that striprtf drops.
    text = rtf_to_text(rtf_bytes.decode("cp1252", errors="replace"))
    return [line.strip() for line in text.splitlines() if line.strip()]


def docx_paragraphs(docx_bytes: bytes) -> list[str]:
    """Clean, namespace-aware paragraph text from a DOCX (word/document.xml)."""
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(docx_bytes)).read("word/document.xml"))
    out: list[str] = []
    for p in root.iter(_W + "p"):
        parts: list[str] = []
        for node in p.iter():
            if node.tag == _W + "t":
                parts.append(node.text or "")
            elif node.tag == _W + "tab":
                parts.append(" ")
            elif node.tag == _W + "br":
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            out.append(text)
    return out


def parse_chapter_docx(agency: str, chapter: str, docx_bytes: bytes, pub_date: str) -> dict:
    """Split a chapter document (DOCX or legacy RTF) into rule dicts (probe-JSON shape)."""
    paras = chapter_paragraphs(docx_bytes)

    chapter_title = ""
    prior_agencies: list[str] = []
    rules: list[dict] = []
    parse_notes: list[str] = []
    seen_numbers: set[str] = set()
    cur: dict | None = None
    expect_title = False

    for line in paras:
        if _CHAPTER_HEAD_RE.match(line):
            expect_title = True
            continue
        if expect_title:
            chapter_title = line.strip()
            expect_title = False
            continue
        if _PRIOR_RE.match(line):
            prior_agencies.append(line.strip("[]").strip())
            continue

        m = _RULE_HEAD_RE.match(line)
        if m:
            number = f"{m.group('chap')}.{m.group('rule')}"
            if number in seen_numbers and cur is not None:
                # Embedded forms re-cite their rule's number as a title block
                # (e.g. the 21—45.28 affidavit) — body text, not a new rule.
                cur["body_text"] += "\n" + line
                parse_notes.append(f"repeated head for rule {number} kept as body text")
                continue
            seen_numbers.add(number)
            heading, _, body0 = m.group("rest").partition(".")
            cur = {
                "number": number,
                "heading": heading.strip(),
                "enabling_statutes": [
                    s.strip() for s in m.group("enabling").split(",") if s.strip()
                ],
                "body_text": body0.strip(),
                "subrules": [],
                "history_brackets": [],
                "effective_from": None,
                "reserved": False,
            }
            rules.append(cur)
            continue

        sub = _SUBRULE_RE.match(line)
        if sub and cur is not None:
            cur["subrules"].append(f"{sub.group('chap')}.{sub.group('rule')}({sub.group('sub')})")
            cur["body_text"] += "\n" + line
            continue

        if line.startswith("[") and line.endswith("]"):  # history / effective bracket
            if cur is not None:
                cur["history_brackets"].append(line)
                eff = _EFF_RE.search(line)
                if eff:
                    iso = _to_iso(*eff.groups())
                    # Keep the most recent effective date across a rule's brackets.
                    if iso and (cur["effective_from"] is None or iso > cur["effective_from"]):
                        cur["effective_from"] = iso
            continue

        if cur is not None:  # continuation body (definitions, prose)
            cur["body_text"] += "\n" + line

    return {
        "chapter": chapter,
        "chapter_title": chapter_title,
        "reserved": False,
        "chapter_docx_url": CHAPTER_DOCX_URL.format(pub_date=pub_date, agency=agency, chapter=chapter),
        "chapter_pdf_url": CHAPTER_PDF_URL.format(pub_date=pub_date, agency=agency, chapter=chapter),
        "prior_agencies": prior_agencies,
        "parse_notes": parse_notes if rules else parse_notes + ["no rules parsed from DOCX"],
        "rules": rules,
    }


def _to_iso(mm: str, dd: str, yy: str) -> str | None:
    if len(yy) == 2:  # pivot: the IAC predates 2000, has nothing near 2050
        yy = ("19" if int(yy) >= 50 else "20") + yy
    try:
        return dt.date(int(yy), int(mm), int(dd)).isoformat()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def scrape_iowa_admin_code(
    *,
    cache_dir: Path,
    pub_date: str | None = None,
    only_agencies: Iterable[str] | None = None,
    rate_limit_seconds: float = 1.0,
    progress: Callable | None = None,
) -> dict:
    """Top-level scrape: enumerate → fetch → parse → probe-JSON dict.

    ``progress`` is ``(agency, chapter, kind, detail) -> None`` for live output."""
    fetcher = Fetcher(cache_dir=cache_dir, rate_limit_seconds=rate_limit_seconds)

    pub_date = pub_date or current_pub_date(fetcher)
    pub_iso = _pubdate_iso(pub_date)

    wanted = set(only_agencies) if only_agencies is not None else None
    agencies_index = [
        (aid, name) for aid, name in enumerate_agencies(fetcher)
        if wanted is None or aid in wanted
    ]

    agencies_out: list[dict] = []
    failures: list[dict] = []
    for aid, name in agencies_index:
        chapters_out: list[dict] = []
        try:
            chapter_nums = enumerate_chapters(fetcher, aid, pub_date)
        except Exception as e:  # noqa: BLE001 — record + continue
            failures.append({"agency": aid, "stage": "chapter_list", "error": str(e)})
            if progress:
                progress(aid, None, "agency_failed", str(e))
            continue

        for chapter in chapter_nums:
            url = CHAPTER_DOCX_URL.format(pub_date=pub_date, agency=aid, chapter=chapter)
            try:
                docx_bytes = fetcher.fetch(url)
                parsed = parse_chapter_docx(aid, chapter, docx_bytes, pub_date)
                chapters_out.append(parsed)
                if progress:
                    progress(aid, chapter, "chapter_ok", f"{len(parsed['rules'])} rules")
            except Exception as e:  # noqa: BLE001
                failures.append({"agency": aid, "chapter": chapter, "url": url, "error": str(e)})
                if progress:
                    progress(aid, chapter, "chapter_failed", str(e))

        agencies_out.append({"agency": aid, "agency_name": name, "chapters": chapters_out})

    return {
        "pub_date": pub_iso,
        "pub_date_url": pub_date,
        "source_base_url": CHAPTER_DOCX_URL,
        "agencies": agencies_out,
        "summary": {
            "agencies_scraped": len(agencies_out),
            "chapters_scraped": sum(len(a["chapters"]) for a in agencies_out),
            "rules_scraped": sum(len(c["rules"]) for a in agencies_out for c in a["chapters"]),
            "failures": len(failures),
        },
        "failures": failures,
    }


def _pubdate_iso(pub_date: str) -> str:
    """``MM-DD-YYYY`` → ISO ``YYYY-MM-DD``."""
    mm, dd, yy = pub_date.split("-")
    return dt.date(int(yy), int(mm), int(dd)).isoformat()
