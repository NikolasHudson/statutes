"""Data brief 001 — the workhorse cases of Iowa law.

Builds the frozen JSON snapshot behind /data/most-cited-cases: the fifty
most-cited Iowa cases (figure 1, from the opinion→opinion citation graph)
and the thirty U.S. Supreme Court cases Iowa courts cite most (figure 2,
from bare official U.S. Reports citations in opinion text).

Counting decisions that shape the numbers, both documented on the page:

* Figure 1 counts citation edges, and every opinion (majority, special
  concurrence, dissent) counts separately. Edges point at *opinion* nodes;
  the caption, filing date, and court live on the parent decision node.
* Figure 2 counts distinct citing opinions per (volume, page) of the
  official cite. Opinions citing only a parallel reporter (S. Ct. / L. Ed.)
  are not counted — the figures are deliberately conservative.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from apps.corpus.models import CrossReference, Node

from .names import (
    CATEGORIES,
    SCOTUS_CASES,
    SCOTUS_CATEGORIES,
    categorize,
    parse_us_cite,
    shorten,
)
from .packing import Bubble, check_invariants, fit_label, pack

SLUG = "most-cited-cases"
BRIEF_NO = 1

# Figure geometry — viewBox sizes, packing fill ratios, and the label-size
# ceiling are design constants from the approved mockup. fig2's ceiling is a
# point higher because its labels are single surnames.
FIG1 = {"id": "iowa-fifty", "viewbox": (1000, 660), "fill": 0.54, "fs_max": 19.0, "top": 50}
FIG2 = {"id": "scotus-thirty", "viewbox": (1000, 560), "fill": 0.53, "fs_max": 20.0, "top": 30}

# Editorial display names win over whatever the upstream metadata calls the
# court ("Supreme Court of Iowa" et al.) — the page style is fixed.
_COURT_NAMES = {
    "iowa": "Iowa Supreme Court",
    "iowactapp": "Iowa Court of Appeals",
}


class MissingScotusEntry(Exception):
    """A top-ranked federal cite has no SCOTUS_CASES entry.

    Deliberately fatal: a refresh that promotes a new case into the top
    thirty must stop here so a human adds the (name, label, year, category)
    entry — that review is the point of the frozen-snapshot workflow.
    """


def _iowa_top_cases(limit: int) -> list[dict]:
    """Rank decisions by citing opinions via the caselaw_graph edges."""
    rows = (
        CrossReference.objects.filter(
            source="caselaw_graph",
            to_node__isnull=False,
            to_node__parent__isnull=False,
        )
        .values("to_node__parent")
        .annotate(n=Count("id"))
        .order_by("-n", "to_node__parent")[:limit]
    )
    parents = {r["to_node__parent"]: r["n"] for r in rows}
    nodes = {
        n.id: n
        for n in Node.objects.filter(id__in=parents).only(
            "id", "heading", "source_metadata"
        )
    }
    out = []
    for pid, cites in sorted(parents.items(), key=lambda kv: (-kv[1], kv[0])):
        md = nodes[pid].source_metadata
        # Ingestion writes the caption to both places; heading is the
        # backstop for rows that predate the metadata key.
        caption = md.get("case_name") or md.get("case_name_full") or nodes[pid].heading
        out.append(
            {
                "name": shorten(caption),
                "full": caption,
                "year": str(md.get("date_filed") or "")[:4],
                "court": _COURT_NAMES.get(
                    md.get("court_id", ""),
                    md.get("court_name") or md.get("court_id", ""),
                ),
                "cites": cites,
                "cat": categorize(caption),
            }
        )
    return out


def _scotus_top_cases(limit: int) -> list[dict]:
    """Rank U.S. Reports cites by distinct citing Iowa opinions."""
    citing: dict[tuple[int, int], set[int]] = defaultdict(set)
    qs = (
        CrossReference.objects.filter(
            source="caselaw_link",
            to_node__isnull=True,
            external_text__regex=r"^\d{1,3} U\.S\. \d",
        )
        .values_list("from_version_id", "external_text")
        .iterator(chunk_size=5000)
    )
    for from_version_id, text in qs:
        cite = parse_us_cite(text)
        if cite:
            citing[cite].add(from_version_id)

    ranked = sorted(citing.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:limit]
    missing = [cite for cite, _ in ranked if cite not in SCOTUS_CASES]
    if missing:
        raise MissingScotusEntry(
            "SCOTUS_CASES needs entries for: "
            + ", ".join(f"{v} U.S. {p}" for v, p in missing)
        )
    out = []
    for (vol, page), versions in ranked:
        name, label, year, cat = SCOTUS_CASES[(vol, page)]
        out.append(
            {
                "name": name,
                "full": f"{vol} U.S. {page}",
                "year": str(year),
                "court": "U.S. Supreme Court",
                "cites": len(versions),
                "cat": cat,
                "label_name": label,
            }
        )
    return out


def _figure(spec: dict, categories: dict, cases: list[dict]) -> dict:
    width, height = spec["viewbox"]
    bubbles = [
        Bubble(
            key=str(i + 1),
            weight=c["cites"],
            name=c["name"],
            count_text=f"{c['cites']:,}",
            label_name=c.get("label_name"),
        )
        for i, c in enumerate(cases)
    ]
    pack(bubbles, width, height, spec["fill"])
    check_invariants(bubbles, width, height)
    for b in bubbles:
        fit_label(b, spec["fs_max"])

    by_key = {b.key: b for b in bubbles}
    out_bubbles = []
    for i, c in enumerate(cases):
        b = by_key[str(i + 1)]
        out_bubbles.append(
            {
                "rank": i + 1,
                "name": c["name"],
                "full": c["full"],
                "year": c["year"],
                "court": c["court"],
                "cites": c["cites"],
                "cat": c["cat"],
                "x": round(b.x, 2),
                "y": round(b.y, 2),
                "r": round(b.r, 2),
                "label": b.label,
                "fs": b.fs,
                "count_label": b.count_label,
            }
        )
    return {
        "id": spec["id"],
        "viewbox": list(spec["viewbox"]),
        "categories": categories,
        "bubbles": out_bubbles,
    }


def build_snapshot(as_of: str) -> dict:
    edges = CrossReference.objects.filter(
        source="caselaw_graph", to_node__isnull=False
    ).count()
    decisions = Node.objects.filter(
        source__slug="iowa-caselaw", node_type__key="decision"
    ).count()
    return {
        "slug": SLUG,
        "brief_no": BRIEF_NO,
        "as_of": as_of,
        "totals": {"edges": edges, "decisions": decisions},
        "figures": [
            _figure(FIG1, CATEGORIES, _iowa_top_cases(FIG1["top"])),
            _figure(FIG2, SCOTUS_CATEGORIES, _scotus_top_cases(FIG2["top"])),
        ],
    }
