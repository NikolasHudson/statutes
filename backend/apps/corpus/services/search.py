"""Hybrid search over current NodeVersions.

Three retrievers, all returning ``[(node_version_id, score), ...]`` in
descending relevance:

    fts_search       — Postgres tsvector (English config) on search_vector
    trigram_search   — pg_trgm fuzzy on Node.heading (typo / partial titles)
    vector_search    — pgvector cosine on embedding

``hybrid_search`` runs all three in parallel and fuses with Reciprocal Rank
Fusion. The fused score does NOT carry semantic meaning across retrievers —
it is only an ordering signal — so callers should treat it as opaque and
sort by it, nothing else.

All retrievers operate over *current, approved* NodeVersions only:
    effective_to IS NULL  (current)
    review_status = 'approved'  (visible to callers)

Pass ``include_pending=True`` to also see pending versions during admin
review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from django.db import connection, transaction

from apps.corpus.models import NodeVersion, ReviewStatus

from .query_expansion import QueryExpander
from .voyage import INPUT_TYPE_QUERY, EmbeddingClient, default_client


# RRF k constant. 60 is the value from the original Cormack et al. 2009 paper
# and the one used by basically every public hybrid search implementation.
# Higher k flattens the contribution of top ranks; we'll tune from the eval
# harness if needed.
RRF_K = 60

# Default per-retriever candidate cap. Each retriever returns up to N hits;
# RRF fuses across all of them. 50 is a reasonable balance — large enough that
# the fusion sees the long tail, small enough to stay snappy.
RETRIEVER_TOP_N = 50


@dataclass
class SearchHit:
    """Result row exposed to callers."""

    node_version_id: int
    node_id: int
    path: str
    heading: str
    body_text: str
    score: float
    # Per-retriever scores for debugging / explain endpoints.
    component_scores: dict[str, float] = field(default_factory=dict)


def _approved_filter_clause(include_pending: bool) -> tuple[str, list]:
    """Returns (SQL fragment, params) for the visibility filter."""
    if include_pending:
        return ("", [])
    return ("AND nv.review_status = %s", [ReviewStatus.APPROVED.value])


def _source_filter_clause(source_slug: str | None) -> tuple[str, str, list]:
    """Returns ``(extra_join, where_fragment, params)`` to scope a retriever to
    a single Source by slug.

    The filter is pushed into each retriever's own query rather than applied
    after fusion: post-fusion filtering would let an off-source corpus crowd
    out the in-scope hits before we ever see them. Dedicated aliases
    (``n_src``/``s_src``) keep this independent of any join a retriever
    already has (trigram joins ``corpus_node n``)."""
    if not source_slug:
        return ("", "", [])
    return (
        "JOIN corpus_node n_src ON n_src.id = nv.node_id "
        "JOIN corpus_source s_src ON s_src.id = n_src.source_id",
        "AND s_src.slug = %s",
        [source_slug],
    )


def fts_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    source_slug: str | None = None,
) -> list[tuple[int, float]]:
    """Full-text search via tsvector + ts_rank_cd.

    ``websearch_to_tsquery`` is forgiving — it handles quoted phrases, the
    ``-`` operator, and bare terms without throwing on punctuation, which is
    what attorneys will type."""

    if not query.strip():
        return []
    visibility, vis_params = _approved_filter_clause(include_pending)
    src_join, src_where, src_params = _source_filter_clause(source_slug)
    sql = f"""
        SELECT nv.id,
               ts_rank_cd(nv.search_vector, websearch_to_tsquery('english', %s)) AS score
        FROM corpus_nodeversion nv
        {src_join}
        WHERE nv.effective_to IS NULL
          AND nv.search_vector @@ websearch_to_tsquery('english', %s)
          {visibility}
          {src_where}
        ORDER BY score DESC
        LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [query, query, *vis_params, *src_params, limit])
        return [(int(row[0]), float(row[1])) for row in cur.fetchall()]


def trigram_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    similarity_threshold: float = 0.1,
    source_slug: str | None = None,
) -> list[tuple[int, float]]:
    """Fuzzy match against Node.heading using pg_trgm similarity — this is the
    typo / partial-title retriever ("incorportion" → "Incorporation").

    Body text is deliberately *not* trigram-matched. A GIN trigram index over
    full statute bodies is near-useless at any recall-friendly threshold: at
    0.1, ``body_text % q`` matched ~75% of the corpus, and the bitmap heap
    recheck then recomputes ``similarity()`` over megabytes of text — that was
    a fixed ~10 s full-scan on every search regardless of query. FTS already
    covers body content well (sub-300 ms via the search_vector GIN index), so
    body fuzzy match was almost pure cost for recall RRF mostly downranked
    anyway. Trigram now does only what trigram is good at: short strings.

    The threshold stays low — RRF downranks weak matches naturally and a
    heading-only scan is cheap, so we keep recall."""

    if not query.strip():
        return []
    visibility, vis_params = _approved_filter_clause(include_pending)
    src_join, src_where, src_params = _source_filter_clause(source_slug)
    # SET LOCAL only sticks within an explicit transaction; without one, Django's
    # autocommit ends the transaction immediately and the threshold is lost. We
    # wrap both statements in atomic() to keep them in a single tx.
    sql = f"""
        SELECT nv.id, similarity(n.heading, %s) AS score
        FROM corpus_nodeversion nv
        JOIN corpus_node n ON n.id = nv.node_id
        {src_join}
        WHERE nv.effective_to IS NULL
          AND n.heading %% %s
          {visibility}
          {src_where}
        ORDER BY score DESC
        LIMIT %s;
    """
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("SET LOCAL pg_trgm.similarity_threshold = %s;", [similarity_threshold])
        cur.execute(sql, [query, query, *vis_params, *src_params, limit])
        return [(int(row[0]), float(row[1])) for row in cur.fetchall()]


