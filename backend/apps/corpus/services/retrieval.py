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

import re

from apps.corpus.models import Node, NodeChunk, NodeVersion
from apps.corpus.services.corpus_tools import (
    _caselaw_decision,
    _node_dict,
    _snippet,
    _today,
)
from apps.corpus.services.rerank import Reranker, default_reranker
from apps.corpus.services.search import hybrid_search


# Candidate-pool width fed to the reranker. PR2 widens this 50→100 (design §8
# Q7): a cross-encoder can only promote an on-point hit that is *in* the pool it
# sees, and dedup/MMR then need headroom below the display cut. The adapters set
# this explicitly; this default is for direct callers (eval rc-mode).
DEFAULT_CANDIDATE_POOL = 100
DEFAULT_DISPLAY_LIMIT = 6
DEFAULT_EXCERPT_BUDGET_TOP = 9000
DEFAULT_EXCERPT_BUDGET_REST = 2000
DEFAULT_TOP_HITS_FULL = 2

# Per-document char cap fed to the reranker, unified across both surfaces (PR2).
# An opinion runs to 100k+ chars; reranking a 100-candidate pool of whole
# opinions would blow Voyage's per-request token budget. The reranker truncates
# anyway and an opinion's holding/syllabus sits near the top, so a prefix carries
# the relevance signal (mirrors the MCP path and ``eval_caselaw``). This caps only
# the *rerank candidate text*; the excerpt the model actually reads keeps its full
# budget. Invisible to the test suite (NoopReranker ignores candidate text).
DEFAULT_RERANK_DOC_CHARS = 8000

# MMR diversity (design §4 stage 3). ``lambda`` trades relevance vs novelty:
# 0.6 leans relevance. v1 uses a cheap token-overlap (Jaccard) diversity.
#
# DISABLED BY DEFAULT (retrieve_context's ``mmr_lambda`` defaults to None). The
# eval_caselaw A/B (eval-gating, 2026-06-08) showed MMR *regressed* pinpoint
# retrieval: on holding-description queries the target case IS the answer, and
# the diversity penalty demoted it out of the display (hit@10 0.75 with MMR vs
# 0.90 without; target_in_shown 0.75 vs 0.85). The code + ``mmr_lambda`` param are
# kept for diversity-oriented surfaces (e.g. browse/discovery) where novelty
# matters more than surfacing one controlling case; pass ``mmr_lambda=0.6`` there.
DEFAULT_MMR_LAMBDA = 0.6
MMR_TEXT_CHARS = 2000  # chars of body used to build the diversity token set
MMR_WINDOW_FACTOR = 4  # MMR considers top (display_limit * factor) deduped hits

# Neighbor context to pull around a matched caselaw chunk so a holding isn't cut
# mid-thought; the budget bounds the total, this just sets how the slack is spent.
CHUNK_NEIGHBOR_CHARS = 600


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


