"""Scrape the Iowa Administrative Code into a probe-JSON file.

    python manage.py scrape_iowa_admin_code --out data/raw/iac_probe.json
    python manage.py scrape_iowa_admin_code --agency 441 --agency 191 --out /tmp/iac.json
    python manage.py scrape_iowa_admin_code --pub-date 07-08-2026 --out data/raw/iac.json

Politeness: reuses the Iowa Code Fetcher (1s global rate-limit, on-disk cache),
so re-runs are cheap and only un-cached chapters touch the network. Scraping the
whole IAC is ~3k requests — run it off-hours.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ingestion_iowa_admin_code.scraper import scrape_iowa_admin_code


class Command(BaseCommand):
    help = "Scrape the Iowa Administrative Code (DOCX per chapter) into probe JSON."

    def add_arguments(self, parser):
        parser.add_argument("--out", type=str, required=True, help="Output JSON path.")
        parser.add_argument(
            "--agency", action="append", default=None,
            help="Limit to these agency ids (repeatable). Default: all agencies.",
        )
        parser.add_argument(
            "--pub-date", type=str, default=None,
            help="Publication date MM-DD-YYYY. Default: current live edition.",
        )
        parser.add_argument("--rate-limit", type=float, default=1.0)
        parser.add_argument(
            "--cache-dir", type=str, default=None,
            help="Fetch cache dir. Default: data/raw/iac_cache under BASE_DIR.",
        )

    def handle(self, *args, **opts):
        cache_dir = Path(
            opts["cache_dir"] or Path(settings.BASE_DIR) / "data" / "raw" / "iac_cache"
        )

        def progress(agency, chapter, kind, detail):
            if kind == "chapter_ok":
                self.stdout.write(f"  {agency}—ch.{chapter}: {detail}")
            elif kind in ("chapter_failed", "agency_failed"):
                self.stdout.write(self.style.WARNING(f"  {agency} {chapter or ''}: {kind} — {detail}"))

        result = scrape_iowa_admin_code(
            cache_dir=cache_dir,
            pub_date=opts["pub_date"],
            only_agencies=opts["agency"],
            rate_limit_seconds=opts["rate_limit"],
            progress=progress,
        )

        out_path = Path(opts["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

        s = result["summary"]
        self.stdout.write(self.style.SUCCESS(
            f"Scraped pub_date={result['pub_date']}: {s['agencies_scraped']} agencies, "
            f"{s['chapters_scraped']} chapters, {s['rules_scraped']} rules, "
            f"{s['failures']} failures → {out_path}"
        ))
        if result["failures"]:
            self.stdout.write(self.style.WARNING(
                f"{len(result['failures'])} fetch/parse failures recorded in the JSON."
            ))
