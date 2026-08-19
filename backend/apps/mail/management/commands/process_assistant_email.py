"""Drain the inbound-email queue: run each pending message through the
assistant pipeline (apps/mail/services.py) and reply by email.

    python manage.py process_assistant_email            # one pass, then exit
    python manage.py process_assistant_email --forever  # long-lived worker

--forever is what the App Platform email-assistant worker runs. Same rationale
as purge_chat_traces: App Platform has no cron and no bash in the slim image,
so the loop/sleep/error-guard live inside the command and the worker's
run_command stays a single shell-free argv.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.mail.services import claim_pending, process_inbound


class Command(BaseCommand):
    help = "Process pending inbound assistant emails and send replies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--forever",
            action="store_true",
            help="Run as a long-lived worker: process, sleep --interval, repeat.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=5,
            help="Seconds to sleep between passes when the queue is empty "
            "(default: 5). A non-empty pass loops again immediately.",
        )
        parser.add_argument(
            "--batch",
            type=int,
            default=10,
            help="Messages to claim per pass (default: 10).",
        )

    def handle(self, *args, **options):
        if not options["forever"]:
            processed = self._one_pass(options["batch"])
            self.stdout.write(f"Processed {processed} message(s).")
            return

        interval = options["interval"]
        self.stdout.write(
            f"Starting email-assistant loop (poll every {interval}s)."
        )
        while True:
            # Recycle a stale/dropped persistent connection before each pass;
            # nothing else does outside a Django request, and a dropped
            # connection would otherwise fail every pass until redeploy (same
            # bug class as apps/mcp_server/server._with_db_hygiene).
            close_old_connections()
            try:
                processed = self._one_pass(options["batch"])
            except Exception as exc:  # noqa: BLE001 — keep the worker alive
                processed = 0
                self.stderr.write(f"pass failed, will retry: {exc!r}")
            if processed == 0:
                time.sleep(interval)

    def _one_pass(self, batch: int) -> int:
        rows = claim_pending(batch)
        for inbound in rows:
            process_inbound(inbound)
        return len(rows)
