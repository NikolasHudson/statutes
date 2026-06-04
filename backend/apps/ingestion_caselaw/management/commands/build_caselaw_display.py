"""Populate display-only ``NodeVersion.body_segments`` for caselaw opinions
from the retained ``html_with_citations`` in the acquire slice.

Display-only: the canonical ``body_text`` (FTS / content_hash / embeddings) is
untouched, and no new versions are created — this just sets a column on the
existing open version. Citation anchors (``/opinion/<id>/``) are resolved to the
cited case's decision-node id so the UI can link them to ``/cases/<id>``.

    manage.py build_caselaw_display --in-dir /home/dev/cl-iowa-slice --cluster 4405279
    manage.py build_caselaw_display --in-dir /home/dev/cl-iowa-slice   # full backfill
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.corpus.models import Node, NodeVersion
from apps.ingestion_caselaw.display import html_to_blocks

TEXT_FIELD = "html_with_citations"


class Command(BaseCommand):
    help = "Build display-only body_segments (linked citations) for caselaw opinions."

    def add_arguments(self, parser):
        parser.add_argument("--in-dir", required=True)
        parser.add_argument(
            "--cluster", type=int, default=None,
            help="only opinions of this cl_cluster_id (prototype scope)",
        )

    def handle(self, *args, **opts):
        opinions_path = Path(opts["in_dir"]) / "opinions.jsonl"
        if not opinions_path.exists():
            raise CommandError(f"missing {opinions_path}")

        self.stdout.write("Building cl_opinion_id → decision-node map …")
        cl_to_decision: dict[int, int] = {}
        for cl, parent in Node.objects.filter(
            source__slug="iowa-caselaw", node_type__key="opinion"
        ).values_list("source_metadata__cl_opinion_id", "parent_id"):
            if cl is not None and parent is not None:
                cl_to_decision[int(cl)] = parent
        self.stdout.write(f"  {len(cl_to_decision):,} opinions mapped")

        self.stdout.write("Preloading open opinion versions …")
        ver_by_path = dict(
            NodeVersion.objects.filter(
                node__source__slug="iowa-caselaw",
                node__node_type__key="opinion",
                effective_to__isnull=True,
            ).values_list("node__path", "id")
        )
        self.stdout.write(f"  {len(ver_by_path):,} versions")

        cluster_tag = f"cl-cluster-{opts['cluster']}/" if opts["cluster"] else None
        scanned = updated = links = unresolved = 0
        batch: list[NodeVersion] = []

        def flush():
            nonlocal updated
            if batch:
                NodeVersion.objects.bulk_update(batch, ["body_segments"])
                updated += len(batch)
                batch.clear()
                self.stdout.write(f"  {updated:,} updated …")

        with opinions_path.open() as fh:
            for line in fh:
                # cheap substring gate before the (relatively costly) JSON parse
                if cluster_tag and cluster_tag not in line:
                    continue
                rec = json.loads(line)
                path = rec.get("node_path") or ""
                if cluster_tag and not path.startswith(cluster_tag):
                    continue
                vid = ver_by_path.get(path)
                if vid is None:
                    continue
                scanned += 1
                html = rec.get(TEXT_FIELD) or ""
                if not html.strip():
                    continue
                blocks = html_to_blocks(html)
                for block in blocks:
                    for run in block["runs"]:
                        cl = run.pop("cl", None)
                        if cl is None:
                            continue
                        case = cl_to_decision.get(int(cl))
                        if case is not None:
                            run["case"] = case
                            links += 1
                        else:
                            unresolved += 1
                if not blocks:
                    continue
                batch.append(NodeVersion(id=vid, body_segments=blocks))
                if len(batch) >= 200:
                    flush()
        flush()

        self.stdout.write(self.style.SUCCESS(
            f"updated {updated} opinion version(s) (scanned {scanned}); "
            f"{links} cite links resolved, {unresolved} external/unresolved"
        ))
