"""Delete marketing lead PII past the retention window.

Lead rows are personal data with no prior lifecycle: a ``ContactSubmission``
holds a name, email, message and source IP, and a ``NewsletterSubscriber`` holds
an email. Keeping them forever is the SOC 2 data-retention gap this closes.

Two different rules, because the two tables mean different things:

* ``ContactSubmission`` — a one-off message. Deleted outright once it is older
  than the window (a lead nobody acted on in a year is not a lead we should
  still be storing PII for).
* ``NewsletterSubscriber`` — a live mailing list. Active subscribers are kept;
  only rows that have been UNSUBSCRIBED longer than the window are deleted, so
  the opt-out is honored and then the record itself is erased.

The window is ``settings.MARKETING_LEAD_RETENTION_DAYS`` (default 0 = disabled,
retain forever). Setting a real number is a policy decision, so the mechanism
ships off; turn it on and schedule this command (cron / platform scheduler).
Idempotent and safe to re-run.

    python manage.py purge_marketing_leads              # one-shot, configured window
    python manage.py purge_marketing_leads --days 365   # override the window
    python manage.py purge_marketing_leads --dry-run    # report, delete nothing
    python manage.py purge_marketing_leads --forever    # long-lived worker loop
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketing.models import ContactSubmission, NewsletterSubscriber


class Command(BaseCommand):
    help = "Delete marketing lead PII (contact submissions, unsubscribed emails) past retention."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retention window in days (default: MARKETING_LEAD_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be deleted without deleting them.",
        )
        parser.add_argument(
            "--forever",
            action="store_true",
            help="Run as a long-lived worker: purge, sleep --interval seconds, repeat.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=86400,
            help="Seconds to sleep between runs when --forever is set (default: 86400).",
        )

    def handle(self, *args, **options):
        if not options["forever"]:
            self._purge_once(options)
            return

        interval = options["interval"]
        self.stdout.write(f"Starting marketing-lead purge loop (every {interval}s).")
        while True:
            try:
                self._purge_once(options)
            except Exception as exc:  # noqa: BLE001 - keep the worker alive
                self.stderr.write(f"purge pass failed, will retry: {exc!r}")
            time.sleep(interval)

    def _purge_once(self, options):
        days = options["days"]
        if days is None:
            days = getattr(settings, "MARKETING_LEAD_RETENTION_DAYS", 0)

        if days <= 0:
            self.stdout.write(f"Retention disabled (days={days}); nothing purged.")
            return

        cutoff = timezone.now() - timedelta(days=days)
        stale_contacts = ContactSubmission.objects.filter(created_at__lt=cutoff)
        # Only UNSUBSCRIBED subscribers are eligible — active ones are the live
        # list. NULL unsubscribed_at is excluded by the __lt comparison.
        stale_unsubs = NewsletterSubscriber.objects.filter(
            unsubscribed_at__lt=cutoff
        )

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] {stale_contacts.count()} contact submission(s) and "
                f"{stale_unsubs.count()} unsubscribed email(s) older than {days}d "
                f"(before {cutoff.isoformat()}) would be deleted."
            )
            return

        deleted_contacts, _ = stale_contacts.delete()
        deleted_unsubs, _ = stale_unsubs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_contacts} contact submission(s) and "
                f"{deleted_unsubs} unsubscribed email(s) older than {days}d "
                f"(before {cutoff.isoformat()})."
            )
        )