def _chunk_excerpt(
    version_body: str,
    chunk_body: str,
    char_start: int,
    char_end: int,
    budget: int,
) -> str:
    """Excerpt a caselaw passage centered on the matched chunk span.

    This is the fix for "opinion-head excerpt misses the holding": instead of a
    whole-version prefix (which is the caption + procedural history), the model
    reads the chunk the dense retriever actually matched, padded with neighbor
    context up to ``budget`` so a sentence isn't cut mid-thought.

    Robust to offset drift: the neighbor window is only taken when the offsets
    actually reconstruct the chunk inside ``version_body``
    (``version_body[char_start:char_end] == chunk_body``, the invariant
    ``chunk_caselaw`` guarantees). If they don't — a re-chunked version, or a
    test fixture with placeholder offsets — it falls back to the authoritative
    ``chunk_body`` alone. Either way the returned text is real, citable span."""
    n = len(version_body)
    valid = (
        0 <= char_start <= char_end <= n
        and version_body[char_start:char_end] == chunk_body
    )
    if not valid:
        return _excerpt(chunk_body, budget)

    span_len = char_end - char_start
    if span_len >= budget:
        return _excerpt(version_body[char_start:char_end], budget)

    # A small neighbor window on each side, bounded by the budget.
    half = min(CHUNK_NEIGHBOR_CHARS, (budget - span_len) // 2)
    start = max(0, char_start - half)
    end = min(n, char_end + half)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < n else ""
    # Reserve room for the ellipses so the whole string (incl. them) never
    # exceeds the budget — the contract the chat token-budget relies on.
    body = version_body[start:end].strip()
    room = budget - len(prefix) - len(suffix)
    if len(body) > room:
        body = body[:room].rstrip()
    return prefix + body + suffix


_WORD_RE = re.compile(r"[a-z0-9]+")


def _token_set(text: str) -> frozenset[str]:
    """Lowercased alphanumeric tokens >=3 chars — the unit for MMR's cheap
    token-overlap diversity. Short tokens are dropped as low-signal noise."""
    return frozenset(t for t in _WORD_RE.findall(text.lower()) if len(t) >= 3)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _mmr_select(hits: list, *, k: int, lambda_: float) -> list:
    """Maximal-Marginal-Relevance selection: greedily pick ``k`` hits trading
    relevance (input rank, best first) against novelty vs already-picked hits.

    Relevance is reciprocal rank ``1/(i+1)`` over a capped window of the most
    relevant deduped hits, so a lexically-diverse far-tail hit can't be pulled up
    purely for novelty. The FIRST pick is always the top-ranked hit (empty
    selected set → zero diversity penalty → max relevance), which keeps rank-1
    stable — the invariant the surface tests rely on. Deterministic: candidates
    are scanned in ascending rank and ties resolve to the lower rank."""
    window = hits[: max(k * MMR_WINDOW_FACTOR, 24)]
    n = len(window)
    k = min(k, n)
    if k <= 1 or lambda_ >= 1.0:
        return window[:k]
    rel = {i: 1.0 / (i + 1) for i in range(n)}
    toks = [
        _token_set(f"{h.heading} {h.body_text[:MMR_TEXT_CHARS]}") for h in window
    ]
    chosen: list[int] = []
    remaining = list(range(n))
    while remaining and len(chosen) < k:
        best_i = None
        best_score = None
        for i in remaining:  # ascending rank → deterministic tiebreak
            if not chosen:
                score = rel[i]
            else:
                max_sim = max(_jaccard(toks[i], toks[j]) for j in chosen)
                score = lambda_ * rel[i] - (1.0 - lambda_) * max_sim
            if best_score is None or score > best_score:
                best_score = score
                best_i = i
        chosen.append(best_i)
        remaining.remove(best_i)
    return [window[i] for i in chosen]


_TREATMENT_FIELDS = {
    "status", "severity", "label", "by_citation", "excerpt", "source", "confidence",
}


def treatment_payload(flag: TreatmentFlag) -> dict:
    """Serialize a :class:`TreatmentFlag` for a surface hit (additive). Surfaces
    show this so a downstream agent / the chat model can see whether a cited case
    is still good law and the verbatim evidence sentence."""
    return {
        "status": flag.status,
        "severity": flag.severity,
        "label": flag.label,
        "by_citation": flag.by_citation,
        "excerpt": flag.excerpt,
        "source": flag.source,
        "confidence": flag.confidence,
    }


def _treatment_for(node: Node) -> TreatmentFlag:
    """Read the cached good-law flag off the node's DECISION (caselaw) and build a
    :class:`TreatmentFlag`. ``annotate_treatment`` (PR3) writes it onto the cited
    decision's ``source_metadata["treatment"]``; absence means no negative
    treatment was found → the behavior-preserving "unknown" default. Statutes have
    no decision/treatment, so they also get the default."""
    decision = _caselaw_decision(node)
    td = (decision.source_metadata or {}).get("treatment")
    if not td:
        return TreatmentFlag()
    return TreatmentFlag(**{k: v for k, v in td.items() if k in _TREATMENT_FIELDS})


def _u_order(items: list) -> list:
    """Reorder a relevance-ranked list (best first) into a U-curve so the two
    strongest land at the ends and the weakest in the middle — the "lost in the
    middle" mitigation. ``items[0]`` (the most relevant) stays at position 0, so
    rank-1 assertions hold; ``items[1]`` moves to the last position."""
    left, right = [], []
    for i, it in enumerate(items):
        (left if i % 2 == 0 else right).append(it)
    return left + right[::-1]


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
    rerank_doc_chars: int | None = DEFAULT_RERANK_DOC_CHARS,
    enrich_bodies: bool = False,
    excerpt_budget_top: int = DEFAULT_EXCERPT_BUDGET_TOP,
    excerpt_budget_rest: int = DEFAULT_EXCERPT_BUDGET_REST,
    top_hits_full: int = DEFAULT_TOP_HITS_FULL,
    metadata_contains: dict | None = None,
    dedup_clusters: bool = True,
    mmr_lambda: float | None = None,  # off by default — eval showed MMR regresses
    u_order: bool = True,
    chunk_excerpts: bool = True,
    protect_citations: bool = True,
) -> RetrievedContext:
    """Retrieve, rerank, dedup, diversify, and assemble a surface-agnostic context.

    Pipeline (PR2): hybrid retrieve → rerank (exact-citation lane bypasses it) →
    decision-cluster dedup → MMR diversity select → chunk-aware passage assembly
    → U-curve order. Each stage past rerank is individually togglable (for the
    eval A/B); every stage preserves the rank-1 hit at position 0.

    ``candidate_pool`` is the width of the hybrid-search pool the reranker sees
    (wide), ``display_limit`` how many passages survive (narrow). ``rerank``
    toggles the cross-encoder (``reranker`` defaults to ``default_reranker()`` —
    Noop without a Voyage key); ``rerank_doc_chars`` caps each candidate's text
    fed to it. ``enrich_bodies`` adds the chat surface's long ``body_excerpt`` +
    ``effective_from``; otherwise passages carry only the 280-char ``snippet``.

    PR2 toggles: ``dedup_clusters`` collapses a decision's opinions to one
    passage; ``mmr_lambda`` (None / >=1.0 = off) sets MMR diversity;
    ``chunk_excerpts`` excerpts the matched caselaw chunk span instead of the
    opinion-head prefix (statutes always keep the prefix); ``u_order`` applies the
    lost-in-the-middle reorder; ``protect_citations`` keeps exact-cite hits from
    being demoted by the reranker.
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

    diagnostics: dict[str, Any] = {
        "pool": len(hits),
        "candidate_pool": candidate_pool,
        "display_limit": display_limit,
        "reranked": bool(rerank),
    }

    # --- Stage A: rerank, with the exact-citation lane bypassing it ----------
    # An exact reporter-cite hit is a known-item lookup (precision ~1.0); the
    # eval showed the reranker can demote it. Pull cite hits out (they keep their
    # hybrid_search prepend order), rerank only the rest over the FULL pool, then
    # restore the cite hits at the front. Without rerank, hybrid_search order
    # already has cites prepended, so there is nothing to protect.
    if rerank:
        active = reranker or default_reranker()
        if protect_citations:
            cite_ids = {
                h.node_version_id
                for h in hits
                if "citation" in h.component_scores
            }
        else:
            cite_ids = set()
        cite_hits = [h for h in hits if h.node_version_id in cite_ids]
        rerankable = [h for h in hits if h.node_version_id not in cite_ids]
        candidates: list[tuple[int, str]] = [
            (
                h.node_version_id,
                f"{h.heading}\n"
                f"{h.body_text if rerank_doc_chars is None else h.body_text[:rerank_doc_chars]}",
            )
            for h in rerankable
        ]
        ranked_ids = active.rerank(query, candidates, top_k=len(candidates))
        by_id = {h.node_version_id: h for h in rerankable}
        ordered = cite_hits + [by_id[i] for i in ranked_ids if i in by_id]
        diagnostics["cite_protected"] = len(cite_hits)
    else:
        ordered = list(hits)

    # --- Stage B: fetch the pool's nodes once; derive each hit's cluster ------
    pool_node_ids = [h.node_id for h in ordered]
    nodes = {
        n.id: n
        for n in Node.objects.filter(id__in=pool_node_ids).select_related(
            "source", "parent"
        )
    }
    # Drop hits whose node vanished between search and fetch (parity with the
    # pre-PR2 per-passage None-skip), so later stages see only live nodes.
    ordered = [h for h in ordered if h.node_id in nodes]

    def _cluster_id_of(h) -> int:
        node = nodes[h.node_id]
        if node.source.slug == "iowa-caselaw":
            return _caselaw_decision(node).id
        # A statute section is its own cluster (NOT its chapter parent).
        return node.id

    # --- Stage C: decision-cluster dedup (keep the best-ranked per cluster) ---
    if dedup_clusters:
        seen: set[int] = set()
        deduped = []
        for h in ordered:
            cid = _cluster_id_of(h)
            if cid in seen:
                continue
            seen.add(cid)
            deduped.append(h)
        diagnostics["deduped_out"] = len(ordered) - len(deduped)
        ordered = deduped

    # --- Stage D: MMR diversity select down to display_limit ------------------
    if mmr_lambda is not None and mmr_lambda < 1.0 and len(ordered) > 1:
        selected = _mmr_select(ordered, k=display_limit, lambda_=mmr_lambda)
        diagnostics["mmr_lambda"] = mmr_lambda
    else:
        selected = ordered[:display_limit]

    # --- Stage E: assemble passages (chunk-aware excerpts for caselaw) --------
    selected_node_ids = [h.node_id for h in selected]
    chunk_ids = [h.chunk_id for h in selected if h.chunk_id is not None]
    chunks: dict[int, NodeChunk] = {}
    if chunk_excerpts and chunk_ids:
        chunks = {
            c.id: c
            for c in NodeChunk.objects.filter(id__in=chunk_ids).only(
                "id", "version_id", "body_text", "char_start", "char_end"
            )
        }

    bodies: dict[int, str] = {}
    effective_from: dict[int, str] = {}
    if enrich_bodies:
        for nv in NodeVersion.objects.filter(
            node_id__in=selected_node_ids, effective_to__isnull=True
        ).only("node_id", "body_text", "effective_from"):
            bodies.setdefault(nv.node_id, nv.body_text)
            if nv.effective_from and nv.node_id not in effective_from:
                effective_from[nv.node_id] = nv.effective_from.isoformat()

    passages: list[RetrievedPassage] = []
    for h in selected:
        node = nodes[h.node_id]
        rank = len(passages)  # relevance rank — drives the excerpt budget below
        node_dict = _node_dict(node)
        is_caselaw = node_dict["source_slug"] == "iowa-caselaw"
        cluster_id = _cluster_id_of(h)
        chunk = (
            chunks.get(h.chunk_id)
            if (is_caselaw and h.chunk_id is not None)
            else None
        )

        if chunk is not None:
            char_start, char_end, chunk_id = (
                chunk.char_start,
                chunk.char_end,
                chunk.id,
            )
            snippet = _snippet(chunk.body_text)
        else:
            char_start = char_end = chunk_id = None
            snippet = _snippet(h.body_text)

        if enrich_bodies:
            budget = (
                excerpt_budget_top if rank < top_hits_full else excerpt_budget_rest
            )
            if chunk is not None:
                excerpt = _chunk_excerpt(
                    bodies.get(h.node_id, ""),
                    chunk.body_text,
                    chunk.char_start,
                    chunk.char_end,
                    budget,
                )
            else:
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
                chunk_id=chunk_id,
                char_start=char_start,
                char_end=char_end,
                excerpt=excerpt,
                snippet=snippet,
                effective_from=effective_from.get(h.node_id),
                is_repealed=node_dict["is_repealed"],
                score=h.score,
                component_scores=h.component_scores,
                treatment=_treatment_for(node),
                node_dict=node_dict,
            )
        )

    # --- Stage F: U-curve order (presentation only; rank-1 stays at index 0) --
    if u_order and len(passages) > 2:
        passages = _u_order(passages)
        diagnostics["u_order"] = True

    return RetrievedContext(
        query=query,
        passages=passages,
        as_of_date=as_of,
        diagnostics=diagnostics,
    )
