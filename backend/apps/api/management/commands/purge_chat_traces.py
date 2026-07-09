"""Delete ChatTrace and VerificationRun rows past the retention window.

A chat trace holds the user's verbatim question and the full answer, and a
verification run holds quote fragments lifted from the user's uploaded
document — both are confidential and must not live forever. This command
deletes every row of either table older than
``settings.CHAT_TRACE_RETENTION_DAYS`` (default 7). Run it on a schedule
(cron / the platform scheduler); it is idempotent and safe to re-run.

    python manage.py purge_chat_traces             # one-shot, configured window
    python manage.py purge_chat_traces --days 30   # override the window
    python manage.py purge_chat_traces --dry-run   # report, delete nothing
    python manage.py purge_chat_traces --forever   # long-lived worker loop

The --forever mode is what the App Platform trace-purge worker runs: it purges,
sleeps --interval seconds, and repeats, so the worker's run_command stays a
plain shell-free argv (the slim image has no bash and the platform does not
wrap run_command in a shell).
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.api.models import ChatTrace, SearchLog, VerificationRun
from apps.mail.models import InboundEmail, OutboundEmail


class Command(BaseCommand):
    help = (
        "Delete ChatTrace and VerificationRun rows older than the retention "
        "window."
    )

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
        parser.add_argument(
            "--forever",
            action="store_true",
            help=(
                "Run as a long-lived worker: purge, sleep --interval seconds, "
                "repeat. Lets the App Platform worker run a single shell-free "
                "argv (no `while/sleep` run_command) so it works regardless of "
                "whether the platform execs the command directly or via a shell "
                "— the slim runtime image ships no bash."
            ),
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

        # Long-lived worker mode. A transient failure (e.g. a DB blip) must not
        # kill the loop, so each pass is guarded and we sleep before retrying.
        interval = options["interval"]
        self.stdout.write(f"Starting trace-purge loop (every {interval}s).")
        while True:
            try:
                self._purge_once(options)
            except Exception as exc:  # noqa: BLE001 - keep the worker alive
                self.stderr.write(f"purge pass failed, will retry: {exc!r}")
            time.sleep(interval)

    def _purge_once(self, options):
        days = options["days"]
        if days is None:
            days = getattr(settings, "CHAT_TRACE_RETENTION_DAYS", 7)

        if days <= 0:
            self.stdout.write(
                f"Retention disabled (days={days}); nothing purged."
            )
            return

        cutoff = timezone.now() - timedelta(days=days)
        stale_traces = ChatTrace.objects.filter(created_at__lt=cutoff)
        stale_runs = VerificationRun.objects.filter(created_at__lt=cutoff)
        stale_searches = SearchLog.objects.filter(created_at__lt=cutoff)
        # Email-assistant bodies are the same class of confidential material as
        # a chat trace. SCRUB (not delete) so threading metadata — message ids,
        # thread links, status — survives for reply matching and ops forensics,
        # while the content itself honors the retention window. Thread history
        # (EmailThread.messages) is intentionally kept while a thread is open:
        # it IS the conversation state; a reply after the window still works.
        stale_inbound = InboundEmail.objects.filter(
            created_at__lt=cutoff
        ).exclude(body_text="", raw_payload={})
        stale_outbound = OutboundEmail.objects.filter(
            created_at__lt=cutoff
        ).exclude(body_text="")

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] {stale_traces.count()} chat trace(s), "
                f"{stale_runs.count()} verification run(s), "
                f"{stale_searches.count()} search log(s), "
                f"{stale_inbound.count()} inbound email(s) and "
                f"{stale_outbound.count()} outbound email(s) older than {days}d "
                f"(before {cutoff.isoformat()}) would be deleted/scrubbed."
            )
            return

        deleted_traces, _ = stale_traces.delete()
        deleted_runs, _ = stale_runs.delete()
        deleted_searches, _ = stale_searches.delete()
        scrubbed_inbound = stale_inbound.update(body_text="", raw_payload={})
        scrubbed_outbound = stale_outbound.update(body_text="")
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_traces} chat trace(s), {deleted_runs} "
                f"verification run(s) and {deleted_searches} search log(s); "
                f"scrubbed {scrubbed_inbound} inbound and {scrubbed_outbound} "
                f"outbound email bodies older than {days}d "
                f"(before {cutoff.isoformat()})."
            )
        )
