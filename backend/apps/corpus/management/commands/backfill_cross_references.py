"""Populate the CrossReference table from statute body text.

    python manage.py backfill_cross_references
    python manage.py backfill_cross_references --dry-run
    python manage.py backfill_cross_references --source iowa-code

The ``CrossReference`` model has existed since launch but nothing wrote
to it — ingestion only stashed the upstream ``referred_to_in`` list in
source_metadata. This walks every current approved NodeVersion, extracts
the citations its body text makes (the same ``citation_links`` primitive
the reader uses for inline links), and materializes them as first-class
internal references so ``/sections/{id}/cross-references`` and future
chat grounding have real data to read.

Idempotent: a version's outgoing references are deleted and rebuilt each
run, so re-running after a re-ingest just reconciles. Scoped to Iowa Code
by default (see citation_links — Court Rules paths aren't parser-ready).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.corpus.models import (
    CrossReference,
    CrossReferenceKind,
    NodeVersion,
    ReviewStatus,
    Source,
)
from apps.corpus.services.lookups import citation_links


class Command(BaseCommand):
    help = "Materialize internal CrossReference rows from statute body text."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="iowa-code",
            help="Source slug to backfill (default: iowa-code).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **opts):
        slug = opts["source"]
        dry_run = opts["dry_run"]

        source = Source.objects.filter(slug=slug).first()
        if source is None:
            self.stderr.write(self.style.ERROR(f"No source with slug {slug!r}"))
            return

        versions = (
            NodeVersion.objects.filter(
                node__source=source,
                effective_to__isnull=True,
                review_status=ReviewStatus.APPROVED,
            )
            .select_related("node")
            .order_by("node__path")
        )

        versions_with_refs = 0
        total_refs = 0
        for version in versions.iterator():
            links = citation_links(
                version.body_text,
                source=source,
                exclude_node_id=version.node_id,
            )
            # One CrossReference per distinct target — the body may cite
            # the same section three times; that's one edge, not three.
            target_ids = sorted(
                {link.target_node_id for link in links}
            )
            if not target_ids:
                if not dry_run:
                    CrossReference.objects.filter(
                        from_version=version
                    ).delete()
                continue

            versions_with_refs += 1
            total_refs += len(target_ids)

            if dry_run:
                self.stdout.write(
                    f"{version.node.path}: "
                    f"{len(target_ids)} ref(s) → "
                    + ", ".join(
                        sorted(
                            {link.target_path for link in links},
                            key=len,
                        )
                    )
                )
                continue

            with transaction.atomic():
                CrossReference.objects.filter(from_version=version).delete()
                CrossReference.objects.bulk_create(
                    [
                        CrossReference(
                            from_version=version,
                            to_node_id=target_id,
                            kind=CrossReferenceKind.INTERNAL,
                        )
                        for target_id in target_ids
                    ]
                )

        verb = "Would link" if dry_run else "Linked"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {total_refs} cross-reference(s) across "
                f"{versions_with_refs} section(s) in {slug}."
            )
        )
