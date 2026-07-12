"""Re-derive ``User.tier`` from billing state and report (or fix) the drift.

``User.tier`` is a cache of :func:`apps.tenancy.services.effective_plan`, kept in
step by the Stripe webhooks and the membership mutations. Anything that writes tier
outside those paths (a staff edit in the Django admin, a dropped webhook, a manual
DB fix, this migration's own backfill) can leave the cache stale — a user paying for
nothing, or worse, a canceled account still on ``firm``.

This is the reconciler. Cron it (nightly is plenty):

    python manage.py reconcile_tiers            # report drift, change nothing
    python manage.py reconcile_tiers --fix      # write the corrections
    python manage.py reconcile_tiers --fix --quiet

Exit code is 1 when drift is found and ``--fix`` was not given, so a cron wrapper
can alert on it.
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.tenancy.services import effective_plan


class Command(BaseCommand):
    help = "Recompute User.tier from billing state; report drift, --fix to write."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Write the recomputed tier onto drifted users.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print the summary line.",
        )

    def handle(self, *args, **options):
        fix = options["fix"]
        quiet = options["quiet"]

        drifted: list[tuple[User, str]] = []
        # prefetch the membership→org→subscription chain effective_plan walks.
        users = User.objects.all().order_by("id")
        for user in users.iterator():
            expected = effective_plan(user)
            if user.tier != expected:
                drifted.append((user, expected))

        for user, expected in drifted:
            if not quiet:
                self.stdout.write(f"{user.email}: {user.tier} → {expected}")
            if fix:
                user.tier = expected
                user.save(update_fields=["tier"])

        total = users.count()
        if not drifted:
            self.stdout.write(
                self.style.SUCCESS(f"{total} users checked, no tier drift.")
            )
            return

        summary = f"{total} users checked, {len(drifted)} drifted"
        if fix:
            self.stdout.write(self.style.SUCCESS(f"{summary} — fixed."))
            return
        self.stdout.write(self.style.WARNING(f"{summary} — run with --fix to write."))
        sys.exit(1)
