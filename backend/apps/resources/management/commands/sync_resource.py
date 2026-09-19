"""Refresh one resources dataset from its published source.

    python manage.py sync_resource iowa-business-entities
    python manage.py sync_resource iowa-business-entities --dry-run
    python manage.py sync_resource iowa-business-entities --file /tmp/rows.zip
    python manage.py sync_resource iowa-business-entities --force

Exit status is what a cron wrapper should key on: 0 for a load that ran or was
correctly skipped, non-zero for anything that refused or failed. Every run
leaves a ``Snapshot`` row saying which it was.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from apps.resources.models import Dataset, SnapshotStatus
from apps.resources.registry import get_sync, known_slugs
from apps.resources.sync import SyncAborted


class Command(BaseCommand):
    help = "Sync a resources dataset from its published source file."

    def add_arguments(self, parser):
        parser.add_argument("slug", help=f"one of: {', '.join(known_slugs())}")
        parser.add_argument(
            "--file",
            dest="path",
            default=None,
            help="Load this local file instead of downloading (zip or csv).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Load even if unchanged, and override the safety gate.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Stage and report what would change, then roll back.",
        )

    def handle(self, *args, **options):
        slug = options["slug"]
        try:
            sync = get_sync(slug)
        except KeyError:
            raise CommandError(
                f"unknown dataset '{slug}'. Known: {', '.join(known_slugs())}"
            ) from None
        if not Dataset.objects.filter(slug=slug).exists():
            raise CommandError(
                f"no Dataset row for '{slug}' — the registry row is created by "
                "a data migration; run `manage.py migrate resources`."
            )

        # A cron log wants the step-by-step; a test run does not.
        verbose = options.get("verbosity", 1) >= 1
        log = (lambda msg: self.stdout.write(str(msg))) if verbose else (lambda msg: None)

        started = time.monotonic()
        try:
            result = sync.run(
                path=options["path"],
                force=options["force"],
                dry_run=options["dry_run"],
                log=log,
            )
        except SyncAborted as exc:
            raise CommandError(str(exc)) from None

        elapsed = time.monotonic() - started
        log(
            f"{slug}: {result.status} in {elapsed:.1f}s — "
            f"{result.row_count:,} rows read, {result.inserted:,} inserted, "
            f"{result.updated:,} updated ({result.reactivated:,} reactivated), "
            f"{result.deactivated:,} deactivated, {result.rejected:,} rejected"
        )
        if result.message:
            log(result.message)

        if options["dry_run"] and result.status == SnapshotStatus.ABORTED:
            # A dry run always rolls back; that is the point, not a failure.
            log(self.style.SUCCESS("dry run complete — nothing written"))
        elif result.status == SnapshotStatus.OK:
            log(self.style.SUCCESS("done"))
        elif result.status == SnapshotStatus.SKIPPED:
            log(self.style.SUCCESS("nothing to do"))
        else:
            raise CommandError(result.message or result.status)
