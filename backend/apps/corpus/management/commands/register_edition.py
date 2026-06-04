"""Register an Edition row over data that is already in the corpus.

An Edition is a named as-of date over the append-only NodeVersion timeline.
Use this to label the edition that is currently loaded (so prior editions have
something to anchor behind), e.g. the 2026 Iowa Code::

    python manage.py register_edition --source iowa-code --year 2026 --as-of 2026-04-30

``--as-of`` must be on or after the newest ``effective_from`` of that source's
current (open) versions so a point-in-time lookup at that date resolves them.
When omitted it defaults to the max ``effective_from`` among open versions.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max

from apps.corpus.models import Edition, NodeVersion, Source


class Command(BaseCommand):
    help = "Create/update an Edition row labelling already-loaded corpus data."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, help="Source slug, e.g. iowa-code")
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--as-of", type=str, default=None, help="ISO date. Defaults to max effective_from of open versions.")
        parser.add_argument("--label", type=str, default=None, help="Display label. Defaults to '<Source name> <year>'.")
        parser.add_argument("--published-at", type=str, default=None, help="ISO publication date (optional).")

    def handle(self, *args, **opts):
        try:
            source = Source.objects.get(slug=opts["source"])
        except Source.DoesNotExist as e:
            raise CommandError(f"no source with slug {opts['source']!r}") from e

        if opts["as_of"]:
            as_of = dt.date.fromisoformat(opts["as_of"])
        else:
            agg = NodeVersion.objects.filter(
                node__source=source, effective_to__isnull=True
            ).aggregate(mx=Max("effective_from"))
            as_of = agg["mx"]
            if as_of is None:
                raise CommandError(
                    "source has no open versions; pass --as-of explicitly."
                )

        label = opts["label"] or f"{source.name} {opts['year']}"
        published_at = (
            dt.date.fromisoformat(opts["published_at"]) if opts["published_at"] else None
        )

        edition, created = Edition.objects.update_or_create(
            source=source,
            year=opts["year"],
            defaults={"label": label, "as_of_date": as_of, "published_at": published_at},
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} edition {edition.label} (as of {edition.as_of_date}).")
        )
