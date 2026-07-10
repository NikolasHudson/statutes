"""Search plumbing shared by the public browse endpoint and the authed
research endpoint.

Extracted verbatim from ``apps.api.browse`` so both surfaces build the same
result rows / snippets / citation resolution — the public endpoint stays
byte-identical while ``/api/research/search`` reuses the pieces. Keep this
module free of router imports so it can't create cycles.
"""

from __future__ import annotations

import html
import re

from apps.corpus.models import Node, ReporterCitation

# Public browse search is keyword-only (FTS + trigram, RRF-fused) — no vector
# embeddings and no reranker, so an unauthenticated box can't run up a Voyage
# bill and stays instant. Semantic retrieval lives behind the authenticated
# surfaces (chat, /api/research/search), not here.
SEARCH_LIMIT_DEFAULT = 10
SEARCH_LIMIT_MAX = 50
# Don't fire a corpus query on a stray keystroke / single letter.
SEARCH_MIN_QUERY_LEN = 2
SNIPPET_CHARS = 240
# How deep pagination can reach: the fused candidate pool is capped here, so the
# last reachable page is ~SEARCH_FUSED_MAX/limit (less for caselaw, which
# over-fetches to survive per-decision dedup). Exhaustive caselaw browsing is
# what /api/browse/cases is for.
SEARCH_FUSED_MAX = 200


def _citation(node: Node) -> str:
    abbr = node.source.citation_abbreviation
    if node.source.slug == "iowa-admin-code":
        # IAC cites carry a tier sigil: rules "Iowa Admin. Code r. 441—65.2",
        # chapters "ch. 441—65"; the agency tier is just the bare number.
        sigil = {"rule": "r. ", "chapter": "ch. "}.get(node.node_type.key, "")
        return f"{abbr} {sigil}{node.path}"
    return f"{abbr} {node.path}".strip()


