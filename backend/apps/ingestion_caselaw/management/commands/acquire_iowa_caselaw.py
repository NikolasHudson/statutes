"""Phase 1: stream the CourtListener bulk CSVs into an Iowa-only JSONL slice.

Read-only relative to the corpus DB. Records ``RawIngestion``/``IngestionRun``
audit rows unless ``--no-persist`` is given. Rerunnable: identical input yields
byte-identical artifacts, and content-hash dedupe short-circuits the audit rows.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...acquire import IOWA_COURT_IDS, persist_acquire_run, run_acquire

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Phase 1 acquire: CourtListener bulk CSVs → Iowa-only JSONL slice."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bulk-dir",
            required=True,
            help="Directory holding the five CourtListener bulk .csv.bz2 files.",
        )
        parser.add_argument(
            "--out-dir",
            required=True,
            help="Directory to write the Iowa JSONL artifacts into.",
        )
        parser.add_argument(
            "--export-year",
            type=int,
            required=True,
            help="Quarterly bulk export year (stored on RawIngestion.code_year).",
        )
        parser.add_argument(
            "--court",
            action="append",
            dest="courts",
            default=None,
            help=f"CourtListener court id to include (repeatable). "
            f"Default: {' '.join(IOWA_COURT_IDS)}.",
        )
        parser.add_argument(
            "--no-persist",
            action="store_true",
            help="Emit JSONL only; skip the RawIngestion/IngestionRun DB rows.",
        )

    def handle(self, *args, **opts):
        bulk_dir = Path(opts["bulk_dir"])
        out_dir = Path(opts["out_dir"])
        if not bulk_dir.is_dir():
            raise CommandError(f"--bulk-dir is not a directory: {bulk_dir}")
        courts = tuple(opts["courts"]) if opts.get("courts") else IOWA_COURT_IDS

        try:
            result = run_acquire(bulk_dir, out_dir, courts=courts)
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("acquire complete:"))
        self.stdout.write(json.dumps(result.counts, indent=2))

        if not opts["no_persist"]:
            run = persist_acquire_run(
                result, export_year=opts["export_year"], fetched_from=str(bulk_dir)
            )
            self.stdout.write(
                self.style.SUCCESS(f"recorded IngestionRun #{run.pk} (acquire)")
            )
