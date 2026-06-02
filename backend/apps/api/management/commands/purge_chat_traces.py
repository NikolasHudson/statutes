"""Delete ChatTrace rows past the retention window.

A trace holds the user's verbatim question and the full answer, so it is
confidential and must not live forever. This command deletes every row older
than ``settings.CHAT_TRACE_RETENTION_DAYS`` (default 7). Run it on a schedule
(cron / the platform scheduler); it is idempotent and safe to re-run.

    python manage.py purge_chat_traces            # use the configured window
    python manage.py purge_chat_traces --days 30  # override the window
    python manage.py purge_chat_traces --dry-run  # report, delete nothing
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.api.models import ChatTrace


class Command(BaseCommand):
    help = "Delete ChatTrace rows older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retention window in days (default: CHAT_TRACE_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = getattr(settings, "CHAT_TRACE_RETENTION_DAYS", 7)

        if days <= 0:
            self.stdout.write(
                f"Retention disabled (days={days}); nothing purged."
            )
            return

        cutoff = timezone.now() - timedelta(days=days)
        stale = ChatTrace.objects.filter(created_at__lt=cutoff)
        count = stale.count()

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] {count} trace(s) older than {days}d "
                f"(before {cutoff.isoformat()}) would be deleted."
            )
            return

        deleted, _ = stale.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} chat trace(s) older than {days}d "
                f"(before {cutoff.isoformat()})."
            )
        )
