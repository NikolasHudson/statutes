"""Edition comparison: what changed between two published editions.

An Edition is a named as-of date over the append-only NodeVersion timeline
(see ``apps.corpus.models.Edition``). Because a new version row is only ever
created when a section's body actually changed, comparing two editions is a
matter of *row identity*: resolve which version is effective at each edition's
as-of date and check whether it is the same row.

    same row at both dates           -> unchanged
    a row at ``to`` but none at ``from`` -> added
    a row at ``from`` but none at ``to`` -> repealed
    different rows                    -> amended

The summary therefore needs no body text at all — only (id, node_id,
effective_from, effective_to) — which keeps a whole-corpus diff cheap. Body
text is loaded only for a single-section diff (``section_diff``).
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field

from apps.corpus.models import Edition, Node, NodeVersion, ReviewStatus, Source


@dataclass
class NodeRef:
    node_id: int
    path: str
    citation: str
    heading: str
    chapter: str  # chapter path prefix, for grouping in the UI


@dataclass
class ComparisonSummary:
    source_slug: str
    from_year: int
    to_year: int
    from_as_of: dt.date
    to_as_of: dt.date
    unchanged: int = 0
    added: list[NodeRef] = field(default_factory=list)
    repealed: list[NodeRef] = field(default_factory=list)
    amended: list[NodeRef] = field(default_factory=list)
    covered_chapters: int = 0  # chapters with prior-edition data loaded

    @property
    def counts(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "amended": len(self.amended),
            "repealed": len(self.repealed),
            "unchanged": self.unchanged,
        }


def get_edition(source: Source, year: int) -> Edition:
    return Edition.objects.get(source=source, year=year)


def _version_at(versions: list[dict], on_date: dt.date) -> dict | None:
    """The version row effective on ``on_date`` ([effective_from, effective_to))."""
    best: dict | None = None
    for v in versions:
        if v["effective_from"] <= on_date and (
            v["effective_to"] is None or v["effective_to"] > on_date
        ):
            if (
                best is None
                or v["effective_from"] > best["effective_from"]
                or (v["effective_from"] == best["effective_from"] and v["id"] > best["id"])
            ):
                best = v
    return best


def compare_editions(
    source: Source, from_year: int, to_year: int, *, include_pending: bool = False
) -> ComparisonSummary:
    from_ed = get_edition(source, from_year)
    to_ed = get_edition(source, to_year)
    summary = ComparisonSummary(
        source_slug=source.slug,
        from_year=from_year,
        to_year=to_year,
        from_as_of=from_ed.as_of_date,
        to_as_of=to_ed.as_of_date,
    )

    nodes = {
        n.id: n
        for n in Node.objects.filter(
            source=source, node_type__key="section"
        ).select_related("source", "node_type")
    }

    vq = NodeVersion.objects.filter(
        node__source=source, node__node_type__key="section"
    )
    if not include_pending:
        vq = vq.filter(review_status=ReviewStatus.APPROVED)

    by_node: dict[int, list[dict]] = defaultdict(list)
    for v in vq.values("id", "node_id", "effective_from", "effective_to"):
        by_node[v["node_id"]].append(v)

    # Resolve the version effective at each edition for every section first, so
    # we know which chapters actually have prior-edition ("from") data loaded.
    resolved: list[tuple[Node, dict | None, dict | None]] = []
    covered_chapters: set[str] = set()
    for nid, node in nodes.items():
        versions = by_node.get(nid, [])
        fv = _version_at(versions, from_ed.as_of_date)
        tv = _version_at(versions, to_ed.as_of_date)
        resolved.append((node, fv, tv))
        if fv is not None:
            covered_chapters.add(node.path.split(".", 1)[0])
    summary.covered_chapters = len(covered_chapters)

    for node, fv, tv in resolved:
        if fv is None and tv is None:
            continue
        if fv is None:
            # "Added" only makes sense where the prior edition is loaded —
            # otherwise an unloaded chapter would report all its sections as
            # added. amended/repealed need a prior version, so are immune.
            if node.path.split(".", 1)[0] in covered_chapters:
                summary.added.append(_ref(node))
        elif tv is None:
            summary.repealed.append(_ref(node))
        elif fv["id"] == tv["id"]:
            summary.unchanged += 1
        else:
            summary.amended.append(_ref(node))

    for bucket in (summary.added, summary.repealed, summary.amended):
        bucket.sort(key=_ref_sort_key)
    return summary


def _ref(node: Node) -> NodeRef:
    return NodeRef(
        node_id=node.id,
        path=node.path,
        citation=f"{node.source.citation_abbreviation} {node.path}".strip(),
        heading=node.heading,
        chapter=node.path.split(".", 1)[0],
    )


def _ref_sort_key(ref: NodeRef) -> tuple:
    parts = []
    for chunk in ref.path.replace(":", ".").split("."):
        head = "".join(c for c in chunk if c.isdigit())
        tail = "".join(c for c in chunk if not c.isdigit())
        parts.append((int(head) if head else 0, tail))
    return tuple(parts)


# --------------------------------------------------------------------------
# Single-section diff
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\S+|\s+")


def diff_segments(a: str, b: str) -> list[dict]:
    """Word-level diff of ``a`` (from) vs ``b`` (to) as renderable segments.

    Each segment is ``{"op": "equal"|"insert"|"delete", "text": str}``. A
    replacement is emitted as a delete followed by an insert so the UI only
    needs three colors.
    """
    from difflib import SequenceMatcher

    at = _TOKEN_RE.findall(a)
    bt = _TOKEN_RE.findall(b)
    segments: list[dict] = []

    def emit(op: str, text: str) -> None:
        if not text:
            return
        if segments and segments[-1]["op"] == op:
            segments[-1]["text"] += text
        else:
            segments.append({"op": op, "text": text})

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, at, bt).get_opcodes():
        if tag == "equal":
            emit("equal", "".join(at[i1:i2]))
        elif tag == "delete":
            emit("delete", "".join(at[i1:i2]))
        elif tag == "insert":
            emit("insert", "".join(bt[j1:j2]))
        else:  # replace
            emit("delete", "".join(at[i1:i2]))
            emit("insert", "".join(bt[j1:j2]))
    return segments


def section_diff(
    node: Node, from_year: int, to_year: int, *, include_pending: bool = False
) -> dict:
    """From/to body text for one section plus a word-level diff."""
    source = node.source
    from_ed = get_edition(source, from_year)
    to_ed = get_edition(source, to_year)

    from .lookups import get_section_at

    fv = get_section_at(node, from_ed.as_of_date, include_pending=include_pending)
    tv = get_section_at(node, to_ed.as_of_date, include_pending=include_pending)
    from_text = fv.body_text if fv else ""
    to_text = tv.body_text if tv else ""

    return {
        "node_id": node.id,
        "path": node.path,
        "citation": f"{source.citation_abbreviation} {node.path}".strip(),
        "heading": node.heading,
        "from": {
            "year": from_year,
            "as_of": from_ed.as_of_date.isoformat(),
            "present": fv is not None,
            "body_text": from_text,
        },
        "to": {
            "year": to_year,
            "as_of": to_ed.as_of_date.isoformat(),
            "present": tv is not None,
            "body_text": to_text,
        },
        "changed": (fv.id if fv else None) != (tv.id if tv else None),
        "diff": diff_segments(from_text, to_text),
    }
