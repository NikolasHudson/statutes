"""Ingest a scraped Iowa Acts session probe JSON into the corpus tables.

    python manage.py ingest_iowa_acts data/raw/acts_probe_2024.json
    python manage.py ingest_iowa_acts data/raw/acts_probe_2024.json --dry-run
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ingestion_iowa_acts.writer import apply_session, persist_raw_input


class Command(BaseCommand):
    help = "Ingest an Iowa Acts probe JSON into the corpus tables."

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str)
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be written without writing.",
        )

    def handle(self, *args, **opts):
        json_path = Path(opts["json_path"])
        if not json_path.exists():
            raise CommandError(f"file not found: {json_path}")

        payload_bytes = json_path.read_bytes()
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise CommandError(f"invalid JSON: {e}") from e

        for key in ("year", "ga", "session", "chapters", "amended"):
            if key not in payload:
                raise CommandError(f"payload missing {key!r} — not an acts probe?")

        n_sections = sum(len(c["sections"]) for c in payload["chapters"])
        n_edges = sum(
            len(s["edges"]) for c in payload["chapters"] for s in c["sections"]
        )
        self.stdout.write(
            f"{payload['year']} (GA {payload['ga']}, session {payload['session']}): "
            f"{len(payload['chapters'])} chapters, {n_sections} sections, "
            f"{n_edges} parser edges, {len(payload['amended'])} amended rows."
        )

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no writes."))
            return

        raw = persist_raw_input(
            payload_bytes=payload_bytes,
            source_kind="probe_json",
            code_year=payload["year"],
            fetched_from=str(json_path),
            storage_dir=Path(settings.BASE_DIR) / "data" / "raw",
            notes=f"ingest_iowa_acts from {json_path.name}",
        )
        run = apply_session(payload, raw)
        if run.validation_errors:
            for issue in run.validation_errors:
                self.stdout.write(self.style.WARNING(f"  [warn] {issue}"))
        self.stdout.write(
            self.style.SUCCESS(f"Ingest complete. Run #{run.pk} pending review.")
        )
