"""CourtListener ``html_with_citations`` → structured display segments.

Pure (no DB): turns an opinion's rich HTML into a list of block dicts the
frontend renders directly (no raw-HTML injection, so no XSS surface). This is a
DISPLAY-ONLY representation; the canonical ``NodeVersion.body_text`` stays the
stripped plain text used for FTS / content_hash / embeddings.

Block shape::

    {"k": "byline"|"p"|"quote"|"fn", "runs": [run, ...]}

Run shape (one of)::

    {"t": "plain text", "em"?: true, "cl"?: <cited cl_opinion_id>}
    {"star": "*810"}        # West star-pagination page break
    {"sup": "1"}            # footnote mark

``cl`` is the cited opinion's CourtListener id (from ``/opinion/<id>/`` links);
a later pass resolves it to a corpus decision node id (``case``).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_CITE_HREF = re.compile(r"^/opinion/(\d+)/")
_BLOCK_TAGS = {"p", "blockquote", "author", "footnote"}
_KIND = {"p": "p", "blockquote": "quote", "author": "byline", "footnote": "fn"}


class _OpinionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self._cur: dict | None = None
        self._em = 0
        self._cl: int | None = None
        self._in_pagenum = False
        self._pagenum = ""
        self._in_mark = False
        self._fn_depth = 0

    def _open(self, kind: str) -> None:
        self._close()
        self._cur = {"k": kind, "runs": []}

    def _close(self) -> None:
        if self._cur is not None:
            runs = _merge(self._cur["runs"])
            # Collapse HTML formatting whitespace (newlines + indentation between
            # tags). Without this, a pretty-printed "<p>\n  I. Background.\n </p>"
            # yields run text "\n  I. Background." and the client's ^-anchored
            # heading detection misses it. HTML treats any whitespace run as a
            # single space anyway.
            for r in runs:
                if "t" in r:
                    r["t"] = re.sub(r"\s+", " ", r["t"])
            text_runs = [r for r in runs if "t" in r]
            if text_runs:
                text_runs[0]["t"] = text_runs[0]["t"].lstrip()
                text_runs[-1]["t"] = text_runs[-1]["t"].rstrip()
            runs = [r for r in runs if "t" not in r or r["t"] != ""]
            if any(r.get("t", "").strip() or "star" in r or "sup" in r for r in runs):
                self._cur["runs"] = runs
                self.blocks.append(self._cur)
        self._cur = None

    def handle_starttag(self, tag, attrs):
        if tag == "footnote":
            self._fn_depth += 1
            self._open("fn")
            self._cur["mark"] = dict(attrs).get("label", "")
        elif tag in ("p", "blockquote", "author"):
            # paragraphs nested inside a footnote stay part of the footnote
            if self._fn_depth == 0:
                self._open(_KIND[tag])
        elif tag in ("em", "i"):
            self._em += 1
        elif tag == "a":
            m = _CITE_HREF.match(dict(attrs).get("href", ""))
            self._cl = int(m.group(1)) if m else None
        elif tag == "page-number":
            self._in_pagenum = True
            self._pagenum = ""
        elif tag == "footnotemark":
            self._in_mark = True

    def handle_endtag(self, tag):
        if tag == "footnote":
            self._fn_depth = max(0, self._fn_depth - 1)
            self._close()
        elif tag in ("p", "blockquote", "author"):
            if self._fn_depth == 0:
                self._close()
        elif tag in ("em", "i"):
            self._em = max(0, self._em - 1)
        elif tag == "a":
            self._cl = None
        elif tag == "page-number":
            self._in_pagenum = False
            if self._pagenum.strip() and self._cur is not None:
                self._cur["runs"].append({"star": self._pagenum.strip()})
        elif tag == "footnotemark":
            self._in_mark = False

    def handle_data(self, data):
        if self._in_pagenum:
            self._pagenum += data
            return
        if self._cur is None:
            self._open("p")
        if self._in_mark:
            mark = data.strip()
            if mark:
                self._cur["runs"].append({"sup": mark})
            return
        run: dict = {"t": data}
        if self._em > 0:
            run["em"] = True
        if self._cl is not None:
            run["cl"] = self._cl
        self._cur["runs"].append(run)


def _merge(runs: list[dict]) -> list[dict]:
    """Coalesce adjacent plain-text runs that share styling, so the output is
    compact (the parser emits a run per data chunk)."""
    out: list[dict] = []
    for r in runs:
        last = out[-1] if out else None
        if (
            last is not None
            and "t" in last
            and "t" in r
            and last.get("em") == r.get("em")
            and last.get("cl") == r.get("cl")
        ):
            last["t"] += r["t"]
        else:
            out.append(dict(r))
    return out


def html_to_blocks(html: str) -> list[dict]:
    p = _OpinionParser()
    p.feed(html or "")
    p._close()
    return p.blocks
