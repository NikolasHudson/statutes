"""Delete one user's crowdsourced contributions from the bucket and the index.

The contribution opt-in is prospective: turning it off stops future intake and
removes nothing already shared (Nick, 2026-07-28). This command is the other
half of that policy — the deliberate, auditable way a written removal request
gets honoured. Account deletion runs the same code automatically
(apps/edms/signals.py).

    ./manage.py purge_crowdsource --user nick@example.com
    ./manage.py purge_crowdsource --user 42 --dry-run

Not scheduled and not wired to any request path on purpose: nothing about
ordinary product use should be able to delete evidence of what was shared.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.edms.models import CrowdsourceArtifact
from apps.edms.services import purge_user_contributions


class Command(BaseCommand):
    help = "Purge a user's contributed filings from the private bucket."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user", required=True, help="User id or email address."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted and stop.",
        )

    def handle(self, *args, **options):
        raw = options["user"].strip()
        query = {"pk": raw} if raw.isdigit() else {"email__iexact": raw}
        user = User.objects.filter(**query).first()
        if user is None:
            raise CommandError(f"No user matching '{raw}'.")

        pending = CrowdsourceArtifact.objects.filter(
            submitted_by=user, status=CrowdsourceArtifact.Status.STORED
        )
        count = pending.count()
        if options["dry_run"]:
            self.stdout.write(
                f"Would purge {count} artifact(s) for {user.email}:"
            )
            for row in pending[:50]:
                self.stdout.write(f"  {row.object_key} ({row.byte_size} bytes)")
            if count > 50:
                self.stdout.write(f"  … and {count - 50} more")
            return

        purged = purge_user_contributions(user)
        self.stdout.write(
            self.style.SUCCESS(f"Purged {purged} artifact(s) for {user.email}.")
        )
