"""Tool implementations for the MCP server.

The *pure* tool bodies — JSON-able in, JSON-able out — now live in
``apps.corpus.services``:

* direct-lookup / verification tools + their serializers:
  ``apps.corpus.services.corpus_tools``
* the search/retrieval pipeline (hybrid search + rerank + assembly):
  ``apps.corpus.services.retrieval`` (``retrieve_context``)

This module is the thin MCP adapter: it re-exports the corpus tools under the
names ``apps.mcp_server.server`` (and the tests) already import, and it owns
``search_statutes_tool`` — the MCP-shaped wrapper around ``retrieve_context``.

Keeping the bodies in ``apps.corpus`` lets the human-facing chat surface
(``apps.api.chat``) import them from corpus too, instead of from
``apps.mcp_server`` — removing the old backwards ``apps.api → apps.mcp_server``
dependency.

We deliberately do NOT register these with FastMCP here, so they can be
imported and unit-tested without spinning up a full server.

Every response includes ``official_url``, an ``as_of_date`` stamp, and
``effective_from`` / ``effective_to`` on each version, so an LLM client can
never accidentally cite stale text. Ambiguity rule: when a citation doesn't
resolve unambiguously we return the candidate list — never a silent substitute.
"""

from __future__ import annotations

from typing import Any

# Re-export the corpus-owned tool bodies under the names the MCP server
# registration (apps.mcp_server.server) and the tests import as ``tools.X``.
from apps.corpus.services.corpus_tools import (  # noqa: F401
    _today,
    audit_brief_tool,
    get_cross_references_tool,
    get_definitions_tool,
    get_section_at_date_tool,
    get_version_history_tool,
    list_recent_amendments_tool,
    lookup_citation_tool,
    validate_citations_tool,
    verify_quote_tool,
)
from apps.corpus.services.retrieval import retrieve_context


# Candidate pool pulled from hybrid search before reranking. A cross-encoder can
# only promote an on-point hit that is *in* the pool it sees, so the reranked
# tool over-fetches well past the handful it will return. 50 is the low end of the
# reported reranker sweet spot (and the cap hybrid_search hits here).
SEARCH_RERANK_POOL = 50

# Per-document char cap when reranking. A caselaw hit's body is a whole opinion
# (100k+ chars); feeding 50 of those to the reranker would blow its per-request
# token budget. The reranker truncates anyway, and an opinion's holding/syllabus
# sits near the top, so a prefix carries the conceptual signal. Mirrors the
# eval harness (RERANK_DOC_CHARS).
SEARCH_RERANK_DOC_CHARS = 8000


def search_statutes_tool(
    query: str,
    *,
    limit: int = 20,
    use_vector: bool = True,
    source_slug: str | None = None,
    rerank: bool = False,
) -> dict[str, Any]:
    """Hybrid search — FTS + trigram + vector, RRF-fused (dense-dominant weights).

    ``source_slug`` (e.g. ``"iowa-court-rules"``) scopes the search to a
    single corpus; ``None`` searches everything.

    ``rerank`` adds a Voyage cross-encoder pass: pull a wider candidate pool
    (``SEARCH_RERANK_POOL``) from hybrid search, re-score each against the query,
    and keep the top ``limit``. RRF fusion is a *recall* mechanism — its fused
    score doesn't measure how well a hit answers the query — so for an agent that
    will act on the top result, the reranker is what turns recall into precision.
    Off by default so the chat endpoint (which reranks itself, with body
    enrichment) doesn't double-rerank; the MCP server turns it on so external
    agents get reranked results.

    Delegates to ``retrieve_context`` (the shared pipeline) and serializes the
    passages into the MCP hit shape: ``{node, snippet, score, component_scores}``.
    """
    if not query or not query.strip():
        return {
            "query": query,
            "hits": [],
            "as_of_date": _today(),
            "error": "query must not be empty",
        }
    pool = SEARCH_RERANK_POOL if rerank else min(limit, 50)
    ctx = retrieve_context(
        query,
        source_slug=source_slug,
        use_vector=use_vector,
        candidate_pool=min(pool, 50),
        display_limit=limit,
        rerank=rerank,
        rerank_doc_chars=SEARCH_RERANK_DOC_CHARS,
        enrich_bodies=False,
    )
    return {
        "query": query,
        "hits": [
            {
                "node": p.node_dict,
                "snippet": p.snippet,
                "score": p.score,
                "component_scores": p.component_scores,
            }
            for p in ctx.passages
        ],
        "as_of_date": ctx.as_of_date,
    }
