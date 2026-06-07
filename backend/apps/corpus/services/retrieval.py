"""Shared retrieval/answer-context pipeline.

This is the single ``retrieve → rerank → assemble`` context layer that BOTH
the human-facing chat surface (``apps.api.chat``) and the agent-facing MCP
surface (``apps.mcp_server.tools``) call down into. Before this module the
two surfaces shared only ``hybrid_search``; chat re-implemented rerank +
body enrichment on top of an ``apps.api → apps.mcp_server`` import, so the
rerank logic drifted between them. ``retrieve_context`` unifies that path and
returns a surface-agnostic :class:`RetrievedContext`; each surface serializes
the passages into its own output contract.

PR1 is a *behavior-preserving* extraction. ``retrieve_context`` reproduces
today's chat enrichment (candidate pool 50, top 6, 9000/2000 excerpt budgets,
``effective_from`` from the current version) and the MCP rerank (pool 50,
8000-char rerank budget, top ``limit``). The two surface-specific knobs that
genuinely differed are parameters here:

* ``rerank_doc_chars`` — per-document char cap fed to the reranker. MCP caps
  at 8000; chat passed the full body (``None`` = no cap).
* ``enrich_bodies`` — chat attaches a long ``body_excerpt`` + ``effective_from``;
  MCP returns only the 280-char ``snippet``.

One deliberate (documented, non-silent) unification: the rerank *candidate
text* now uses the raw node heading for both surfaces. Chat previously
reranked caselaw on the display-annotated heading ("Court, Year") because it
reranked after serialization; the raw heading (which carries the case name)
is strictly better and matches the MCP path. This is invisible to the test
suite (which uses ``NoopReranker``, ignoring candidate text) and to
``eval_caselaw`` (which does not traverse chat).

The dataclasses below carry forward fields that later PRs populate
(``cluster_id``, ``char_start/char_end``, ``chunk_id``, ``treatment``). In PR1
they are filled with their behavior-preserving defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from apps.corpus.models import Node, NodeVersion
from apps.corpus.services.corpus_tools import (
    _caselaw_decision,
    _node_dict,
    _snippet,
    _today,
)
from apps.corpus.services.rerank import Reranker, default_reranker
from apps.corpus.services.search import hybrid_search


# Behavior-preserving defaults (mirrors the constants the chat surface used).
DEFAULT_CANDIDATE_POOL = 50
DEFAULT_DISPLAY_LIMIT = 6
DEFAULT_EXCERPT_BUDGET_TOP = 9000
DEFAULT_EXCERPT_BUDGET_REST = 2000
DEFAULT_TOP_HITS_FULL = 2


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TreatmentFlag:
    """Good-law / currency flag for a passage. PR3 populates this; PR1 emits
    the behavior-preserving default ("unknown", advisory, no negative signal)."""

    status: str = "unknown"  # "good" | "caution" | "negative" | "unknown"
    severity: int = 0  # 0 good .. 5 invalidated
    label: str = ""  # "overruled" | "superseded" | "distinguished" | ...
    by_citation: str = ""  # the case/statute that did it, if known
    excerpt: str = ""  # verbatim citing-sentence (the evidence)
    source: str = "none"  # "history" | "graph_phrase" | "llm" | "none"
    confidence: float = 0.0


@dataclass
class RetrievedPassage:
    node_version_id: int
    node_id: int
    cluster_id: int  # decision node id (== node_id for statutes)
    path: str
    heading: str
    citation: str  # rendered, surface-ready
    source_slug: str
    chunk_id: int | None  # the winning NodeChunk, if caselaw (PR2)
    char_start: int | None  # offsets into version.body_text (PR2)
    char_end: int | None
    excerpt: str  # the body_excerpt (chat enrichment); "" when not enriched
    snippet: str  # the 280-char snippet (always present)
    effective_from: str | None
    is_repealed: bool
    score: float  # fused RRF score (rerank reorders but does not rescore)
    component_scores: dict[str, float]
    treatment: TreatmentFlag
    # The exact ``node`` sub-dict both surfaces already emit (via
    # ``corpus_tools._node_dict``), carried so the adapters reproduce their
    # output shape byte-for-byte without re-serializing.
    node_dict: dict[str, Any]


@dataclass
class RetrievedContext:
    query: str
    passages: list[RetrievedPassage]
    as_of_date: str
    abstain: bool = False  # PR4
    abstain_reason: str = ""
    diagnostics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Excerpting (moved verbatim from apps.api.chat._excerpt)
# ---------------------------------------------------------------------------


def _excerpt(text: str, max_chars: int) -> str:
    """Trim ``text`` to ``max_chars``, breaking on a word boundary and
    flagging the cut with an ellipsis so the model (per the system prompt)
    knows to call lookup_citation for the complete section."""
    text = text.rstrip()
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    last_space = cut.rfind(" ")
    if last_space > max_chars // 2:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


# ---------------------------------------------------------------------------
# The shared pipeline
# ---------------------------------------------------------------------------


def retrieve_context(
    query: str,
    *,
    source_slug: str | None = None,
    use_vector: bool = True,
    candidate_pool: int = DEFAULT_CANDIDATE_POOL,
    display_limit: int = DEFAULT_DISPLAY_LIMIT,
    rerank: bool = True,
    reranker: Reranker | None = None,
    rerank_doc_chars: int | None = None,
    enrich_bodies: bool = False,
    excerpt_budget_top: int = DEFAULT_EXCERPT_BUDGET_TOP,
    excerpt_budget_rest: int = DEFAULT_EXCERPT_BUDGET_REST,
    top_hits_full: int = DEFAULT_TOP_HITS_FULL,
    metadata_contains: dict | None = None,
) -> RetrievedContext:
    """Retrieve, (optionally) rerank, and assemble a surface-agnostic context.

    ``candidate_pool`` is the width of the hybrid-search pool the reranker
    sees; ``display_limit`` is how many passages survive. ``rerank`` toggles
    the cross-encoder pass (``reranker`` defaults to ``default_reranker()``,
    which is the Noop without a Voyage key). ``enrich_bodies`` adds the chat
    surface's long ``body_excerpt`` + ``effective_from``; otherwise passages
    carry only the 280-char ``snippet``.
    """
    as_of = _today()
    if not query or not query.strip():
        return RetrievedContext(query=query, passages=[], as_of_date=as_of)

    hits = hybrid_search(
        query,
        limit=candidate_pool,
        use_vector=use_vector,
        source_slug=source_slug,
        metadata_contains=metadata_contains,
    )
    if not hits:
        return RetrievedContext(query=query, passages=[], as_of_date=as_of)

    if rerank:
        active = reranker or default_reranker()
        candidates: list[tuple[int, str]] = [
            (
                h.node_version_id,
                f"{h.heading}\n"
                f"{h.body_text if rerank_doc_chars is None else h.body_text[:rerank_doc_chars]}",
            )
            for h in hits
        ]
        ranked_ids = active.rerank(query, candidates, top_k=display_limit)
        by_id = {h.node_version_id: h for h in hits}
        selected = [by_id[i] for i in ranked_ids if i in by_id]
    else:
        selected = hits[:display_limit]

    # Serialize the surviving hits' nodes (same query both surfaces used).
    node_ids = [h.node_id for h in selected]
    nodes = {
        n.id: n
        for n in Node.objects.filter(id__in=node_ids).select_related(
            "source", "parent"
        )
    }

    # Chat enrichment: current body_text (for the long excerpt) + effective_from.
    bodies: dict[int, str] = {}
    effective_from: dict[int, str] = {}
    if enrich_bodies:
        for nv in NodeVersion.objects.filter(
            node_id__in=node_ids, effective_to__isnull=True
        ).only("node_id", "body_text", "effective_from"):
            bodies.setdefault(nv.node_id, nv.body_text)
            if nv.effective_from and nv.node_id not in effective_from:
                effective_from[nv.node_id] = nv.effective_from.isoformat()

    passages: list[RetrievedPassage] = []
    for h in selected:
        node = nodes.get(h.node_id)
        if node is None:
            continue
        rank = len(passages)
        node_dict = _node_dict(node)
        # cluster_id collapses a decision's opinions to one id for caselaw;
        # for statutes a section is its own cluster (NOT its chapter parent),
        # so gate the decision lookup on source. (PR2 dedups on cluster_id.)
        cluster_id = (
            _caselaw_decision(node).id
            if node_dict["source_slug"] == "iowa-caselaw"
            else node.id
        )
        if enrich_bodies:
            budget = (
                excerpt_budget_top
                if rank < top_hits_full
                else excerpt_budget_rest
            )
            excerpt = _excerpt(bodies.get(h.node_id, ""), budget)
        else:
            excerpt = ""
        passages.append(
            RetrievedPassage(
                node_version_id=h.node_version_id,
                node_id=h.node_id,
                cluster_id=cluster_id,
                path=node_dict["path"],
                heading=node_dict["heading"],
                citation=node_dict["citation"],
                source_slug=node_dict["source_slug"],
                chunk_id=None,
                char_start=None,
                char_end=None,
                excerpt=excerpt,
                snippet=_snippet(h.body_text),
                effective_from=effective_from.get(h.node_id),
                is_repealed=node_dict["is_repealed"],
                score=h.score,
                component_scores=h.component_scores,
                treatment=TreatmentFlag(),
                node_dict=node_dict,
            )
        )

    return RetrievedContext(query=query, passages=passages, as_of_date=as_of)
