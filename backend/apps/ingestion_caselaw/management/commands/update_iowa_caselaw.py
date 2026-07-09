"""Phase 5 — ongoing incremental updates from the CourtListener REST API.

Sweeps clusters/opinions/dockets ADDED to CourtListener (``date_created``, not
``date_filed`` — CL harvests cases late, so a filed-date cursor would skip
them forever) since the last successful update run, writes them as the same
four JSONL artifacts the bulk acquire produces, and (unless ``--fetch-only``)
runs the standard downstream chain over the slice:

    ingest_iowa_caselaw → load_case_citations → build_caselaw_display
    → backfill_caselaw_cross_references → chunk_caselaw → embed_chunks

Every leg is idempotent, so the sweep deliberately overlaps the previous run
(``--overlap-days``); re-seen unchanged records are no-ops. The cursor stored
on the run is the RUN START time (not the max ``date_created`` seen): the
sweeps cover everything CL had committed by then, and a quiet week must still
advance the cursor. The cursor only advances when the whole pipeline
succeeds, so a failed run is re-covered by the next one.

Reporter citations: fresh opinions carry none (N.W.2d/3d numbers arrive months
later), and the v4 API inlines a cluster's citations WITHOUT their bulk-table
ids. Any that do appear are written with a stable NEGATIVE synthetic
``cl_citation_id`` (never colliding with the real, positive bulk ids); the
quarterly bulk reload reconciles the real rows. Depth-weighted citation-graph
edges (``build_caselaw_citation_graph``) also remain bulk-only — new cases
still get day-one inline-link edges via the cross-reference backfill.

Budget: the default token allows 5 req/min, 50/hr, 125/day. A normal daily run
is ~6–10 requests; a multi-month catch-up run is throttled by the client's
429 backoff and just takes longer.

    python manage.py update_iowa_caselaw --out-dir /home/dev/cl-updates
    python manage.py update_iowa_caselaw --out-dir ... --since 2026-06-01
    python manage.py update_iowa_caselaw --out-dir ... --fetch-only
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ...cl_api import CLClient
from ...models import IngestionRun
from .sample_iowa_caselaw_api import _token_from_env_file

# court id → display name, matching the bulk courts.csv values already stored
# in decision source_metadata (a mismatch would dirty-update every node on
# each overlap re-ingest).
COURTS = {
    "iowa": "Supreme Court of Iowa",
    "iowactapp": "Court of Appeals of Iowa",
}

_OPINION_TEXT_FIELDS = (
    "plain_text", "html", "html_lawbox", "html_columbia", "html_anon_2020",
    "xml_harvard", "html_with_citations",
)

# Synthetic reporter-citation ids: -(cluster_id * 100 + index). Negative so
# they can never collide with CL's real bulk citation ids, stable so re-runs
# upsert instead of duplicating.
_MAX_CITES_PER_CLUSTER = 100


def _cluster_record(c: dict, court_id: str, court_name: str) -> dict:
    cid = c["id"]
    return {
        "cl_cluster_id": cid,
        "node_path": f"cl-cluster-{cid}",
        "docket_id": c.get("docket_id"),
        "court_id": court_id,
        "court_name": court_name,
        "case_name": c.get("case_name") or "",
        "case_name_short": c.get("case_name_short") or "",
        "case_name_full": c.get("case_name_full") or "",
        "date_filed": (c.get("date_filed") or "")[:10],
        "precedential_status": c.get("precedential_status") or "",
        "judges": c.get("judges") or "",
        "citation_count": c.get("citation_count"),
        "scdb_id": c.get("scdb_id") or "",
        "slug": c.get("slug") or "",
        "syllabus": c.get("syllabus") or "",
        "headnotes": c.get("headnotes") or "",
        "summary": c.get("summary") or "",
        "disposition": c.get("disposition") or "",
        "posture": c.get("posture") or "",
        "nature_of_suit": c.get("nature_of_suit") or "",
    }


def _opinion_record(o: dict, cid: int) -> dict:
    rec = {
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
    }
    for field in _OPINION_TEXT_FIELDS:
        rec[field] = o.get(field) or ""
    return rec


def _opinion_cluster_id(o: dict) -> int | None:
    cid = o.get("cluster_id")
    if cid is not None:
        return int(cid)
    # Fallback: ".../api/rest/v4/clusters/<id>/"
    url = (o.get("cluster") or "").rstrip("/")
    tail = url.rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


class Command(BaseCommand):
    help = "Phase 5: pull newly-added Iowa cases from the CourtListener API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-dir",
            required=True,
            help="Base directory; each run writes a timestamped slice under it.",
        )
        parser.add_argument(
            "--since",
            default=None,
            help="Sweep start (YYYY-MM-DD or ISO datetime, UTC). Required on "
            "the first run; afterwards defaults to the stored cursor.",
        )
        parser.add_argument(
            "--overlap-days",
            type=int,
            default=2,
            help="Back the stored cursor off by this many days (idempotent "
            "re-ingest makes overlap free; it absorbs CL commit lag).",
        )
        parser.add_argument(
            "--fetch-only",
            action="store_true",
            help="Write the JSONL slice but skip ingest + downstream passes "
            "(no cursor advance).",
        )
        parser.add_argument("--token", default=None)

    def handle(self, *args, **opts):
        token = (opts["token"] or os.environ.get("COURTLISTENER_TOKEN")
                 or _token_from_env_file())
        if not token:
            raise CommandError("no token (--token / COURTLISTENER_TOKEN / .env)")

        run_start = timezone.now()
        since = self._resolve_since(opts["since"], opts["overlap_days"])
        since_str = since.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        out = Path(opts["out_dir"]) / run_start.strftime("update-%Y%m%d-%H%M%S")
        out.mkdir(parents=True, exist_ok=True)
        client = CLClient(token)

        self.stdout.write(f"sweeping CL adds since {since_str} → {out}")
        try:
            summary = self._fetch_slice(client, since_str, out)
        except Exception as exc:
            self._record_run("failed", cursor=None, log={"error": str(exc),
                                                         "since": since_str})
            raise

        self.stdout.write(json.dumps(summary, indent=2))

        if opts["fetch_only"]:
            self._record_run("pending", cursor=None,
                             log={**summary, "since": since_str,
                                  "fetch_only": True})
            self.stdout.write(self.style.WARNING(
                "fetch-only: slice written, pipeline skipped, cursor NOT advanced"
            ))
            return

        if summary["clusters"] == 0 and summary["opinions"] == 0:
            self._record_run("approved", cursor=run_start,
                             log={**summary, "since": since_str})
            self.stdout.write(self.style.SUCCESS(
                "no new cases; cursor advanced"))
            return

        try:
            self._run_pipeline(out)
        except Exception as exc:
            self._record_run("failed", cursor=None,
                             log={**summary, "since": since_str,
                                  "pipeline_error": str(exc)})
            raise

        run = self._record_run("approved", cursor=run_start,
                               log={**summary, "since": since_str},
                               last_cluster_id=summary.get("max_cluster_id"))
        self.stdout.write(self.style.SUCCESS(
            f"update complete (run #{run.pk}); cursor → {run_start.isoformat()}"
        ))

    # ------------------------------------------------------------------ fetch

    def _resolve_since(self, since_opt: str | None, overlap_days: int) -> dt.datetime:
        if since_opt:
            try:
                parsed = dt.datetime.fromisoformat(since_opt)
            except ValueError as exc:
                raise CommandError(f"bad --since {since_opt!r}: {exc}") from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        last = (
            IngestionRun.objects.filter(
                phase="update", status="approved", cursor_date__isnull=False
            )
            .order_by("-cursor_date")
            .first()
        )
        if last is None:
            raise CommandError(
                "no prior update run — pass --since for the bootstrap sweep "
                "(the corpus bulk load ends 2026-03-27, so e.g. --since 2026-03-27)"
            )
        return last.cursor_date - dt.timedelta(days=overlap_days)

    def _fetch_slice(self, client: CLClient, since_str: str, out: Path) -> dict:
        clusters: dict[int, dict] = {}       # cid → REST cluster
        cluster_court: dict[int, str] = {}   # cid → court id
        opinions: dict[int, dict] = {}       # oid → REST opinion
        dockets: dict[int, dict] = {}        # did → REST docket
        fetched_individually = 0

        for court in COURTS:
            self.stdout.write(f"  {court}: clusters…")
            for c in client.clusters_since(court, since_str):
                clusters[c["id"]] = c
                cluster_court[c["id"]] = court
            self.stdout.write(f"  {court}: opinions…")
            for o in client.opinions_since(court, since_str):
                opinions[o["id"]] = o
            self.stdout.write(f"  {court}: dockets…")
            for d in client.dockets_since(court, since_str):
                dockets[d["id"]] = d

        # An opinion added to a cluster CL created before the window (e.g. a
        # late concurrence) would be orphan-skipped by the ingest writer, which
        # only links opinions to decisions present in the same slice. Backfill
        # those clusters individually — normally zero requests.
        for o in opinions.values():
            cid = _opinion_cluster_id(o)
            if cid is not None and cid not in clusters:
                c = client.get_cluster(cid)
                clusters[cid] = c
                fetched_individually += 1
        # Docket numbers for clusters whose docket predates the window.
        for c in clusters.values():
            did = c.get("docket_id")
            if did is not None and did not in dockets:
                dockets[did] = client.get_docket(did)
                fetched_individually += 1
        # Court for individually-fetched clusters comes from their docket.
        for cid, c in clusters.items():
            if cid not in cluster_court:
                d = dockets.get(c.get("docket_id")) or {}
                cluster_court[cid] = d.get("court_id") or ""

        counts = {"clusters": 0, "opinions": 0, "citations": 0, "dockets": 0}

        def w(fh, rec):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        with (out / "clusters.jsonl").open("w", encoding="utf-8") as cl_f, \
             (out / "opinions.jsonl").open("w", encoding="utf-8") as op_f, \
             (out / "citations.jsonl").open("w", encoding="utf-8") as ci_f, \
             (out / "dockets.jsonl").open("w", encoding="utf-8") as dk_f:
            for cid in sorted(clusters):
                c = clusters[cid]
                court_id = cluster_court.get(cid, "")
                w(cl_f, _cluster_record(c, court_id, COURTS.get(court_id, "")))
                counts["clusters"] += 1
                for idx, cite in enumerate(c.get("citations") or []):
                    if idx >= _MAX_CITES_PER_CLUSTER:
                        self.stderr.write(
                            f"cluster {cid}: >{_MAX_CITES_PER_CLUSTER} "
                            "citations, extras dropped")
                        break
                    w(ci_f, {
                        "cl_citation_id": -(cid * _MAX_CITES_PER_CLUSTER + idx),
                        "cl_cluster_id": cid,
                        "volume": str(cite.get("volume") or ""),
                        "reporter": str(cite.get("reporter") or ""),
                        "page": str(cite.get("page") or ""),
                        "type": cite.get("type"),
                    })
                    counts["citations"] += 1
            for oid in sorted(opinions):
                o = opinions[oid]
                cid = _opinion_cluster_id(o)
                if cid is None:
                    self.stderr.write(f"opinion {oid}: no cluster id, skipped")
                    continue
                w(op_f, _opinion_record(o, cid))
                counts["opinions"] += 1
            for did in sorted(dockets):
                d = dockets[did]
                w(dk_f, {
                    "docket_id": did,
                    "court_id": d.get("court_id") or "",
                    "docket_number": d.get("docket_number") or "",
                })
                counts["dockets"] += 1

        return {
            **counts,
            "fetched_individually": fetched_individually,
            "max_cluster_id": max(clusters) if clusters else None,
            "out_dir": str(out),
        }

    # --------------------------------------------------------------- pipeline

    def _run_pipeline(self, out: Path) -> None:
        in_dir = str(out)
        self.stdout.write("pipeline: ingest_iowa_caselaw…")
        call_command("ingest_iowa_caselaw", in_dir=in_dir)
        self.stdout.write("pipeline: load_case_citations…")
        call_command("load_case_citations", in_dir=in_dir)
        self.stdout.write("pipeline: build_caselaw_display…")
        call_command("build_caselaw_display", in_dir=in_dir)
        self.stdout.write("pipeline: backfill_caselaw_cross_references…")
        call_command("backfill_caselaw_cross_references", in_dir=in_dir)
        self.stdout.write("pipeline: chunk_caselaw…")
        call_command("chunk_caselaw")
        if os.environ.get("VOYAGE_API_KEY"):
            self.stdout.write("pipeline: embed_chunks…")
            call_command("embed_chunks")
        else:
            # Without the key embed_chunks would write useless deterministic
            # fake vectors; leave the chunks pending for a keyed environment.
            self.stderr.write("VOYAGE_API_KEY not set — embed_chunks skipped, "
                              "chunks left pending")

    # ------------------------------------------------------------------- runs

    def _record_run(self, status: str, *, cursor, log: dict,
                    last_cluster_id: int | None = None) -> IngestionRun:
        return IngestionRun.objects.create(
            raw=None,
            phase="update",
            status=status,
            finished_at=timezone.now(),
            cursor_date=cursor,
            last_cluster_id=last_cluster_id,
            log=json.dumps(log),
        )