def _search_snippet(body: str, query: str) -> str:
    """A ~240-char excerpt centered on the first query-term hit, so a result
    row shows *why* it matched rather than always the section's opening words.
    Falls back to a head excerpt when no term is found (e.g. a pure trigram
    fuzzy match).

    The returned text is HTML-escaped so the snippet can never carry markup
    regardless of how the client renders it — defense in depth alongside the
    client rendering it as plain text (no markup is ever emitted here)."""
    body = " ".join(body.split())
    if len(body) <= SNIPPET_CHARS:
        return html.escape(body)

    lowered = body.lower()
    pos = -1
    for term in (t for t in query.lower().split() if len(t) >= 3):
        pos = lowered.find(term)
        if pos != -1:
            break

    if pos == -1:
        return html.escape(body[: SNIPPET_CHARS - 1].rsplit(" ", 1)[0].rstrip()) + "…"

    start = max(0, pos - SNIPPET_CHARS // 3)
    end = min(len(body), start + SNIPPET_CHARS)
    snippet = body[start:end]
    if start > 0:
        snippet = "…" + snippet.split(" ", 1)[-1]
    if end < len(body):
        snippet = snippet.rsplit(" ", 1)[0] + "…"
    return html.escape(snippet.strip())


def _search_row(
    node: Node, body_text: str, query: str, *, exact: bool = False
) -> dict:
    """Browse-shaped result row. ``kind`` discriminates how the UI opens the hit:
    a ``"case"`` row routes to ``/cases/<case_id>`` (the decision page — an
    opinion hit resolves to its parent decision, a head-matter hit is the
    decision itself), while ``"code"``/``"rule"`` rows open in the section reader
    via ``node_id``. ``body_text`` is passed in (the search hit already carries
    it) to avoid a per-row version query."""
    parent = node.parent
    slug = node.source.slug
    if slug == "iowa-caselaw":
        kind = "case"
        # The /cases page is keyed by the DECISION node; opinion hits point at
        # their parent decision, a head-matter hit IS the decision.
        decision = parent if node.node_type.key == "opinion" else node
        case_id = decision.id if decision is not None else node.id
        case_name = decision.heading if decision is not None else node.heading
        dmd = decision.source_metadata if decision is not None else {}
        court_name = dmd.get("court_name", "")
        date_filed = dmd.get("date_filed", "")
        citations = list(dmd.get("citations", []))
    else:
        kind = {
            "iowa-court-rules": "rule",
            "iowa-admin-code": "admin",
        }.get(slug, "code")
        case_id = None
        case_name = None
        court_name = ""
        date_filed = ""
        citations = []
    return {
        "node_id": node.id,
        "kind": kind,
        "case_id": case_id,
        "case_name": case_name,
        # Caselaw display meta (empty for statutes/rules).
        "court_name": court_name,
        "date_filed": date_filed,
        # This case's own reporter citation(s), e.g. ["223 N.W.2d 270", …].
        "citations": citations,
        "type": node.node_type.label_singular,
        "citation": _citation(node),
        "source": node.source.name,
        "source_slug": slug,
        "chapter": (
            None
            if kind == "case"
            # IAC chapter ordinals ("1") are meaningless without their agency
            # prefix — show the full path ("441—65") instead.
            else {
                "ordinal": parent.path
                if slug == "iowa-admin-code"
                else (parent.ordinal or parent.path),
                "heading": parent.heading,
            }
            if parent is not None
            else None
        ),
        "heading": node.heading,
        "snippet": _search_snippet(body_text or "", query),
        "exact": exact,
    }


def _normalize_fts_query(q: str) -> str:
    """Map user-typed UPPERCASE boolean operators to ``websearch_to_tsquery``
    syntax so the operators the UI advertises actually work: ``AND`` → implicit
    (space), ``OR`` → ``or``, ``NOT foo`` → ``-foo``. Lowercase ``or`` / ``-`` /
    ``"phrases"`` are already understood by websearch and pass through. Only
    whole-word UPPERCASE operators are touched, so ordinary text (e.g. a party
    name) is left alone."""
    q = re.sub(r"\bNOT\s+", "-", q)  # NOT foo -> -foo
    q = re.sub(r"\bAND\b", " ", q)  # space is implicit AND in websearch
    q = re.sub(r"\bOR\b", " or ", q)  # websearch OR
    return " ".join(q.split())


# A free-text reporter citation, e.g. "998 N.W.2d 646" -> (volume, reporter,
# page). Reporter is the middle run; volume and page are the bounding integers
# (page may carry a trailing letter).
_REPORTER_CITE_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s+(\d+[A-Za-z]?)\s*$")


def _resolve_reporter_citation(q: str) -> int | None:
    """Resolve a reporter-citation query (e.g. "998 N.W.2d 646") to the decision
    Node it names. Returns None when the query isn't a reporter cite, doesn't
    resolve, or is ambiguous (one triple naming >1 case — never guess, matching
    ReporterCitation's own policy)."""
    m = _REPORTER_CITE_RE.match(q)
    if not m:
        return None
    volume, reporter, page = m.group(1), m.group(2).strip(), m.group(3)
    ids = list(
        ReporterCitation.objects.filter(
            reporter=reporter, volume=volume, page=page, to_node__isnull=False
        )
        .values_list("to_node_id", flat=True)
        .distinct()[:2]
    )
    return ids[0] if len(ids) == 1 else None


# Friendly ``doc_type`` aliases the advanced-search UI sends, mapped to source
# slugs. The bare ``source`` slug still wins when both are given (in-context
# scoped search passes it directly); ``all``/unknown leaves scope unset.
_DOC_TYPE_SLUG = {
    "code": "iowa-code",
    "statutes": "iowa-code",
    "rules": "iowa-court-rules",
    "cases": "iowa-caselaw",
    "caselaw": "iowa-caselaw",
    "admin": "iowa-admin-code",
    "admin_code": "iowa-admin-code",
    "regulations": "iowa-admin-code",
}
