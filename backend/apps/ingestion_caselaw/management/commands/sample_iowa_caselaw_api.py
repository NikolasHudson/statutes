"""Pull a small Iowa caselaw sample from the CourtListener API into the same
JSONL artifacts the bulk ``acquire`` produces — so the existing
``ingest_iowa_caselaw`` consumes it unchanged.

This is for a smoke test (and the seed of the ongoing-update path); the full
historical backfill uses the bulk CSVs. Token comes from --token,
COURTLISTENER_TOKEN in the environment, or backend/.env.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ...cl_api import CLClient

_SLUG_RE = re.compile(r"/opinion/\d+/([^/]+)/?")


def _token_from_env_file() -> str:
    env = Path(settings.BASE_DIR) / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("COURTLISTENER_TOKEN="):
                return line.split("=", 1)[1].strip()
    return ""


def _joined(value) -> str:
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v)
    return str(value or "")


def _slug(absolute_url: str) -> str:
    m = _SLUG_RE.search(absolute_url or "")
    return m.group(1) if m else ""


def _split_citation(cite: str) -> tuple[str, str, str]:
    """'987 N.W.2d 123' -> ('987', 'N.W.2d', '123'); best-effort."""
    toks = cite.split()
    if len(toks) >= 3:
        return toks[0], " ".join(toks[1:-1]), toks[-1]
    if len(toks) == 2:
        return toks[0], toks[1], ""
    return "", cite, ""


class Command(BaseCommand):
    help = "Sample Iowa caselaw from the CourtListener API into JSONL artifacts."

    def add_arguments(self, parser):
        parser.add_argument("--out-dir", required=True)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--court", default="iowa",
                            help="CourtListener court id (default: iowa).")
        parser.add_argument("--order-by", default="dateFiled desc")
        parser.add_argument("--token", default=None)

    def handle(self, *args, **opts):
        token = (opts["token"] or os.environ.get("COURTLISTENER_TOKEN")
                 or _token_from_env_file())
        if not token:
            raise CommandError("no token (--token / COURTLISTENER_TOKEN / .env)")

        out = Path(opts["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        client = CLClient(token)

        self.stdout.write(f"searching {opts['court']} (limit {opts['limit']})…")
        clusters = client.search_clusters(
            opts["court"], limit=opts["limit"], order_by=opts["order_by"]
        )

        cl_f = (out / "clusters.jsonl").open("w", encoding="utf-8")
        op_f = (out / "opinions.jsonl").open("w", encoding="utf-8")
        ci_f = (out / "citations.jsonl").open("w", encoding="utf-8")
        dk_f = (out / "dockets.jsonl").open("w", encoding="utf-8")
        counts = {"clusters": 0, "opinions": 0, "citations": 0, "dockets": 0}
        seen_dockets: set[int] = set()
        cite_id = 0

        def w(fh, rec):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        try:
            for r in clusters:
                cid = r["cluster_id"]
                w(cl_f, {
                    "cl_cluster_id": cid,
                    "node_path": f"cl-cluster-{cid}",
                    "docket_id": r.get("docket_id"),
                    "court_id": r.get("court_id") or "",
                    "court_name": r.get("court") or "",
                    "case_name": r.get("caseName") or "",
                    "case_name_short": r.get("caseName") or "",
                    "case_name_full": r.get("caseNameFull") or "",
                    "date_filed": (r.get("dateFiled") or "")[:10],
                    "precedential_status": r.get("status") or "",
                    "judges": _joined(r.get("judge")),
                    "citation_count": r.get("citeCount"),
                    "scdb_id": r.get("scdb_id") or "",
                    "slug": _slug(r.get("absolute_url")),
                    "syllabus": r.get("syllabus") or "",
                    "headnotes": "",
                    "summary": "",
                    "disposition": "",
                    "posture": r.get("posture") or "",
                    "nature_of_suit": r.get("suitNature") or "",
                })
                counts["clusters"] += 1

                did = r.get("docket_id")
                if did is not None and did not in seen_dockets:
                    seen_dockets.add(did)
                    w(dk_f, {"docket_id": did, "court_id": r.get("court_id") or "",
                             "docket_number": r.get("docketNumber") or ""})
                    counts["dockets"] += 1

                for cite in (r.get("citation") or []):
                    vol, rep, pg = _split_citation(str(cite))
                    cite_id += 1
                    w(ci_f, {"cl_citation_id": cite_id, "cl_cluster_id": cid,
                             "volume": vol, "reporter": rep, "page": pg, "type": None})
                    counts["citations"] += 1

                for o in client.opinions_for_cluster(cid):
                    w(op_f, {
                        "cl_opinion_id": o["id"],
                        "cl_cluster_id": cid,
                        "node_path": f"cl-cluster-{cid}/op-{o['id']}",
                        "type": o.get("type") or "",
                        "author_str": o.get("author_str") or "",
                        "author_id": o.get("author_id"),
                        "per_curiam": o.get("per_curiam"),
                        "joined_by_str": o.get("joined_by_str") or "",
                        "page_count": o.get("page_count"),
                        "download_url": o.get("download_url") or "",
                        "extracted_by_ocr": o.get("extracted_by_ocr"),
                        "sha1": o.get("sha1") or "",
                        "plain_text": o.get("plain_text") or "",
                        "html": o.get("html") or "",
                        "html_lawbox": o.get("html_lawbox") or "",
                        "html_columbia": o.get("html_columbia") or "",
                        "html_anon_2020": o.get("html_anon_2020") or "",
                        "xml_harvard": o.get("xml_harvard") or "",
                        "html_with_citations": o.get("html_with_citations") or "",
                    })
                    counts["opinions"] += 1
        finally:
            for fh in (cl_f, op_f, ci_f, dk_f):
                fh.close()

        self.stdout.write(self.style.SUCCESS("sample written:"))
        self.stdout.write(json.dumps(counts, indent=2))
