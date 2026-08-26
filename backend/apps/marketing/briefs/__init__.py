"""Data-brief export pipeline (see DATA_BRIEFS.md / DATA_BRIEFS_PLAN.md).

One module per brief plus shared helpers. Each brief module exposes
``SLUG`` and ``build_snapshot(as_of) -> dict``; the registry below is what
``manage.py export_data_brief <name>`` dispatches on. The snapshot JSON is
committed into marketing-frontend/content/data/ — deploy is the publish
step, and the git diff of a re-export is the review.
"""

from __future__ import annotations

from . import most_cited_cases

BRIEFS = {
    "most_cited_cases": most_cited_cases,
}