def vector_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    client: EmbeddingClient | None = None,
    source_slug: str | None = None,
) -> list[tuple[int, float]]:
    """Semantic search via pgvector cosine distance.

    Score returned is similarity (1 - cosine_distance), so larger == more
    similar, matching the convention of the other retrievers."""

    if not query.strip():
        return []
    client = client or default_client()
    [vector] = client.embed_texts([query], input_type=INPUT_TYPE_QUERY)
    vector_literal = "[" + ",".join(f"{x:.7f}" for x in vector) + "]"

    visibility, vis_params = _approved_filter_clause(include_pending)
    src_join, src_where, src_params = _source_filter_clause(source_slug)
    sql = f"""
        SELECT nv.id,
               1 - (nv.embedding <=> %s::vector) AS score
        FROM corpus_nodeversion nv
        {src_join}
        WHERE nv.effective_to IS NULL
          AND nv.embedding IS NOT NULL
          {visibility}
          {src_where}
        ORDER BY nv.embedding <=> %s::vector
        LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(
            sql, [vector_literal, *vis_params, *src_params, vector_literal, limit]
        )
        return [(int(row[0]), float(row[1])) for row in cur.fetchall()]


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[tuple[int, float]]],
    *,
    k: int = RRF_K,
) -> list[tuple[int, float, dict[str, float]]]:
    """Fuse multiple ranked lists into one.

    For each list, item at rank r contributes 1/(k+r) to its fused score.
    Returns ``[(id, fused_score, per_retriever_scores), ...]`` sorted desc.

    The fused score is unitless and only meaningful relative to other items
    in the same fusion call."""

    fused: dict[int, float] = {}
    components: dict[int, dict[str, float]] = {}

    for retriever_name, ranking in ranked_lists.items():
        for rank, (item_id, raw_score) in enumerate(ranking, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (k + rank)
            components.setdefault(item_id, {})[retriever_name] = raw_score

    return sorted(
        (
            (item_id, score, components.get(item_id, {}))
            for item_id, score in fused.items()
        ),
        key=lambda row: row[1],
        reverse=True,
    )


def hybrid_search(
    query: str,
    *,
    limit: int = 20,
    per_retriever: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    client: EmbeddingClient | None = None,
    expander: QueryExpander | None = None,
    use_vector: bool = True,
    source_slug: str | None = None,
) -> list[SearchHit]:
    """The public entrypoint. Runs FTS + trigram + (optional) vector and
    fuses the rankings with RRF.

    ``expander`` is applied before FTS/trigram so they pick up Iowa
    terms-of-art the user didn't type. The vector retriever uses the original
    query — embeddings already capture semantic equivalence, so expansion
    would just add noise.

    ``use_vector=False`` skips embeddings — set it during dev when no Voyage
    key is available and you don't want fake vectors polluting the ranking."""

    if not query.strip():
        return []

    expanded = expander.expand(query) if expander is not None else query

    rankings: dict[str, list[tuple[int, float]]] = {
        "fts": fts_search(
            expanded,
            limit=per_retriever,
            include_pending=include_pending,
            source_slug=source_slug,
        ),
        "trigram": trigram_search(
            expanded,
            limit=per_retriever,
            include_pending=include_pending,
            source_slug=source_slug,
        ),
    }
    if use_vector:
        rankings["vector"] = vector_search(
            query,
            limit=per_retriever,
            include_pending=include_pending,
            client=client,
            source_slug=source_slug,
        )

    fused = reciprocal_rank_fusion(rankings)[:limit]
    if not fused:
        return []

    ids = [row[0] for row in fused]
    rows = NodeVersion.objects.filter(id__in=ids).select_related("node")
    by_id = {r.id: r for r in rows}

    hits: list[SearchHit] = []
    for nv_id, score, components in fused:
        nv = by_id.get(nv_id)
        if nv is None:
            continue
        hits.append(
            SearchHit(
                node_version_id=nv.id,
                node_id=nv.node_id,
                path=nv.node.path,
                heading=nv.node.heading,
                body_text=nv.body_text,
                score=score,
                component_scores=components,
            )
        )
    return hits


def search_iter_node_version_ids(
    hits: Iterable[SearchHit],
) -> list[int]:
    """Convenience for callers that just want the ID list."""
    return [h.node_version_id for h in hits]
