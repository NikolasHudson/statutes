"""#1: materialize CrossReference edges from opinions' inline citation links.

Re-streams ``opinions.jsonl``, extracts the ``<a>`` citation links from each
opinion's raw ``html_with_citations`` (before markup stripping), and writes one
CrossReference per distinct cited case:

  * ``/opinion/<cl_opinion_id>/`` links (≈97%) resolve via the
    ``cl_opinion_id → opinion Node`` map — the primary resolver.
  * ``/c/<reporter>/<vol>/<page>/`` links (≈1%) resolve via the
    ReporterCitation table, but ONLY when the (reporter, volume, page) triple is
    unambiguous (maps to exactly one case); ambiguous/missing → external.
  * Anything that doesn't resolve to an in-slice case becomes an EXTERNAL edge
    carrying the citation's display text, so the citation is still grounded.

    python manage.py backfill_caselaw_cross_references --in-dir <dir>
    python manage.py backfill_caselaw_cross_references --in-dir <dir> --dry-run

Run AFTER ``load_case_citations`` (its ReporterCitation rows back the ``/c/``
branch). A separate pass — not inline in the writer — because a citing opinion
can link a case written later in the same stream; a second pass sees the whole
``cl_opinion_id`` map and so never emits a spurious external edge for an
in-slice case. Idempotent: a version's ``caselaw_link`` edges are deleted and
rebuilt, scoped to that source so the #2 citation-graph pass is never touched.

Two contracts worth knowing:

* **Edge target level is deliberately heterogeneous.** ``/opinion/`` links
  (≈97%, and the #2 graph) resolve to the specific cited OPINION node — the
  more precise, more informative target. ``/c/`` reporter links (≈1%) can only
  resolve to the cited DECISION node (a ReporterCitation maps a cite to a
  case). So any "who cites this case" aggregation must roll opinion → parent
  decision before comparing, and a case cited via both forms yields one
  opinion-level and one decision-level edge.
* **The rebuild is input-scoped, not corpus-scoped.** Only versions present in
  the supplied ``opinions.jsonl`` are reconciled; running against a *smaller*
  file does not retract edges for opinions absent from it. Re-run against the
  full slice to fully reconcile.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.fields.json import KeyTextTransform

from apps.corpus.models import (
    CrossReference,
    CrossReferenceKind,
    CrossReferenceSource,
    Node,
    NodeVersion,
    ReporterCitation,
    ReviewStatus,
)

from ...jsonl import iter_jsonl
from ...parser import extract_citation_links
from ...writer import get_iowa_caselaw_source

_CHUNK = 1000  # opinions per flush transaction
# Cap external_text so the (from_version, external_text, source) partial-unique
# btree index can never exceed Postgres' ~2704-byte row limit. External text is
# a best-effort grounding label; 400 chars (≤1600 bytes UTF-8) is ample.
_MAX_EXTERNAL_TEXT = 400


class Command(BaseCommand):
    help = "Materialize CrossReference edges from opinion inline links (#1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--in-dir",
            required=True,
            help="Directory containing opinions.jsonl.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Resolve + count; do not write.",
        )

    def handle(self, *args, **opts):
        in_dir = Path(opts["in_dir"])
        path = in_dir / "opinions.jsonl"
        if not path.exists():
            raise CommandError(f"missing opinions.jsonl in {in_dir}")
        dry_run = opts["dry_run"]

        source = get_iowa_caselaw_source()

        # --- preload resolver maps (a few MB each at slice scale) -----------
        # Pull only the one JSON key we need (KeyTextTransform → server-side
        # extraction) and stream with .iterator() so the full ~83k-row JSONB is
        # never materialized in the client at once.
        op_by_clid: dict[int, int] = {}   # cl_opinion_id -> opinion Node pk
        parent_of: dict[int, int | None] = {}  # opinion Node pk -> decision pk
        for pk, parent_id, clid in (
            Node.objects.filter(source=source, node_type__key="opinion")
            .annotate(clid=KeyTextTransform("cl_opinion_id", "source_metadata"))
            .values_list("pk", "parent_id", "clid")
            .iterator(chunk_size=5000)
        ):
            parent_of[pk] = parent_id
            if clid is not None:
                op_by_clid[int(clid)] = pk

        # open (current) APPROVED version per opinion node -> the from_version
        open_ver: dict[int, int] = {
            node_id: ver_id
            for node_id, ver_id in NodeVersion.objects.filter(
                node__source=source,
                node__node_type__key="opinion",
                effective_to__isnull=True,
                review_status=ReviewStatus.APPROVED,
            ).values_list("node_id", "id").iterator(chunk_size=5000)
        }

        # /c/ resolver: (reporter, volume, page) -> decision pk, UNAMBIGUOUS
        # keys only (a triple mapping to >1 case is dropped → external).
        rvp: dict[tuple, set] = defaultdict(set)
        for reporter, volume, page, to_node in (
            ReporterCitation.objects.filter(to_node__isnull=False)
            .values_list("reporter", "volume", "page", "to_node_id")
            .iterator(chunk_size=5000)
        ):
            rvp[(reporter, volume, page)].add(to_node)
        c_resolver = {k: next(iter(v)) for k, v in rvp.items() if len(v) == 1}
        if not c_resolver:
            self.stderr.write(
                self.style.WARNING(
                    "no resolvable ReporterCitation rows — every /c/ link will "
                    "become external. Did load_case_citations (#4) run first?"
                )
            )

        stats = defaultdict(int)
        # buffer of (from_version_pk, [CrossReference, ...]) for the current chunk
        chunk: list[tuple[int, list[CrossReference]]] = []

        def flush():
            if not chunk:
                return
            if dry_run:
                chunk.clear()
                return
            touched = [vid for vid, _ in chunk]
            edges = [e for _, es in chunk for e in es]
            with transaction.atomic():
                CrossReference.objects.filter(
                    from_version_id__in=touched,
                    source=CrossReferenceSource.CASELAW_LINK,
                ).delete()
                if edges:
                    CrossReference.objects.bulk_create(edges, ignore_conflicts=True)
            chunk.clear()

        for rec in iter_jsonl(path):
            cl_opinion_id = int(rec["cl_opinion_id"])
            citing_node = op_by_clid.get(cl_opinion_id)
            if citing_node is None:
                stats["missing_node"] += 1
                continue
            from_version = open_ver.get(citing_node)
            if from_version is None:
                stats["no_open_version"] += 1  # empty-body container, never cites
                continue
            decision_pk = parent_of.get(citing_node)
            stats["versions_processed"] += 1

            internal: set[int] = set()
            external: set[str] = set()
            for link in extract_citation_links(rec.get("html_with_citations") or ""):
                stats["links_total"] += 1
                if link.kind == "opinion":
                    tgt = op_by_clid.get(link.cl_opinion_id)
                    fallback = link.display or f"cl-opinion-{link.cl_opinion_id}"
                else:  # reporter
                    tgt = c_resolver.get((link.reporter, link.volume, link.page))
                    fallback = link.display or (
                        f"{link.volume} {link.reporter} {link.page}".strip()
                    )
                if tgt is not None:
                    if tgt == citing_node or tgt == decision_pk:
                        stats["skipped_self"] += 1  # opinion citing its own case
                        continue
                    if decision_pk is not None and parent_of.get(tgt) == decision_pk:
                        # a sibling opinion of the SAME decision (e.g. a
                        # concurrence pointing at the lead) — intra-case, not a
                        # citation to outside authority.
                        stats["skipped_sibling"] += 1
                        continue
                    internal.add(tgt)
                elif fallback:
                    external.add(fallback[:_MAX_EXTERNAL_TEXT])

            edges = [
                CrossReference(
                    from_version_id=from_version,
                    to_node_id=tgt,
                    kind=CrossReferenceKind.INTERNAL,
                    source=CrossReferenceSource.CASELAW_LINK,
                )
                for tgt in internal
            ] + [
                CrossReference(
                    from_version_id=from_version,
                    to_node=None,
                    external_text=txt,
                    kind=CrossReferenceKind.EXTERNAL,
                    source=CrossReferenceSource.CASELAW_LINK,
                )
                for txt in external
            ]
            stats["internal_edges"] += len(internal)
            stats["external_edges"] += len(external)
            # Append even when empty so re-runs still clear this version's stale
            # caselaw_link edges in the flush delete.
            chunk.append((from_version, edges))
            if len(chunk) >= _CHUNK:
                flush()
        flush()

        verb = "Would link" if dry_run else "Linked"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {stats['internal_edges']} internal + "
                f"{stats['external_edges']} external edge(s) across "
                f"{stats['versions_processed']} opinion version(s)."
            )
        )
        self.stdout.write(
            f"  links seen: {stats['links_total']}  "
            f"self-skipped: {stats['skipped_self']}  "
            f"sibling-skipped: {stats['skipped_sibling']}  "
            f"opinions w/o open version: {stats['no_open_version']}  "
            f"opinions w/o node: {stats['missing_node']}"
        )
