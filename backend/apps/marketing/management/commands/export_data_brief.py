"""Export a data-brief snapshot into the marketing frontend.

    python manage.py export_data_brief most_cited_cases
    python manage.py export_data_brief most_cited_cases --out /tmp/preview

Queries the corpus, computes the figure layout, and writes the frozen JSON
snapshot the /data pages render from. The output is deterministic (stable
ordering, rounded floats), so re-running against unchanged data produces an
empty git diff — and a *non*-empty diff is the review step before a refresh
is committed and deployed. Publication itself is the deploy (DATA_BRIEFS.md).
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.marketing.briefs import BRIEFS
from apps.marketing.briefs.most_cited_cases import MissingScotusEntry

# The monorepo location the pages read from; BASE_DIR is backend/, its
# parent is the repo root.
DEFAULT_OUT = Path(settings.BASE_DIR).parent / "marketing-frontend" / "content" / "data"


class Command(BaseCommand):
    help = "Export a data-brief JSON snapshot for the marketing site's /data pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "brief",
            choices=sorted(BRIEFS),
            help="Which brief to export (module name in apps.marketing.briefs).",
        )
        parser.add_argument(
            "--out",
            default=str(DEFAULT_OUT),
            help="Directory the <slug>.json snapshot is written into "
            "(default: marketing-frontend/content/data/).",
        )
        parser.add_argument(
            "--as-of",
            default=None,
            help="Override the snapshot's as-of date (YYYY-MM-DD; default today). "
            "The date is editorial: it freezes with the numbers.",
        )

    def handle(self, *args, **opts):
        module = BRIEFS[opts["brief"]]
        as_of = opts["as_of"] or datetime.date.today().isoformat()
        try:
            datetime.date.fromisoformat(as_of)
        except ValueError as exc:
            raise CommandError(f"--as-of must be YYYY-MM-DD, got {as_of!r}") from exc

        try:
            snapshot = module.build_snapshot(as_of)
        except MissingScotusEntry as exc:
            raise CommandError(str(exc)) from exc

        out_dir = Path(opts["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{snapshot['slug']}.json"
        out_path.write_text(
            json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        totals = snapshot["totals"]
        self.stdout.write(
            f"{snapshot['slug']} as of {as_of}: "
            f"{totals['edges']:,} edges across {totals['decisions']:,} decisions"
        )
        for fig in snapshot["figures"]:
            top = ", ".join(
                f"{b['name']} ({b['cites']:,})" for b in fig["bubbles"][:3]
            )
            labeled = sum(1 for b in fig["bubbles"] if b["label"])
            self.stdout.write(
                f"  {fig['id']}: {len(fig['bubbles'])} bubbles "
                f"({labeled} labeled) — {top}"
            )
        self.stdout.write(self.style.SUCCESS(f"Wrote {out_path}"))
