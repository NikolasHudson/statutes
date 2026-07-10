"""Scrape Iowa Acts sessions into probe JSON.

    python manage.py scrape_iowa_acts --ssid 166
    python manage.py scrape_iowa_acts --year 2024
    python manage.py scrape_iowa_acts --ga 88 --ga 89 --ga 90 --ga 91

Writes one ``acts_probe_{path}.json`` per session under data/raw/.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ingestion_iowa_code.scraper import Fetcher
from apps.ingestion_iowa_acts.scraper import enumerate_sessions, scrape_session
from apps.ingestion_iowa_acts.writer import session_path


class Command(BaseCommand):
    help = "Scrape Iowa Acts session(s) from legis.iowa.gov into probe JSON."

    def add_arguments(self, parser):
        parser.add_argument("--ssid", type=int, action="append", default=None)
        parser.add_argument("--year", type=int, action="append", default=None)
        parser.add_argument(
            "--ga", type=int, action="append", default=None,
            help="Scrape every session of this GA (repeatable).",
        )
        parser.add_argument("--out-dir", type=str, default=None)
        parser.add_argument(
            "--force-refresh", action="store_true",
            help="Bypass the on-disk fetch cache.",
        )

    def handle(self, *args, **opts):
        fetcher = Fetcher(
            cache_dir=Path(settings.BASE_DIR) / "data" / "raw" / "acts_fetch_cache",
            force_refresh=opts["force_refresh"],
        )
        sessions = enumerate_sessions(fetcher)

        wanted = [
            s
            for s in sessions
            if (opts["ssid"] and s["ssid"] in opts["ssid"])
            or (opts["year"] and s["year"] in opts["year"])
            or (opts["ga"] and s["ga"] in opts["ga"])
        ]
        if not wanted:
            raise CommandError("nothing selected — pass --ssid, --year, or --ga")

        out_dir = Path(opts["out_dir"] or Path(settings.BASE_DIR) / "data" / "raw")
        out_dir.mkdir(parents=True, exist_ok=True)

        for s in sorted(wanted, key=lambda x: x["ssid"]):
            self.stdout.write(
                f"scraping ssid={s['ssid']} ({s['year']} {s['label']}, GA {s['ga']})…"
            )
            payload = scrape_session(fetcher, s["ssid"])
            payload["year"], payload["label"] = s["year"], s["label"]
            spath = session_path(s["year"], payload["session"], s["label"])
            out = out_dir / f"acts_probe_{spath}.json"
            out.write_text(json.dumps(payload))
            n_sec = sum(len(c["sections"]) for c in payload["chapters"])
            no_rtf = sum(1 for c in payload["chapters"] if not c["enrolled_rtf"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {out.name}: {len(payload['chapters'])} chapters, "
                    f"{n_sec} sections, {len(payload['amended'])} amended rows"
                    + (f", {no_rtf} chapters WITHOUT enrolled RTF" if no_rtf else "")
                )
            )
