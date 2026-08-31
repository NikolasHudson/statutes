"""Export a /data/coverage/<unit> snapshot into the marketing frontend.

    python manage.py export_coverage_snapshot iowa
    python manage.py export_coverage_snapshot eighth-circuit --out /tmp/preview

Same contract as export_data_brief: the coverage pages render from frozen JSON
committed under marketing-frontend/content/data/, so their numbers never
drift. The export is deterministic (stable ordering); re-running against
unchanged data produces an empty git diff, and a non-empty diff is the review
step before a refresh is committed and deployed.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count

from apps.corpus.models import CrossReference, Edition, Node

DEFAULT_OUT = Path(settings.BASE_DIR).parent / "marketing-frontend" / "content" / "data"

# Federal court_name → display bucket. Strict: an unmapped name fails the
# export, so a corpus refresh that introduces a new court is reviewed here
# instead of silently landing in the wrong row. The Iowa page folds these into
# coarser rows than the Eighth Circuit page, so the buckets are the fine ones
# and each unit's builder groups them.
_FEDERAL_BUCKETS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Court of Appeals for the Eighth Circuit$"), "ca8"),
    (re.compile(r"Bankruptcy Appellate Panel"), "bap"),
    (re.compile(r"^District Court, (N\.D\.|S\.D\.) Iowa$"), "iowa_district"),
    (re.compile(r"^United States Bankruptcy Court, (N\.D\.|S\.D\.) Iowa$"), "iowa_bankruptcy"),
    (re.compile(r"^U\.S\. Circuit Court"), "historical"),
    (re.compile(r"^District Court, D\. Iowa$"), "historical"),
]

_IOWA_COURT_LABELS = {
    "Supreme Court of Iowa": "supreme",
    "Court of Appeals of Iowa": "appeals",
}


def _unit_counts(slug: str) -> dict[str, int]:
    """{node_type key: count} for one source."""
    rows = (
        Node.objects.filter(source__slug=slug)
        .values("node_type__key")
        .annotate(n=Count("id"))
    )
    return {r["node_type__key"]: r["n"] for r in rows}


def _court_rows(slug: str) -> list[dict]:
    """Per-court decision counts and date spans for a caselaw source.
    date_filed lives in source_metadata JSON; min/max over the ->> text is
    correct for ISO dates."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT n.source_metadata->>'court_name',
                   count(*),
                   min(n.source_metadata->>'date_filed'),
                   max(n.source_metadata->>'date_filed')
            FROM corpus_node n
            JOIN corpus_source s ON s.id = n.source_id
            JOIN corpus_nodetype t ON t.id = n.node_type_id
            WHERE t.key = 'decision' AND s.slug = %s
            GROUP BY 1
            ORDER BY count(*) DESC, 1
            """,
            [slug],
        )
        rows = cur.fetchall()
    if not rows:
        raise CommandError(f"{slug}: no decisions found")
    return [
        {"name": name or "", "decisions": n, "first": first, "last": last}
        for name, n, first, last in rows
    ]


def _bucketed_federal() -> dict[str, dict]:
    """Fine federal buckets, each {decisions, first, last, courts: [...]}."""
    buckets: dict[str, dict] = {}
    for row in _court_rows("federal-caselaw"):
        for pattern, key in _FEDERAL_BUCKETS:
            if pattern.search(row["name"]):
                b = buckets.setdefault(
                    key,
                    {"decisions": 0, "first": row["first"], "last": row["last"], "courts": []},
                )
                b["decisions"] += row["decisions"]
                b["first"] = min(b["first"], row["first"])
                b["last"] = max(b["last"], row["last"])
                b["courts"].append(
                    {"name": row["name"], "decisions": row["decisions"]}
                )
                break
        else:
            raise CommandError(f"unmapped federal court_name: {row['name']!r}")
    missing = {k for _, k in _FEDERAL_BUCKETS} - set(buckets)
    if missing:
        raise CommandError(f"federal buckets came back empty: {sorted(missing)}")
    return buckets


def _span_merge(*buckets: dict) -> tuple[str, str, int]:
    first = min(b["first"] for b in buckets)
    last = max(b["last"] for b in buckets)
    return first, last, sum(b["decisions"] for b in buckets)


def _acts_sessions() -> dict:
    """Session count plus year and General Assembly ranges, parsed from the
    session headings ('2019 — 88th G.A., Regular GA'). The GA ordinal is
    re-derived from the number downstream, so the source's '91th' typo never
    reaches the page."""
    headings = list(
        Node.objects.filter(
            source__slug="iowa-acts", node_type__key="session"
        ).values_list("heading", flat=True)
    )
    years, assemblies = [], []
    for h in headings:
        year = re.search(r"\b(\d{4})\b", h or "")
        ga = re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", h or "")
        if not year or not ga:
            raise CommandError(f"unparseable acts session heading: {h!r}")
        years.append(int(year.group(1)))
        assemblies.append(int(ga.group(1)))
    if not years:
        raise CommandError("no iowa-acts sessions found")
    return {
        "sessions": len(headings),
        "first_year": min(years),
        "last_year": max(years),
        "first_ga": min(assemblies),
        "last_ga": max(assemblies),
    }


def _cross_source_citations(from_slug: str, to_slug: str) -> int:
    """Resolved (internal) citation edges from one caselaw corpus into the
    other — the count behind 'stitched into the state reporter'."""
    return CrossReference.objects.filter(
        source__in=("caselaw_link", "caselaw_graph"),
        from_version__node__source__slug=from_slug,
        to_node__source__slug=to_slug,
    ).count()


def build_iowa(as_of: str) -> dict:
    code = _unit_counts("iowa-code")
    iac = _unit_counts("iowa-admin-code")
    acts = _unit_counts("iowa-acts")
    rules = _unit_counts("iowa-court-rules")

    ia_rows = _court_rows("iowa-caselaw")
    for row in ia_rows:
        if row["name"] not in _IOWA_COURT_LABELS:
            raise CommandError(f"unmapped Iowa court_name: {row['name']!r}")
    ia_first = min(r["first"] for r in ia_rows)
    ia_last = max(r["last"] for r in ia_rows)
    ia_decisions = sum(r["decisions"] for r in ia_rows)

    fed = _bucketed_federal()
    fed_first, fed_last, fed_decisions = _span_merge(*fed.values())
    # The Iowa page folds the fine buckets into its coarser shelf rows.
    fed_courts = [
        {
            "key": "ca8",
            "name": "Court of Appeals for the Eighth Circuit",
            "decisions": fed["ca8"]["decisions"],
        },
        {
            "key": "districts",
            "name": "District Courts, N.D. and S.D. Iowa",
            "decisions": fed["iowa_district"]["decisions"],
        },
        {
            "key": "bankruptcy",
            "name": "Bankruptcy courts and the Eighth Circuit BAP",
            "decisions": fed["bap"]["decisions"] + fed["iowa_bankruptcy"]["decisions"],
        },
        {
            "key": "historical",
            "name": "Historical circuit courts",
            "decisions": fed["historical"]["decisions"],
        },
    ]

    connections = {
        # Total mapped edges per extractor, resolved and unresolved alike —
        # the same counting the published /data copy uses.
        "statute_rule": CrossReference.objects.filter(source="reg_enabling").count(),
        "act_code": CrossReference.objects.filter(source="act_affects").count(),
    }

    decisions = ia_decisions + fed_decisions
    authorities = (
        code["section"] + iac["rule"] + acts["section"] + rules["rule"] + decisions
    )

    return {
        "slug": "coverage-iowa",
        "as_of": as_of,
        "totals": {
            "authorities": authorities,
            "decisions": decisions,
            "connections": sum(connections.values()),
            "sources": 6,
        },
        "iowa_code": {
            "sections": code["section"],
            "chapters": code["chapter"],
            "edition_years": sorted(
                Edition.objects.filter(source__slug="iowa-code").values_list(
                    "year", flat=True
                )
            ),
        },
        "iowa_admin_code": {
            "rules": iac["rule"],
            "chapters": iac["chapter"],
            "agencies": iac["agency"],
        },
        "iowa_acts": {
            "sections": acts["section"],
            "chapters": acts["chapter"],
            **_acts_sessions(),
        },
        "iowa_court_rules": {"rules": rules["rule"], "chapters": rules["chapter"]},
        "iowa_caselaw": {
            "decisions": ia_decisions,
            "first": ia_first,
            "last": ia_last,
            "courts": [
                {
                    "key": _IOWA_COURT_LABELS[r["name"]],
                    "name": r["name"],
                    "decisions": r["decisions"],
                }
                for r in ia_rows
            ],
        },
        "federal_caselaw": {
            "decisions": fed_decisions,
            "first": fed_first,
            "last": fed_last,
            "courts": fed_courts,
        },
        "connections": connections,
    }


def build_eighth_circuit(as_of: str) -> dict:
    fed = _bucketed_federal()
    iowa_fed_first, iowa_fed_last, iowa_fed_decisions = _span_merge(
        fed["iowa_district"], fed["iowa_bankruptcy"]
    )
    _, _, total_decisions = _span_merge(*fed.values())

    connections = {
        "federal_to_iowa": _cross_source_citations("federal-caselaw", "iowa-caselaw"),
        "iowa_to_federal": _cross_source_citations("iowa-caselaw", "federal-caselaw"),
        # Resolved edges only — an unresolved citation to an out-of-corpus
        # reporter is not part of the graph the product can traverse.
        "graph_edges": CrossReference.objects.filter(
            source__in=("caselaw_link", "caselaw_graph"), to_node__isnull=False
        ).count(),
    }

    def bucket(key: str) -> dict:
        b = fed[key]
        return {
            "decisions": b["decisions"],
            "first": b["first"],
            "last": b["last"],
        }

    return {
        "slug": "coverage-eighth-circuit",
        "as_of": as_of,
        "totals": {
            "decisions": total_decisions,
            "cross_citations": connections["federal_to_iowa"]
            + connections["iowa_to_federal"],
            # The circuit's composition is a fixed fact, not a corpus count.
            "states": 7,
        },
        "ca8": bucket("ca8"),
        "bap": bucket("bap"),
        "iowa_federal": {
            "decisions": iowa_fed_decisions,
            "first": iowa_fed_first,
            "last": iowa_fed_last,
            "courts": sorted(
                fed["iowa_district"]["courts"] + fed["iowa_bankruptcy"]["courts"],
                key=lambda c: (-c["decisions"], c["name"]),
            ),
        },
        "historical": bucket("historical"),
        "connections": connections,
    }


_UNITS = {
    "iowa": build_iowa,
    "eighth-circuit": build_eighth_circuit,
}


class Command(BaseCommand):
    help = "Export a coverage JSON snapshot for the marketing site's /data/coverage pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "unit",
            choices=sorted(_UNITS),
            help="Which coverage unit to export.",
        )
        parser.add_argument(
            "--out",
            default=str(DEFAULT_OUT),
            help="Directory the coverage-<unit>.json snapshot is written into "
            "(default: marketing-frontend/content/data/).",
        )
        parser.add_argument(
            "--as-of",
            default=None,
            help="Override the snapshot's as-of date (YYYY-MM-DD; default today). "
            "The date is editorial: it freezes with the numbers.",
        )

    def handle(self, *args, **opts):
        as_of = opts["as_of"] or datetime.date.today().isoformat()
        try:
            datetime.date.fromisoformat(as_of)
        except ValueError as exc:
            raise CommandError(f"--as-of must be YYYY-MM-DD, got {as_of!r}") from exc

        snapshot = _UNITS[opts["unit"]](as_of)

        out_dir = Path(opts["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{snapshot['slug']}.json"
        out_path.write_text(
            json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        t = snapshot["totals"]
        stats = ", ".join(f"{k} {v:,}" for k, v in t.items())
        self.stdout.write(f"{snapshot['slug']} as of {as_of}: {stats} → {out_path}")
