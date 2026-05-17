"""Scrape every chapter of the Iowa Code into a probe-JSON file.

    python manage.py scrape_iowa_code
    python manage.py scrape_iowa_code --year 2026 --output data/raw/iowa_code_2026.json
    python manage.py scrape_iowa_code --titles I,II   # restrict to certain titles
    python manage.py scrape_iowa_code --slugs 1,4,12C # only specific chapters

Caching: raw RTF bytes (and the Title index pages) are cached under
``data/raw/iowa_rtf_cache/`` keyed by sha256(URL). Re-runs are free for any
chapter already cached; pass ``--force`` to bypass the cache.

Output is the same probe-JSON shape ``ingest_iowa_code`` already understands,
so the next step after this command finishes is::

    python manage.py ingest_iowa_code <output-path>
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ingestion_iowa_code.scraper import (
    DEFAULT_USER_AGENT,
    TITLE_NUMERALS,
    Fetcher,
    enumerate_chapter_slugs,
    parse_chapter_rtf,
    scrape_iowa_code,
)


log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape every Iowa Code chapter RTF and emit a probe-JSON file."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=2026)
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Output path. Defaults to data/raw/iowa_code_<year>.json.",
        )
        parser.add_argument(
            "--cache-dir",
            type=str,
            default=None,
            help="RTF cache dir. Defaults to data/raw/iowa_rtf_cache.",
        )
        parser.add_argument(
            "--titles",
            type=str,
            default=None,
            help="Comma-separated Roman-numeral Title list (e.g. I,II,III).",
        )
        parser.add_argument(
            "--slugs",
            type=str,
            default=None,
            help=(
                "Comma-separated chapter slugs (e.g. 1,4,12C). When set, "
                "Title enumeration is skipped."
            ),
        )
        parser.add_argument(
            "--rate-limit",
            type=float,
            default=1.0,
            help="Minimum seconds between HTTP requests.",
        )
        parser.add_argument(
            "--user-agent",
            type=str,
            default=DEFAULT_USER_AGENT,
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass the on-disk cache and refetch every URL.",
        )

    def handle(self, *args, **opts):
        base = Path(settings.BASE_DIR)
        cache_dir = Path(opts["cache_dir"]) if opts["cache_dir"] else base / "data" / "raw" / "iowa_rtf_cache"
        output = Path(opts["output"]) if opts["output"] else base / "data" / "raw" / f"iowa_code_{opts['year']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)

        titles = (
            tuple(t.strip() for t in opts["titles"].split(",") if t.strip())
            if opts["titles"]
            else TITLE_NUMERALS
        )
        only_slugs = (
            [s.strip() for s in opts["slugs"].split(",") if s.strip()]
            if opts["slugs"]
            else None
        )

        # Build the fetcher up-front so we can pre-enumerate (and report a
        # chapter total) before kicking off the per-chapter loop.
        fetcher = Fetcher(
            cache_dir=cache_dir,
            rate_limit_seconds=opts["rate_limit"],
            user_agent=opts["user_agent"],
            force_refresh=opts["force"],
        )

        if only_slugs is None:
            self.stdout.write(
                f"Enumerating chapters across {len(titles)} title(s)…"
            )
            slugs = enumerate_chapter_slugs(fetcher, year=opts["year"], titles=titles)
            self.stdout.write(f"  found {len(slugs)} chapters")
        else:
            slugs = only_slugs
            self.stdout.write(f"Scraping {len(slugs)} explicit slug(s).")

        from apps.ingestion_iowa_code.scraper import (
            ScrapeResult,
            CHAPTER_RTF_URL,
        )

        result = ScrapeResult(code_year=opts["year"])
        started = time.monotonic()
        for idx, slug in enumerate(slugs, start=1):
            url = CHAPTER_RTF_URL.format(year=opts["year"], slug=slug)
            try:
                rtf = fetcher.fetch(url)
                chapter = parse_chapter_rtf(slug, rtf, year=opts["year"])
                result.chapters.append(chapter)
                self.stdout.write(
                    f"  [{idx:>3}/{len(slugs)}] {slug:<6} "
                    f"{chapter.section_count:>4} sections "
                    f"({chapter.rtf_bytes:>7,} rtf bytes)"
                )
            except Exception as e:  # noqa: BLE001
                result.failures.append({"slug": slug, "url": url, "error": str(e)})
                self.stdout.write(
                    self.style.ERROR(
                        f"  [{idx:>3}/{len(slugs)}] {slug:<6} FAILED: {e}"
                    )
                )

        elapsed = time.monotonic() - started
        output.write_text(json.dumps(result.to_json(), indent=2, ensure_ascii=False))
        total_sections = sum(c.section_count for c in result.chapters)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done in {elapsed:.1f}s. "
            f"{len(result.chapters)} chapters / {total_sections:,} sections "
            f"/ {len(result.failures)} failures."
        ))
        self.stdout.write(f"Wrote {output} ({output.stat().st_size:,} bytes)")
        if result.failures:
            self.stdout.write(
                self.style.WARNING(
                    "Re-run with --slugs <list> to retry just the failures."
                )
            )
