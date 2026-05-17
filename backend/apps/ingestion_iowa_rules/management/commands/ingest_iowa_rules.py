"""End-to-end Iowa Court Rules ingest from a probe-JSON file.

    python manage.py ingest_iowa_rules "Iowa Court Rules/probe.json"
    python manage.py ingest_iowa_rules "Iowa Court Rules/probe.json" --dry-run
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ingestion_iowa_rules.differ import diff_against_db
from apps.ingestion_iowa_rules.parser import ParseError, parse_probe_json
from apps.ingestion_iowa_rules.validators import (
    ValidationError,
    ValidationIssue,
    validate,
)
from apps.ingestion_iowa_rules.writer import (
    apply_changeset,
    get_iowa_court_rules_source,
    persist_raw_input,
)


class Command(BaseCommand):
    help = "Ingest an Iowa Court Rules probe JSON into the corpus tables."

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse, diff, validate — but do not write.",
        )
        parser.add_argument(
            "--effective-from",
            type=str,
            default=None,
            help="ISO date for the new versions. Defaults to the probe edition date.",
        )
        parser.add_argument(
            "--source-kind",
            type=str,
            default="probe_json",
            help="RawIngestion.source_kind value.",
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

        try:
            parsed = parse_probe_json(payload)
        except ParseError as e:
            raise CommandError(f"parse error: {e}") from e

        n_rules = sum(len(c.rules) for c in parsed.chapters)
        n_reserved = sum(1 for c in parsed.chapters if c.reserved)
        self.stdout.write(
            f"Parsed {len(parsed.chapters)} chapter(s) "
            f"({n_reserved} reserved), {n_rules} rule(s) "
            f"(edition {parsed.edition_date.isoformat()})."
        )
        if parsed.skipped_rules:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {len(parsed.skipped_rules)} rule(s) "
                    f"(reserved placeholders / malformed numbers):"
                )
            )
            for s in parsed.skipped_rules:
                self.stdout.write(
                    f"  - chapter={s.chapter} number={s.number!r} "
                    f"reason={s.reason!r}"
                )

        source = get_iowa_court_rules_source()
        changeset = diff_against_db(parsed, source)
        self._print_summary(changeset.summary())

        try:
            warnings = validate(parsed, changeset)
        except ValidationError as e:
            self._print_issues(e.issues)
            raise CommandError("validation failed; aborting.") from e

        if warnings:
            self._print_issues(warnings)

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no writes."))
            return

        effective_from = (
            dt.date.fromisoformat(opts["effective_from"])
            if opts["effective_from"]
            else None
        )

        storage_dir = Path(settings.BASE_DIR) / "data" / "raw"
        raw = persist_raw_input(
            payload_bytes=payload_bytes,
            source_kind=opts["source_kind"],
            code_year=parsed.edition_year,
            fetched_from=str(json_path),
            storage_dir=storage_dir,
            notes=f"ingest_iowa_rules from {json_path.name}",
        )

        run = apply_changeset(
            parsed=parsed,
            changeset=changeset,
            raw=raw,
            effective_from=effective_from,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Ingest complete. Run #{run.pk} pending review.")
        )

    def _print_summary(self, summary: dict[str, int]):
        for k, v in summary.items():
            self.stdout.write(f"  {k}: {v}")

    def _print_issues(self, issues: list[ValidationIssue]):
        for issue in issues:
            style = (
                self.style.ERROR
                if issue.severity == "error"
                else self.style.WARNING
            )
            self.stdout.write(
                style(
                    f"[{issue.severity}] {issue.code} ({issue.path}): "
                    f"{issue.message}"
                )
            )
