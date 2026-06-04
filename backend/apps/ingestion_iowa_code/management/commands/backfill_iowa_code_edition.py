"""Load a *prior* Iowa Code edition behind the data already in the store.

Two-step flow (the scrape step is the existing command)::

    python manage.py scrape_iowa_code --year 2025 --output data/raw/iowa_code_2025.json
    python manage.py backfill_iowa_code_edition data/raw/iowa_code_2025.json

The newer edition must already be registered as an Edition row (see
``register_edition``) so this one has a date to anchor behind. ``--as-of``
defaults to Jan 1 of the edition year and must fall strictly before the next
(newer) edition's as-of date. Backfilled versions are written ``approved`` and
without embeddings — historical editions are for diffing/display, not search.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.corpus.models import Edition, ReviewStatus
from apps.ingestion_iowa_code.backfill import backfill_edition
from apps.ingestion_iowa_code.parser import ParseError, parse_probe_json
from apps.ingestion_iowa_code.writer import get_iowa_code_source, persist_raw_input


class Command(BaseCommand):
    help = "Backfill a prior Iowa Code edition behind the current data."

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str)
        parser.add_argument("--year", type=int, default=None, help="Edition year. Defaults to the JSON's code_year.")
        parser.add_argument("--as-of", type=str, default=None, help="ISO as-of date. Defaults to <year>-01-01.")
        parser.add_argument("--label", type=str, default=None)
        parser.add_argument(
            "--review-status",
            type=str,
            default=ReviewStatus.APPROVED,
            choices=[c[0] for c in ReviewStatus.choices],
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and compute the backfill report, then roll back.",
        )

    def handle(self, *args, **opts):
        json_path = Path(opts["json_path"])
        if not json_path.exists():
            raise CommandError(f"file not found: {json_path}")

        payload_bytes = json_path.read_bytes()
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
            parsed = parse_probe_json(payload)
        except (json.JSONDecodeError, ParseError) as e:
            raise CommandError(f"could not parse {json_path}: {e}") from e

        year = opts["year"] or parsed.code_year
        as_of = (
            dt.date.fromisoformat(opts["as_of"]) if opts["as_of"] else dt.date(year, 1, 1)
        )
        source = get_iowa_code_source()

        # The edition immediately newer than this one anchors the backfill.
        newer = (
            Edition.objects.filter(source=source, as_of_date__gt=as_of)
            .order_by("as_of_date")
            .first()
        )
        if newer is None:
            raise CommandError(
                f"no registered edition newer than {as_of}. Register the current "
                f"edition first, e.g.\n  python manage.py register_edition "
                f"--source iowa-code --year 2026 --as-of 2026-04-30"
            )

        self.stdout.write(
            f"Parsed {len(parsed.chapters)} chapter(s), "
            f"{sum(len(c.sections) for c in parsed.chapters)} section(s) "
            f"(code year {parsed.code_year}); inserting edition {year} as of {as_of}, "
            f"behind {newer.label} ({newer.as_of_date})."
        )

        report = backfill_edition(
            parsed=parsed,
            source=source,
            as_of=as_of,
            next_as_of=newer.as_of_date,
            review_status=opts["review_status"],
            dry_run=opts["dry_run"],
        )
        self._print_report(report)

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — rolled back, no writes."))
            return

        Edition.objects.update_or_create(
            source=source,
            year=year,
            defaults={
                "label": opts["label"] or f"{source.name} {year}",
                "as_of_date": as_of,
            },
        )
        storage_dir = Path(settings.BASE_DIR) / "data" / "raw"
        persist_raw_input(
            payload_bytes=payload_bytes,
            source_kind="probe_json",
            code_year=parsed.code_year,
            fetched_from=str(json_path),
            storage_dir=storage_dir,
            notes=f"backfill_iowa_code_edition {year}: {json.dumps(report.as_dict())}",
        )
        self.stdout.write(
            self.style.SUCCESS(f"Backfilled edition {year}. Registered as an Edition row.")
        )

    def _print_report(self, report):
        for k, v in report.as_dict().items():
            self.stdout.write(f"  {k}: {v}")
