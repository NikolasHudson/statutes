"""#2: materialize the CourtListener citation graph (with depth) as CrossReference.

Streams CourtListener's ``citation-map`` bulk file — the ``search_opinionscited``
table, columns ``id, depth, citing_opinion_id, cited_opinion_id`` — and writes one
``CrossReference(source=CASELAW_GRAPH, weight=depth)`` per in-corpus edge:

    from_version = the citing opinion's current version
    to_node      = the cited opinion node
    weight       = depth (how many times the citing opinion cites the cited one)

This is the graph the #1 inline-link pass (``backfill_caselaw_cross_references``)
could not give us: CL's eyecite-extracted edges carry a **depth** the ``<a>``-tag
parse has no way to know, and they catch cites that were never hyperlinked. The
two passes are deliberately separate ``source`` values, so rebuilding one never
touches the other (see ``CrossReferenceSource``).

    python manage.py build_caselaw_citation_graph --citation-map <file.csv.bz2>
    python manage.py build_caselaw_citation_graph --citation-map <file.csv.bz2> --dry-run

The bulk file is the *national* graph (~100M+ rows); we stream it once
(``open_bulk_csv`` — never decompress to disk) and keep only **in-corpus** edges,
i.e. both the citing and cited opinion resolve to an Iowa node via
``cl_opinion_id``. That is exactly the slice the treatment classifier (PR3) needs:
to decide whether case B is still good law we look at the Iowa opinions that cite
it, which is only meaningful when we hold the citing opinion's text.

Scope decisions (mirroring #1):
  * **Internal edges only.** An Iowa opinion citing a non-corpus case is skipped
    (counted) — the citation-map gives only a ``cl_opinion_id``, no display text,
    so an external edge would be a bare id; #1 already captures externals with
    real citation text from the inline links.
  * **Self / sibling skipped.** An opinion citing its own case, or a sibling
    opinion of the same decision (a dissent pointing at the lead), is intra-case,
    not a citation to outside authority.

Idempotent: every CASELAW_GRAPH edge under the Iowa source is deleted up front and
rebuilt. (Unlike #1 we can't scope the delete per ``from_version`` chunk — the
bulk file is ordered by the citing/cited opinion ids, so one citing version's
edges are scattered across the whole stream; a per-chunk delete would clobber
edges written by an earlier chunk.)
"""

from __future__ import annotations

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
    ReviewStatus,
)

from ...csv_stream import open_bulk_csv
from ...writer import get_iowa_caselaw_source

_CHUNK = 2000          # edges per bulk_create
_PROGRESS_EVERY = 5_000_000  # log every N streamed rows (the file is ~100M rows)


class Command(BaseCommand):
    help = "Build the CASELAW_GRAPH CrossReference edges from CL's citation-map (#2)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--citation-map",
            required=True,
            help="Path to a CourtListener citation-map-<date>.csv.bz2 bulk file "
            "(streamed; never decompressed to disk).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Stream, resolve, and count; do not write.",
        )

    def handle(self, *args, **opts):
        path = Path(opts["citation_map"])
        if not path.exists():
            raise CommandError(f"citation-map file not found: {path}")
        dry_run = opts["dry_run"]
        source = get_iowa_caselaw_source()

        # --- preload resolver maps (a few MB at slice scale; mirrors #1) ------
        op_by_clid: dict[int, int] = {}        # cl_opinion_id -> opinion Node pk
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

        # current APPROVED version per opinion node -> the from_version
        open_ver: dict[int, int] = {
            node_id: ver_id
            for node_id, ver_id in NodeVersion.objects.filter(
                node__source=source,
                node__node_type__key="opinion",
                effective_to__isnull=True,
                review_status=ReviewStatus.APPROVED,
            ).values_list("node_id", "id").iterator(chunk_size=5000)
        }
        self.stdout.write(
            f"Resolver: {len(op_by_clid):,} Iowa opinions "
            f"({len(open_ver):,} with an open version)."
        )

        # --- idempotency: drop the whole CASELAW_GRAPH slice up front ---------
        if not dry_run:
            deleted, _ = CrossReference.objects.filter(
                source=CrossReferenceSource.CASELAW_GRAPH,
                from_version__node__source=source,
            ).delete()
            if deleted:
                self.stdout.write(f"Cleared {deleted:,} existing CASELAW_GRAPH edge(s).")

        stats: dict[str, int] = {
            "rows": 0, "edges": 0, "citing_external": 0, "cited_external": 0,
            "no_open_version": 0, "self": 0, "sibling": 0, "bad_depth": 0,
        }
        batch: list[CrossReference] = []

        def flush():
            if not batch or dry_run:
                batch.clear()
                return
            CrossReference.objects.bulk_create(batch, ignore_conflicts=True)
            batch.clear()

        for row in open_bulk_csv(path):
            stats["rows"] += 1
            if stats["rows"] % _PROGRESS_EVERY == 0:
                self.stdout.write(
                    f"  …{stats['rows']:,} rows streamed, "
                    f"{stats['edges']:,} in-corpus edge(s) so far"
                )
            try:
                citing_clid = int(row["citing_opinion_id"])
                cited_clid = int(row["cited_opinion_id"])
            except (KeyError, ValueError, TypeError):
                continue

            citing_node = op_by_clid.get(citing_clid)
            if citing_node is None:
                stats["citing_external"] += 1
                continue
            cited_node = op_by_clid.get(cited_clid)
            if cited_node is None:
                stats["cited_external"] += 1   # Iowa case citing a non-corpus case
                continue
            from_version = open_ver.get(citing_node)
            if from_version is None:
                stats["no_open_version"] += 1
                continue
            if cited_node == citing_node:
                stats["self"] += 1
                continue
            if (
                parent_of.get(citing_node) is not None
                and parent_of.get(cited_node) == parent_of.get(citing_node)
            ):
                stats["sibling"] += 1          # intra-case (e.g. dissent → lead)
                continue
            try:
                weight = int(row["depth"])
                if weight < 1:  # depth is a count ≥1; a 0/negative is corruption
                    raise ValueError("non-positive depth")
            except (KeyError, ValueError, TypeError):
                # weight is a PositiveIntegerField — a negative would crash the
                # bulk insert, so coerce corrupt depth to 1 and keep streaming.
                stats["bad_depth"] += 1
                weight = 1

            batch.append(
                CrossReference(
                    from_version_id=from_version,
                    to_node_id=cited_node,
                    kind=CrossReferenceKind.INTERNAL,
                    source=CrossReferenceSource.CASELAW_GRAPH,
                    weight=weight,
                )
            )
            stats["edges"] += 1
            if len(batch) >= _CHUNK:
                with transaction.atomic():
                    flush()
        with transaction.atomic():
            flush()

        verb = "Would build" if dry_run else "Built"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {stats['edges']:,} in-corpus citation-graph edge(s) "
                f"from {stats['rows']:,} streamed rows."
            )
        )
        self.stdout.write(
            f"  skipped — citing not in corpus: {stats['citing_external']:,}  "
            f"cited not in corpus: {stats['cited_external']:,}  "
            f"no open version: {stats['no_open_version']:,}  "
            f"self: {stats['self']:,}  sibling: {stats['sibling']:,}  "
            f"bad depth (→1): {stats['bad_depth']:,}"
        )
