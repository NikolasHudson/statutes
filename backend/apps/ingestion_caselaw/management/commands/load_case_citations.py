"""#4: populate the ReporterCitation resolver from ``citations.jsonl``.

Maps every parallel reporter citation (volume/reporter/page) to the decision
Node of the cluster it belongs to, so a free-text cite ("759 N.W.2d 3") or an
inline ``/c/<reporter>/<vol>/<page>/`` link can resolve to the case it names.

    python manage.py load_case_citations --in-dir <dir>
    python manage.py load_case_citations --in-dir <dir> --dry-run

Run AFTER ``ingest_iowa_caselaw`` (it needs the decision Nodes) and BEFORE
``backfill_caselaw_cross_references`` (whose ``/c/`` branch resolves through
this table). Idempotent: rows are upserted on the unique ``cl_citation_id``, so
re-running reconciles without duplicating. A citation whose cluster is outside
the loaded slice is still stored with ``to_node=None`` — it remains a valid
reporter→cluster fact, just unresolved.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models.fields.json import KeyTextTransform

from apps.corpus.models import Node, ReporterCitation

from ...jsonl import iter_jsonl
from ...writer import get_iowa_caselaw_source

_BATCH = 2000


class Command(BaseCommand):
    help = "Populate the ReporterCitation resolver from citations.jsonl (#4)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--in-dir",
            required=True,
            help="Directory containing citations.jsonl.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse + count; do not write.",
        )

    def handle(self, *args, **opts):
        in_dir = Path(opts["in_dir"])
        path = in_dir / "citations.jsonl"
        if not path.exists():
            raise CommandError(f"missing citations.jsonl in {in_dir}")

        source = get_iowa_caselaw_source()

        # {cl_cluster_id -> decision Node pk}. Decision nodes store their
        # cluster id in source_metadata; pull just that key server-side and
        # stream so the full JSONB is never materialized at once.
        cluster_to_node: dict[int, int] = {}
        for pk, cid in (
            Node.objects.filter(source=source, node_type__key="decision")
            .annotate(cid=KeyTextTransform("cl_cluster_id", "source_metadata"))
            .values_list("pk", "cid")
            .iterator(chunk_size=5000)
        ):
            if cid is not None:
                cluster_to_node[int(cid)] = pk

        total = resolved = 0
        buf: list[ReporterCitation] = []

        def flush():
            if not buf or opts["dry_run"]:
                buf.clear()
                return
            ReporterCitation.objects.bulk_create(
                buf,
                update_conflicts=True,
                unique_fields=["cl_citation_id"],
                update_fields=["cl_cluster_id", "reporter", "volume", "page",
                               "type", "to_node"],
            )
            buf.clear()

        for rec in iter_jsonl(path):
            cluster_id = int(rec["cl_cluster_id"])
            node_pk = cluster_to_node.get(cluster_id)
            total += 1
            resolved += int(node_pk is not None)
            buf.append(
                ReporterCitation(
                    cl_citation_id=int(rec["cl_citation_id"]),
                    cl_cluster_id=cluster_id,
                    reporter=str(rec.get("reporter") or ""),
                    volume=str(rec.get("volume") or ""),
                    page=str(rec.get("page") or ""),
                    type=rec.get("type"),
                    to_node_id=node_pk,
                )
            )
            if len(buf) >= _BATCH:
                flush()
        flush()

        verb = "Would load" if opts["dry_run"] else "Loaded"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {total} reporter citation(s); "
                f"{resolved} resolved to an in-slice case, "
                f"{total - resolved} unresolved (cluster out of slice)."
            )
        )
