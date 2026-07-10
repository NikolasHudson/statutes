"""Iowa Acts (session laws) scraper.

The pipeline per session:

    1. ``actsChapter?ssid=N`` — the chapter listing. Each row carries the
       chapter number, the enrolled bill (``BillBook?ba=SF2385&ga=90``), the
       GA + session (from the chapter-PDF path ``iactc/{ga}.{session}/``),
       and the title.
    2. The enrolled bill RTF ``LGE/{ga}/attachments/{BILL}.rtf`` — the parse
       target (strike-aware; see rtf.py). Verified present GA 83+ (2009+).
    3. ``acts/amended?ga={ga}&session={s}`` — the legislature's own
       Code-sections-amended table (Reference | Action | Bill/Section |
       Eff Date | App Date | Gov's Action | Gov's Action Date). This is the
       authoritative act→Code edge channel; the parser's lead-in extraction
       is the localizing channel. Verified back to GA 84 (2011).

Emits probe JSON in the shape ``ingest_iowa_acts`` consumes. Politeness:
reuses the Iowa Code ``Fetcher`` (rate-limit, UA, on-disk cache, backoff).
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from html.parser import HTMLParser

from apps.ingestion_iowa_code.scraper import Fetcher

from .parser import parse_enrolled_rtf

log = logging.getLogger(__name__)

BASE = "https://www.legis.iowa.gov"
LISTING_URL = BASE + "/law/statutory/acts/actsChapter?ssid={ssid}"
ENROLLED_RTF_URL = BASE + "/docs/publications/LGE/{ga}/attachments/{bill}.rtf"
AMENDED_URL = BASE + "/law/statutory/acts/amended?ga={ga}&session={session}"

# Session dropdown entries: ssid=166">General Assembly: 90 (2024 Regular GA)
_SSID_RE = re.compile(
    r"ssid=(?P<ssid>\d+)\"[^>]*>General Assembly:\s*(?P<ga>\d+)\s*"
    r"\((?P<year>\d{4})\s*(?P<label>[^)]*)\)"
)

# Listing row: chapter PDF href carries ga.session + zero-padded chapter;
# the BillBook link carries the bill.
_ROW_RE = re.compile(
    r"/docs/publications/iactc/(?P<ga>\d+)\.(?P<session>\d+)/CH(?P<chapter>\d{4})\.pdf"
    r".{0,400}?BillBook\?ba=(?P<bill>[A-Z]{2,4}\d+)&ga=\d+",
    re.S,
)
_TITLE_RE = re.compile(
    r'<td class="left" sorttable_customkey="(?P<title>[^"]{3,})">'
)


def enumerate_sessions(fetcher: Fetcher) -> list[dict]:
    """All sessions from the dropdown on any listing page, newest first.
    ``[{"ssid": 166, "ga": 90, "year": 2024, "label": "Regular GA"}, …]``"""
    html = fetcher.fetch(LISTING_URL.format(ssid=168)).decode("utf-8", "replace")
    out, seen = [], set()
    for m in _SSID_RE.finditer(html):
        ssid = int(m["ssid"])
        if ssid in seen:
            continue
        seen.add(ssid)
        out.append(
            {
                "ssid": ssid,
                "ga": int(m["ga"]),
                "year": int(m["year"]),
                "label": m["label"].strip(),
            }
        )
    return out


def session_chapters(fetcher: Fetcher, ssid: int) -> list[dict]:
    """Chapter rows for one session: number, bill, ga, session, title."""
    html = fetcher.fetch(LISTING_URL.format(ssid=ssid)).decode("utf-8", "replace")
    rows = []
    row_matches = list(_ROW_RE.finditer(html))
    for m in row_matches:
        # The title cell follows the row's bill link; search a bounded window.
        window = html[m.end() : m.end() + 800]
        tm = _TITLE_RE.search(window)
        rows.append(
            {
                "chapter": int(m["chapter"]),
                "bill": m["bill"],
                "ga": int(m["ga"]),
                "session": int(m["session"]),
                "title": tm["title"].strip() if tm else "",
            }
        )
    return rows


class _AmendedTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []
        self._in_td = False

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._in_td, self._cell = True, []
        elif tag == "tr":
            self._row = []

    def handle_endtag(self, tag):
        if tag == "td":
            self._in_td = False
            self._row.append(" ".join("".join(self._cell).split()))
        elif tag == "tr" and self._row:
            self.rows.append(self._row)

    def handle_data(self, data):
        if self._in_td:
            self._cell.append(data)


_REF_RE = re.compile(
    r"^(?:(?P<code_year>\d{4}) Code|(?P<new>New Code))\s*-\s*"
    r"(?P<chapter_only>Ch\.\s*)?(?P<ref>[0-9A-Z.]+)"
    r"\s*(?P<subunit>\([^)]*\).*)?$"
)
_BILL_SEC_RE = re.compile(
    r"^(?P<bill>[A-Z]{2,4}\s*\d+)\s*(?:,\s*§(?P<section>[\d,\s–—-]+))?"
)


def amended_table(fetcher: Fetcher, ga: int, session: int) -> list[dict]:
    """The official act→Code edge table for one session, normalized.

    One dict per row: code_ref (dotted section or chapter token), code_year
    (None for "New Code" rows), subunit (verbatim parenthetical tail or ""),
    action, bill, bill_sections (list of ints where parseable), eff_date,
    gov_action, gov_date. Unparseable references are kept verbatim under
    ``raw_ref`` with code_ref=None rather than dropped.
    """
    html = fetcher.fetch(AMENDED_URL.format(ga=ga, session=session)).decode(
        "utf-8", "replace"
    )
    p = _AmendedTableParser()
    p.feed(html)
    out = []
    for row in p.rows:
        if len(row) < 7:
            continue
        ref_raw, action, bill_sec, eff, app, gov, gov_date = row[:7]
        rm = _REF_RE.match(ref_raw)
        bm = _BILL_SEC_RE.match(bill_sec)
        sections: list[int] = []
        if bm and bm["section"]:
            sections = [int(x) for x in re.findall(r"\d+", bm["section"])]
        out.append(
            {
                "code_ref": rm["ref"] if rm else None,
                "code_year": rm["code_year"] if rm else None,
                "new_code": bool(rm and rm["new"]),
                "chapter_only": bool(rm and rm["chapter_only"]),
                "subunit": (rm["subunit"] or "").strip() if rm else "",
                "raw_ref": ref_raw,
                "action": action,
                "bill": bm["bill"].replace(" ", "") if bm else bill_sec,
                "bill_sections": sections,
                "eff_date": eff or None,
                "app_date": app or None,
                "gov_action": gov,
                "gov_date": gov_date or None,
            }
        )
    return out


def scrape_session(fetcher: Fetcher, ssid: int) -> dict:
    """Everything ``ingest_iowa_acts`` needs for one session, as JSON-ready
    dicts: session meta, chapters with parsed sections, and the amended
    table. Chapters whose enrolled RTF is missing (pre-GA-83 sessions) are
    listed with ``"enrolled_rtf": false`` and no sections — the PDF fallback
    is future work, tracked in the plan."""
    chapters = session_chapters(fetcher, ssid)
    if not chapters:
        # Zero rows usually means a rate-limit/error page got cached, not an
        # empty session — evict that one entry and refetch before giving up.
        from apps.ingestion_iowa_code.scraper import _url_hash

        (fetcher.cache_dir / f"{_url_hash(LISTING_URL.format(ssid=ssid))}.bin").unlink(
            missing_ok=True
        )
        chapters = session_chapters(fetcher, ssid)
    if not chapters:
        raise ValueError(f"no chapters found for ssid={ssid}")
    ga, session = chapters[0]["ga"], chapters[0]["session"]

    out_chapters = []
    for ch in chapters:
        url = ENROLLED_RTF_URL.format(ga=ga, bill=ch["bill"])
        try:
            data = fetcher.fetch(url)
        except Exception as e:  # 404s on pre-RTF sessions
            log.warning("no enrolled RTF for %s GA %s: %s", ch["bill"], ga, e)
            out_chapters.append({**ch, "enrolled_rtf": False, "sections": []})
            continue
        act = parse_enrolled_rtf(data)
        out_chapters.append(
            {
                **ch,
                "enrolled_rtf": True,
                "act_title": act.title,
                "sections": [asdict(s) for s in act.sections],
            }
        )

    return {
        "ssid": ssid,
        "ga": ga,
        "session": session,
        "chapters": out_chapters,
        "amended": amended_table(fetcher, ga, session),
    }
