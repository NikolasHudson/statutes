"""Hybrid search over current NodeVersions.

Three retrievers, all returning ``[(node_version_id, score), ...]`` in
descending relevance:

    fts_search       — Postgres tsvector (English config) on search_vector
    trigram_search   — pg_trgm fuzzy on Node.heading (typo / partial titles)
    vector_search    — pgvector cosine; unions whole-version embeddings
                       (statutes/rules) with passage-level NodeChunk embeddings
                       (caselaw) rolled up to their version

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

import json
import re
from dataclasses import dataclass, field
from typing import Iterable

from django.db import connection, transaction

from apps.corpus.models import NodeVersion, ReviewStatus

from .embedding_cache import embed_query_cached
from .query_expansion import QueryExpander
from .voyage import EmbeddingClient


# RRF k constant. 60 is the value from the original Cormack et al. 2009 paper
# and the one used by basically every public hybrid search implementation.
# Higher k flattens the contribution of top ranks; we'll tune from the eval
# harness if needed.
RRF_K = 60

# Per-retriever fusion weights. Plain RRF gives every retriever an identical
# 1/(k+rank) vote. On conceptual caselaw queries that is actively harmful: the
# eval_caselaw harness measured 'hybrid' scoring WORSE than pure 'vector' (MRR
# 0.48 vs 0.73, hit@1 0.20 vs 0.55) because two weak lexical retrievers (fts MRR
# ~0.15, trigram near-noise) agreeing on a near-miss case out-vote the dense
# retriever's single correct rank-1 hit. Weighting the dense vote up and the
# fuzzy/lexical votes down keeps their *complementary* recall (a lexical-only hit
# can still surface, and the downstream reranker fixes final ordering) without
# letting them override a confident vector match. Exact citations bypass fusion
# entirely (prepended in hybrid_search); case_name is a precise, query-conditional
# retriever that mostly no-ops, so it keeps a mid weight. A retriever absent from
# this dict votes at 1.0. Tunable from the eval harness via hybrid_search(weights=).
RETRIEVER_WEIGHTS: dict[str, float] = {
    "vector": 1.0,
    "case_name": 0.5,
    "fts": 0.3,
    "trigram": 0.2,
}

# Default per-retriever candidate cap. Each retriever returns up to N hits;
# RRF fuses across all of them. 50 is a reasonable balance — large enough that
# the fusion sees the long tail, small enough to stay snappy.
RETRIEVER_TOP_N = 50

# Chunk over-fetch factor for the vector retriever. Many chunks collapse onto one
# version when rolled up, so the chunk query pulls this many × `limit` candidates
# from the HNSW index to still yield `limit` distinct versions after rollup.
CHUNK_OVERFETCH = 5

# HNSW search-beam width (pgvector ``hnsw.ef_search``). The default of 40 is far
# too narrow for the ~500K-vector caselaw chunk index: the eval_caselaw harness
# found top semantic matches — cases ranking #1/#2 by cosine — silently dropping
# out of the result set at 40, fully recovered at 200 (recall 90% → 100%, hit@10
# 0.90 → 1.00). Applied once per connection in ``apps.corpus.signals`` rather than
# per query (pgvector registers the GUC only after its module loads, so a per-query
# ``SET`` races the first vector op). Tunable: higher = better recall, more scan.
HNSW_EF_SEARCH = 200

# Filtered-ANN completeness (pgvector >= 0.8). When a selective metadata filter
# (court / precedential status) rejects most of the HNSW beam, a plain top-k scan
# can return fewer than ``limit`` rows — the index walks ef_search candidates, the
# filter discards them, and the tail is silently lost (the under-return caveat in
# ``_vector_search_chunks``). ``hnsw.iterative_scan`` makes pgvector keep walking
# the graph until ``limit`` rows pass the filter (or ``max_scan_tuples`` is hit).
# ``strict_order`` preserves exact distance ordering (vs ``relaxed_order``), which a
# legal tool needs since rank order is load-bearing. Set per connection in
# ``apps.corpus.signals`` alongside ef_search; best-effort there, so a pre-0.8
# pgvector simply keeps the ef_search widening. Empty string disables.
HNSW_ITERATIVE_SCAN = "strict_order"
HNSW_MAX_SCAN_TUPLES = 20000


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
    # The NodeChunk that won this version in the dense retriever, if any. Set
    # only for caselaw hits the vector retriever surfaced (a statute embeds
    # whole, so it has no chunk; a caselaw hit that reached the top only via
    # FTS/citation has no *winning* chunk either). ``retrieve_context`` uses it
    # to excerpt the matched passage instead of the opinion head. Default None
    # keeps every other caller — which never reads it — untouched.
    chunk_id: int | None = None


def _approved_filter_clause(include_pending: bool) -> tuple[str, list]:
    """Returns (SQL fragment, params) for the visibility filter."""
    if include_pending:
        return ("", [])
    return ("AND nv.review_status = %s", [ReviewStatus.APPROVED.value])


def _source_filter_clause(
    source_slug: str | None, metadata_contains: dict | None = None
) -> tuple[str, str, list]:
    """Returns ``(extra_join, where_fragment, params)`` scoping a retriever to a
    single Source by slug and/or a ``source_metadata`` containment filter.

    Both filters are pushed into each retriever's own query rather than applied
    after fusion: post-fusion filtering would let off-scope hits crowd out the
    in-scope ones before we ever see them. The containment filter (``@>``) is
    served by the ``node_source_metadata_gin`` (jsonb_path_ops) index — used for
    caselaw facets like ``{"court_id": "iowa"}`` / ``{"precedential_status":
    "Published"}``. Dedicated aliases (``n_src``/``s_src``) keep this independent
    of any join a retriever already has (trigram joins ``corpus_node n``); the
    node join is emitted once and shared by both filters."""
    if not source_slug and not metadata_contains:
        return ("", "", [])
    join = "JOIN corpus_node n_src ON n_src.id = nv.node_id"
    wheres: list[str] = []
    params: list = []
    if source_slug:
        join += " JOIN corpus_source s_src ON s_src.id = n_src.source_id"
        wheres.append("AND s_src.slug = %s")
        params.append(source_slug)
    if metadata_contains:
        # Match the hit node's own metadata OR its parent's: a caselaw hit is
        # usually an *opinion* whose court/status live on the parent *decision*
        # (a decision head-matter hit matches via its own metadata). Both use
        # the jsonb_path_ops GIN index.
        md_json = json.dumps(metadata_contains)
        wheres.append(
            "AND (n_src.source_metadata @> %s::jsonb "
            "OR EXISTS (SELECT 1 FROM corpus_node p_src "
            "WHERE p_src.id = n_src.parent_id "
            "AND p_src.source_metadata @> %s::jsonb))"
        )
        params.append(md_json)
        params.append(md_json)
    return (join, " ".join(wheres), params)


def fts_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    source_slug: str | None = None,
    metadata_contains: dict | None = None,
) -> list[tuple[int, float]]:
    """Full-text search via tsvector + ts_rank_cd.

    ``websearch_to_tsquery`` is forgiving — it handles quoted phrases, the
    ``-`` operator, and bare terms without throwing on punctuation, which is
    what attorneys will type."""

    if not query.strip():
        return []
    visibility, vis_params = _approved_filter_clause(include_pending)
    src_join, src_where, src_params = _source_filter_clause(
        source_slug, metadata_contains
    )
    sql = f"""
        SELECT nv.id,
               ts_rank_cd(nv.search_vector, websearch_to_tsquery('english', %s)) AS score
        FROM corpus_nodeversion nv
        {src_join}
        WHERE nv.effective_to IS NULL
          AND nv.search_vector @@ websearch_to_tsquery('english', %s)
          {visibility}
          {src_where}
        ORDER BY score DESC, nv.id
        LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [query, query, *vis_params, *src_params, limit])
        return [(int(row[0]), float(row[1])) for row in cur.fetchall()]


_PAGED_FTS_FUNCS = {"websearch_to_tsquery", "to_tsquery"}
_PAGED_FTS_ORDERS = {
    "rank": "score DESC, id",
    "date_desc": "date_filed DESC NULLS LAST, score DESC, id",
    "date_asc": "date_filed ASC NULLS LAST, score DESC, id",
}


def _paged_fts_ctes(
    tsquery: str,
    *,
    tsquery_func: str,
    include_pending: bool,
    source_slug: str | None,
    metadata_contains: dict | None,
    date_from: str | None,
    date_to: str | None,
    rank: bool = True,
) -> tuple[str, list]:
    """The shared CTE chain for the exhaustive boolean-mode queries:
    ``matches`` (every FTS hit, opinion rolled up to its decision as
    ``cluster_id``) → ``best`` (one best-scoring row per cluster) → ``scoped``
    (decision-level attributes + date bounds). ``fts_search_paged`` appends a
    page SELECT, ``search_facets_fts`` a GROUPING SETS aggregate — same match
    set by construction, so page totals and facet counts can never disagree.

    ``tsquery_func`` must already be whitelisted by the caller (it is
    interpolated). Returns ``(sql_text, params)``.

    ``rank=False`` skips ``ts_rank_cd`` (score fixed at 0): computing rank
    detoasts every matching tsvector, which dominates cost on broad match
    sets (measured 6.9s → 2.0s over a 78K-match term). Facet aggregation and
    date-ordered pages never read the score, so they never pay for it."""
    visibility, vis_params = _approved_filter_clause(include_pending)
    src_join, src_where, src_params = _source_filter_clause(
        source_slug, metadata_contains
    )
    date_wheres: list[str] = []
    date_params: list = []
    if date_from:
        date_wheres.append("AND (c.source_metadata->>'date_filed') >= %s")
        date_params.append(date_from)
    if date_to:
        date_wheres.append("AND (c.source_metadata->>'date_filed') <= %s")
        date_params.append(date_to)

    score_expr = (
        f"ts_rank_cd(nv.search_vector, {tsquery_func}('english', %s))"
        if rank
        else "0.0"
    )
    ctes = f"""
        WITH matches AS (
            SELECT nv.id,
                   nv.node_id,
                   {score_expr} AS score,
                   CASE WHEN nt.key = 'opinion' AND n.parent_id IS NOT NULL
                        THEN n.parent_id ELSE n.id END AS cluster_id
            FROM corpus_nodeversion nv
            JOIN corpus_node n ON n.id = nv.node_id
            JOIN corpus_nodetype nt ON nt.id = n.node_type_id
            {src_join}
            WHERE nv.effective_to IS NULL
              AND nv.search_vector @@ {tsquery_func}('english', %s)
              {visibility}
              {src_where}
        ),
        best AS (
            SELECT DISTINCT ON (m.cluster_id) m.*
            FROM matches m
            ORDER BY m.cluster_id, m.score DESC, m.id
        ),
        scoped AS (
            SELECT b.*,
                   c.source_metadata->>'date_filed' AS date_filed,
                   c.source_metadata->>'court_id' AS court_id,
                   c.source_metadata->>'precedential_status' AS status,
                   s.slug AS source_slug
            FROM best b
            JOIN corpus_node c ON c.id = b.cluster_id
            JOIN corpus_source s ON s.id = c.source_id
            WHERE TRUE {' '.join(date_wheres)}
        )
    """
    # The score expression only binds a param when ranking is on.
    params = [
        *([tsquery] if rank else []),
        tsquery, *vis_params, *src_params, *date_params,
    ]
    return ctes, params


def search_facets_fts(
    tsquery: str,
    *,
    tsquery_func: str = "websearch_to_tsquery",
    include_pending: bool = False,
    source_slug: str | None = None,
    metadata_contains: dict | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Exact facet counts over the boolean-mode match set, in one scan.

    Returns ``{"sources": {slug: n}, "courts": {court_id: n},
    "statuses": {status: n}, "decades": {"1990": n, ...}}`` computed with
    GROUPING SETS over the same CTE chain as ``fts_search_paged`` (all current
    filters applied). Decade buckets come from the decision's ``date_filed``
    year; rows with no date (statutes/rules) simply don't appear in the
    caselaw dimensions. A NULL group key within a set (e.g. court of a
    statute row) is skipped on read."""
    if tsquery_func not in _PAGED_FTS_FUNCS:
        raise ValueError(f"unsupported tsquery func: {tsquery_func!r}")
    if not tsquery.strip():
        return {"sources": {}, "courts": {}, "statuses": {}, "decades": {}}

    ctes, params = _paged_fts_ctes(
        tsquery,
        tsquery_func=tsquery_func,
        include_pending=include_pending,
        source_slug=source_slug,
        metadata_contains=metadata_contains,
        date_from=date_from,
        date_to=date_to,
        rank=False,  # aggregation never reads the score
    )
    sql = f"""
        {ctes}
        SELECT GROUPING(source_slug, court_id, status, decade) AS gmask,
               source_slug, court_id, status, decade,
               count(*) AS n
        FROM (
            SELECT source_slug, court_id, status,
                   CASE WHEN date_filed ~ '^\\d{{4}}'
                        THEN substr(date_filed, 1, 3) || '0'
                   END AS decade
            FROM scoped
        ) dims
        GROUP BY GROUPING SETS ((source_slug), (court_id), (status), (decade));
    """
    out: dict[str, dict] = {
        "sources": {}, "courts": {}, "statuses": {}, "decades": {}
    }
    # GROUPING() bitmask over (source_slug, court_id, status, decade):
    # 0 = grouped-by. 0b0111 → the (source_slug) set, etc.
    by_mask = {
        0b0111: ("sources", 1),
        0b1011: ("courts", 2),
        0b1101: ("statuses", 3),
        0b1110: ("decades", 4),
    }
    with connection.cursor() as cur:
        cur.execute(sql, params)
        for row in cur.fetchall():
            entry = by_mask.get(int(row[0]))
            if entry is None:
                continue
            bucket, col = entry
            key = row[col]
            if key:
                out[bucket][str(key)] = int(row[5])
    return out


def fts_search_paged(
    tsquery: str,
    *,
    tsquery_func: str = "websearch_to_tsquery",
    limit: int = 10,
    offset: int = 0,
    include_pending: bool = False,
    source_slug: str | None = None,
    metadata_contains: dict | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    order: str = "rank",
) -> tuple[list[SearchHit], int]:
    """Exhaustive FTS for the boolean (terms-and-connectors) search mode.

    Unlike ``fts_search`` (a fixed-depth retriever feeding RRF), this is a
    *complete* match-set query: an attorney typing connectors is asking for a
    deterministic, auditable result set, so it returns the exact deduped total
    (``count(*) OVER ()``) and supports true deep pagination — no candidate-pool
    cap. Caselaw rows are deduped to one per decision (best-scoring opinion
    wins) so the count means "cases", mirroring the browse search behavior.

    ``tsquery`` is the pre-compiled query text for ``tsquery_func`` (see
    ``search_intent.compile_boolean_tsquery``); the function name is whitelisted
    here because it is interpolated into SQL. Date bounds live in-SQL (on the
    decision's ``date_filed``, ISO strings compare lexicographically) so the
    total stays honest under filtering; a date bound necessarily excludes
    undated rows (statutes), matching the endpoint rule that any caselaw-only
    filter forces the cases scope."""

    if tsquery_func not in _PAGED_FTS_FUNCS:
        raise ValueError(f"unsupported tsquery func: {tsquery_func!r}")
    order_clause = _PAGED_FTS_ORDERS.get(order)
    if order_clause is None:
        raise ValueError(f"unsupported order: {order!r}")
    if not tsquery.strip():
        return [], 0

    ctes, params = _paged_fts_ctes(
        tsquery,
        tsquery_func=tsquery_func,
        include_pending=include_pending,
        source_slug=source_slug,
        metadata_contains=metadata_contains,
        date_from=date_from,
        date_to=date_to,
        # Date-ordered pages never read the score; skipping ts_rank_cd is the
        # difference between ~2s and ~7s on broad match sets.
        rank=(order == "rank"),
    )
    sql = f"""
        {ctes}
        SELECT id, score, count(*) OVER () AS total
        FROM scoped
        ORDER BY {order_clause}
        LIMIT %s OFFSET %s;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [*params, limit, offset])
        rows = cur.fetchall()

    total = int(rows[0][2]) if rows else 0
    ordered = [(int(r[0]), float(r[1])) for r in rows]
    by_id = {
        nv.id: nv
        for nv in NodeVersion.objects.filter(
            id__in=[i for i, _ in ordered]
        ).select_related("node")
    }
    hits = [
        SearchHit(
            node_version_id=nv_id,
            node_id=by_id[nv_id].node_id,
            path=by_id[nv_id].node.path,
            heading=by_id[nv_id].node.heading,
            body_text=by_id[nv_id].body_text,
            score=score,
            component_scores={"fts": score},
            chunk_id=None,
        )
        for nv_id, score in ordered
        if nv_id in by_id
    ]
    return hits, total


def trigram_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    similarity_threshold: float = 0.1,
    source_slug: str | None = None,
    metadata_contains: dict | None = None,
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
    src_join, src_where, src_params = _source_filter_clause(
        source_slug, metadata_contains
    )
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
        ORDER BY score DESC, nv.id
        LIMIT %s;
    """
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("SET LOCAL pg_trgm.similarity_threshold = %s;", [similarity_threshold])
        cur.execute(sql, [query, query, *vis_params, *src_params, limit])
        return [(int(row[0]), float(row[1])) for row in cur.fetchall()]


# Reporter-citation pattern: <volume> <reporter words> [series] <page>, e.g.
# "763 N.W.2d 862", "111 N.W.2d 753", "253 Iowa 378", "1 Morris 1". The reporter
# is one or more capitalized abbreviation tokens (N.W., Iowa, Morris, U.S., F.,
# Cal. Rptr.), optionally followed by a series token (2d/3d/4th). Anchored on a
# leading volume integer and a trailing page integer so it does NOT fire on prose
# like "Article I Section 17" or a bare statute ref like "598.41" — only on an
# actual reporter cite. ``extract_citations`` returns the matched spans verbatim
# so they can be matched against the stored ``source_metadata.citations`` array.
_CITATION_RE = re.compile(
    r"\b\d{1,4}\s+"  # volume
    r"(?:[A-Z][A-Za-z.]*\.?\s*){1,4}?"  # 1-4 reporter abbreviation tokens
    r"(?:\d+[a-z]{1,2}\s+)?"  # optional series: 2d / 3d / 4th
    r"\d{1,5}\b"  # page
)


def extract_citations(query: str) -> list[str]:
    """Pull reporter citations out of a free-text query, whitespace-normalized.

    Returns ``[]`` when the query carries no citation — which is the common case,
    so callers can cheaply skip the citation retriever entirely."""
    out: list[str] = []
    for m in _CITATION_RE.finditer(query):
        norm = " ".join(m.group(0).split())
        if norm not in out:
            out.append(norm)
    return out


def citation_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    source_slug: str | None = None,
) -> list[tuple[int, float]]:
    """Exact reporter-citation lookup — the retrieval path the bi-encoder, FTS,
    and trigram all lack.

    A reporter citation ("763 N.W.2d 862") is stored in the decision's
    ``source_metadata.citations`` array, NOT in the opinion body text, so FTS
    can't see it, it's semantically empty to the embedder, and trigram only
    matches headings. This retriever extracts any citation from the query and
    matches it against the stored array via jsonb containment (``@>``, served by
    the ``node_source_metadata_gin`` jsonb_path_ops index), matching either the
    hit node's own metadata or its parent decision's (caselaw citations live on
    the *cluster*, while the embedded/returned unit is the child *opinion*). All
    matches are exact, so every returned version scores 1.0; RRF consumes rank,
    not magnitude, and downstream cluster-collapse dedups multiple opinions of
    the same decision.

    Returns ``[]`` for citation-free queries (no overhead, no fusion noise)."""
    cites = extract_citations(query)
    if not cites:
        return []

    visibility, vis_params = _approved_filter_clause(include_pending)
    ors: list[str] = []
    cite_params: list = []
    for c in cites:
        j = json.dumps({"citations": [c]})
        ors.append("(n.source_metadata @> %s::jsonb OR p.source_metadata @> %s::jsonb)")
        cite_params += [j, j]
    cite_where = "(" + " OR ".join(ors) + ")"

    src_join = ""
    src_where = ""
    src_params: list = []
    if source_slug:
        src_join = "JOIN corpus_source s ON s.id = n.source_id"
        src_where = "AND s.slug = %s"
        src_params = [source_slug]

    sql = f"""
        SELECT nv.id
        FROM corpus_nodeversion nv
        JOIN corpus_node n ON n.id = nv.node_id
        LEFT JOIN corpus_node p ON p.id = n.parent_id
        {src_join}
        WHERE nv.effective_to IS NULL
          {visibility}
          {src_where}
          AND {cite_where}
        ORDER BY nv.id
        LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [*vis_params, *src_params, *cite_params, limit])
        return [(int(row[0]), 1.0) for row in cur.fetchall()]


# Capitalized word, length >= 3, not an ALL-CAPS acronym (DNA, OWI, U.S.) — the
# shape of a party surname in a query ("Hansen", "Puntenney", "Baldwin").
_NAME_TOKEN_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")

# Capitalized words that look like names but aren't parties: sentence openers,
# procedural/structural legal terms, and connectors that show up capitalized in
# legal queries. A token here is never treated as a party name. (Rare conceptual
# caps like "Abrogation"/"Warrantless" and ubiquitous ones like "Iowa" are
# screened by the heading document-frequency band instead, so this list only has
# to cover the common-English / common-legal middle.)
_CASE_NAME_STOP = frozenset(
    """
    the a an and or of in on at to for by with from under over into nor but
    does do did is are was were will would shall should can could may might must
    whether what when where why how who which that this these those
    article section amendment clause constitution constitutional code chapter act
    statute rule subsection paragraph title division
    state states united supreme court courts county counties city board panel
    commission department district attorney general office bureau agency
    appeal appellant appellee defendant plaintiff petitioner respondent matter
    opinion motion order judgment petition application doctrine standard
    first second third fourth fifth sixth seventh eighth ninth tenth
    fiduciary categorical warrantless suspicionless spectator
    """.split()
)

# A party surname is selective in the case-name (heading) space: it appears in
# *some* decision headings but not a huge fraction. This band screens out both
# conceptual caps that hit zero headings and ubiquitous terms ("Iowa" ~11k
# headings, "Can" ~1.3k) that slip past the stoplist. Measured separation on the
# eval set: real names land at 3-125, the noise extremes outside [1, 250].
MIN_NAME_HEADING_DF = 1
MAX_NAME_HEADING_DF = 250


def extract_case_names(query: str) -> list[str]:
    """Pull candidate party surnames from a query — capitalized, non-stoplisted
    tokens, citations stripped first so a reporter abbreviation isn't mistaken
    for a name. Returns ``[]`` for the common case (no name), so the case-name
    retriever can be skipped cheaply. This is a *candidate* list; the retriever
    then screens each by heading frequency before using it."""
    text = _CITATION_RE.sub(" ", query)
    out: list[str] = []
    for m in _NAME_TOKEN_RE.finditer(text):
        w = m.group(0)
        if w.lower() in _CASE_NAME_STOP or w in out:
            continue
        out.append(w)
    return out


def case_name_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    source_slug: str | None = None,
) -> list[tuple[int, float]]:
    """Party-name + concept retriever — the path that lets "Hansen joint physical
    care factors 598.41" find *In re Marriage of Hansen*.

    The disambiguating signal in a name query is the party name, but no other
    retriever can use it: the embedder doesn't weight a proper noun, FTS can't
    isolate the seminal case from the thousands of decisions that cite it, and
    trigram fuzzy-matches the *whole* query string against headings (so even a
    bare surname drowns among same-named cases). This retriever instead
    intersects two precise filters — the case *name* (matched on the decision
    heading, which for caselaw lives on the parent cluster, NOT the opinion node)
    AND the residual *concept* (FTS over the body once the name and any citation
    are removed) — and ranks the intersection by concept relevance. The
    intersection is self-limiting: a misfired "name" that no real party matches,
    or one whose cases don't match the concept, simply yields nothing.

    Returns ``[]`` when the query has no name, no name survives the heading-
    frequency screen, or nothing satisfies both filters."""
    cands = extract_case_names(query)
    if not cands:
        return []

    visibility, vis_params = _approved_filter_clause(include_pending)
    df_src = "AND s.slug = %s" if source_slug else ""
    names: list[str] = []
    with connection.cursor() as cur:
        for tok in cands:
            cur.execute(
                f"""SELECT count(*) FROM corpus_node n
                    JOIN corpus_source s ON s.id = n.source_id
                    WHERE n.parent_id IS NULL AND n.heading ILIKE %s {df_src};""",
                ["%" + tok + "%", *( [source_slug] if source_slug else [] )],
            )
            df = cur.fetchone()[0]
            if MIN_NAME_HEADING_DF <= df <= MAX_NAME_HEADING_DF:
                names.append(tok)
    if not names:
        return []

    # residual concept = query minus citations minus the surviving name tokens.
    residual = _CITATION_RE.sub(" ", query)
    for tok in names:
        residual = re.sub(rf"\b{re.escape(tok)}\b", " ", residual)
    residual = " ".join(residual.split())

    name_ors: list[str] = []
    name_params: list = []
    for tok in names:
        name_ors.append("(n.heading ILIKE %s OR p.heading ILIKE %s)")
        name_params += ["%" + tok + "%", "%" + tok + "%"]
    name_where = "(" + " OR ".join(name_ors) + ")"

    src_join = ""
    src_where = ""
    src_params: list = []
    if source_slug:
        src_join = "JOIN corpus_source s ON s.id = n.source_id"
        src_where = "AND s.slug = %s"
        src_params = [source_slug]

    sql = f"""
        SELECT nv.id,
               ts_rank_cd(nv.search_vector,
                          websearch_to_tsquery('english', %s)) AS score
        FROM corpus_nodeversion nv
        JOIN corpus_node n ON n.id = nv.node_id
        LEFT JOIN corpus_node p ON p.id = n.parent_id
        {src_join}
        WHERE nv.effective_to IS NULL
          {visibility}
          {src_where}
          AND {name_where}
          AND (%s = '' OR nv.search_vector @@ websearch_to_tsquery('english', %s))
        ORDER BY score DESC, nv.id
        LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(
            sql,
            [residual, *vis_params, *src_params, *name_params,
             residual, residual, limit],
        )
        return [(int(row[0]), float(row[1])) for row in cur.fetchall()]


def _merge_version_chunk_hits(
    version_hits: list[tuple[int, float]],
    chunk_hits: list[tuple[int, float, int]],
    limit: int,
) -> tuple[list[tuple[int, float]], dict[int, int]]:
    """Union whole-version and chunk-rolled-up vector hits, keeping the higher
    score per version. Returns ``(merged 2-tuples sorted desc, {version_id:
    winning_chunk_id})`` where the chunk map only carries versions whose kept
    score came from a chunk.

    The returned 2-tuple list is byte-identical to the pre-PR2 ``vector_search``
    output (same early-returns, same merge, same tiebreak) so every 2-tuple
    caller is unaffected; the chunk map is additive context for callers that ask
    for it via ``with_chunks=True``."""
    chunk_pairs = [(vid, score) for vid, score, _ in chunk_hits]
    chunk_by_vid = {vid: cid for vid, _, cid in chunk_hits}
    # In practice version- and chunk-embedded corpora are disjoint, so one side
    # is empty: preserve the exact pre-PR2 early-return behaviour.
    if not chunk_hits:
        return version_hits, {}
    if not version_hits:
        return chunk_pairs, dict(chunk_by_vid)

    best: dict[int, float] = {}
    prov: dict[int, int | None] = {}
    for vid, score in version_hits:
        if vid not in best or score > best[vid]:
            best[vid] = score
            prov[vid] = None
    for vid, score in chunk_pairs:
        if vid not in best or score > best[vid]:
            best[vid] = score
            prov[vid] = chunk_by_vid[vid]
    ranked = sorted(best.items(), key=lambda r: (r[1], -r[0]), reverse=True)[:limit]
    merged = [(vid, score) for vid, score in ranked]
    chunk_map = {vid: prov[vid] for vid, _ in ranked if prov.get(vid) is not None}
    return merged, chunk_map


def vector_search(
    query: str,
    *,
    limit: int = RETRIEVER_TOP_N,
    include_pending: bool = False,
    client: EmbeddingClient | None = None,
    source_slug: str | None = None,
    metadata_contains: dict | None = None,
    with_chunks: bool = False,
) -> list[tuple[int, float]] | tuple[list[tuple[int, float]], dict[int, int]]:
    """Semantic search via pgvector cosine distance, returning
    ``[(node_version_id, similarity), ...]`` (similarity = 1 - cosine_distance,
    larger == closer, matching the other retrievers).

    Two indexes are queried and merged, because the corpus is embedded at two
    granularities: statutes/rules carry one embedding on the whole NodeVersion,
    while caselaw is embedded per passage in NodeChunk. The chunk hits are
    rolled up to their version (best-scoring chunk wins), then unioned with the
    version-level hits keeping the higher score per version. In practice the two
    are disjoint — a caselaw version has chunks and a NULL version embedding; a
    statute has a version embedding and no chunks — so the merge just routes by
    whatever was embedded, with no double counting.

    ``with_chunks=True`` additionally returns the ``{version_id:
    winning_chunk_id}`` map (as ``(hits, chunk_map)``) so ``hybrid_search`` can
    record which passage won a caselaw version. The default (``False``) returns
    the bare 2-tuple list exactly as before — every existing caller relies on
    that shape."""

    if not query.strip():
        return ([], {}) if with_chunks else []
    vector = embed_query_cached(query, client=client)
    vector_literal = "[" + ",".join(f"{x:.7f}" for x in vector) + "]"

    version_hits = _vector_search_versions(
        vector_literal,
        limit=limit,
        include_pending=include_pending,
        source_slug=source_slug,
        metadata_contains=metadata_contains,
    )
    chunk_hits = _vector_search_chunks(
        vector_literal,
        limit=limit,
        include_pending=include_pending,
        source_slug=source_slug,
        metadata_contains=metadata_contains,
    )
    merged, chunk_map = _merge_version_chunk_hits(version_hits, chunk_hits, limit)
    if with_chunks:
        return merged, chunk_map
    return merged


def _vector_search_versions(
    vector_literal: str,
    *,
    limit: int,
    include_pending: bool,
    source_slug: str | None,
    metadata_contains: dict | None,
) -> list[tuple[int, float]]:
    """Whole-NodeVersion embeddings (statutes/rules embed whole)."""
    visibility, vis_params = _approved_filter_clause(include_pending)
    src_join, src_where, src_params = _source_filter_clause(
        source_slug, metadata_contains
    )
    sql = f"""
        SELECT nv.id,
               1 - (nv.embedding <=> %s::vector) AS score
        FROM corpus_nodeversion nv
        {src_join}
        WHERE nv.effective_to IS NULL
          AND nv.embedding IS NOT NULL
          {visibility}
          {src_where}
        ORDER BY nv.embedding <=> %s::vector, nv.id
        LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(
            sql, [vector_literal, *vis_params, *src_params, vector_literal, limit]
        )
        return [(int(row[0]), float(row[1])) for row in cur.fetchall()]


def _vector_search_chunks(
    vector_literal: str,
    *,
    limit: int,
    include_pending: bool,
    source_slug: str | None,
    metadata_contains: dict | None,
) -> list[tuple[int, float, int]]:
    """Passage-level NodeChunk embeddings (caselaw), rolled up to the version.

    Returns ``[(version_id, best_score, winning_chunk_id), ...]`` — the chunk id
    is the passage whose embedding gave the version its best score, which
    ``retrieve_context`` later excerpts so the model reads the matched holding
    rather than the opinion head.

    The HNSW index serves ``ORDER BY embedding <=> q LIMIT k``; we over-fetch
    (``CHUNK_OVERFETCH × limit``) because many chunks collapse onto one version,
    then keep the best chunk per version. ``_source_filter_clause`` joins on
    ``nv.node_id``, and a chunk's version is the *opinion* node whose parent is
    the decision — so the existing parent-aware metadata filter already scopes
    caselaw facets (court / precedential status) without an extra hop.

    Caveat: filtered ANN can under-return if a selective filter rejects most of
    the top-k; fine while chunks exist for one source, revisit (raise overfetch
    / ef_search) once multiple sources are chunked."""
    candidate_cap = max(limit * CHUNK_OVERFETCH, limit)
    visibility, vis_params = _approved_filter_clause(include_pending)
    src_join, src_where, src_params = _source_filter_clause(
        source_slug, metadata_contains
    )
    sql = f"""
        SELECT nv.id,
               1 - (c.embedding <=> %s::vector) AS score,
               c.id AS chunk_id
        FROM corpus_nodechunk c
        JOIN corpus_nodeversion nv ON nv.id = c.version_id
        {src_join}
        WHERE nv.effective_to IS NULL
          AND c.embedding IS NOT NULL
          {visibility}
          {src_where}
        ORDER BY c.embedding <=> %s::vector, nv.id
        LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(
            sql,
            [vector_literal, *vis_params, *src_params, vector_literal, candidate_cap],
        )
        rows = cur.fetchall()

    # Keep the best-scoring chunk per version (the rollup) AND remember which
    # chunk it was. Iteration order is best-distance-first from the index, so the
    # strict ``>`` keeps the first (closest) chunk on ties — deterministic.
    best: dict[int, tuple[float, int]] = {}
    for vid, score, chunk_id in rows:
        vid, score, chunk_id = int(vid), float(score), int(chunk_id)
        if vid not in best or score > best[vid][0]:
            best[vid] = (score, chunk_id)
    return sorted(
        ((vid, sc, cid) for vid, (sc, cid) in best.items()),
        key=lambda r: (r[1], -r[0]),
        reverse=True,
    )[:limit]


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[tuple[int, float]]],
    *,
    k: int = RRF_K,
    weights: dict[str, float] | None = None,
) -> list[tuple[int, float, dict[str, float]]]:
    """Fuse multiple ranked lists into one.

    For each list, item at rank r contributes ``weight·1/(k+r)`` to its fused
    score, where ``weight`` is ``weights[retriever_name]`` (default 1.0 — i.e.
    plain unweighted RRF when ``weights`` is None/empty). Returns
    ``[(id, fused_score, per_retriever_scores), ...]`` sorted desc.

    ``weights`` lets a strong retriever (the dense vector path) out-vote weak
    ones (fuzzy trigram, lexical fts) so their agreement on a near-miss can't
    demote a confident rank-1 dense hit — see ``RETRIEVER_WEIGHTS``. The
    per-retriever raw scores stored in ``components`` are the *unweighted*
    originals (for debug/explain), unaffected by ``weights``.

    The fused score is unitless and only meaningful relative to other items
    in the same fusion call."""

    weights = weights or {}
    fused: dict[int, float] = {}
    components: dict[int, dict[str, float]] = {}

    for retriever_name, ranking in ranked_lists.items():
        weight = weights.get(retriever_name, 1.0)
        for rank, (item_id, raw_score) in enumerate(ranking, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + weight * (1.0 / (k + rank))
            components.setdefault(item_id, {})[retriever_name] = raw_score

    return sorted(
        (
            (item_id, score, components.get(item_id, {}))
            for item_id, score in fused.items()
        ),
        # Score DESC, then node_version_id ASC — a deterministic tiebreak so the
        # fused order is stable across requests (required for stable pagination).
        key=lambda row: (row[1], -row[0]),
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
    use_trigram: bool = True,
    use_citation: bool = True,
    use_case_name: bool = True,
    source_slug: str | None = None,
    metadata_contains: dict | None = None,
    weights: dict[str, float] | None = None,
) -> list[SearchHit]:
    """The public entrypoint. Runs FTS + trigram + (optional) vector and
    fuses the rankings with RRF.

    ``expander`` is applied before FTS/trigram so they pick up Iowa
    terms-of-art the user didn't type. The vector retriever uses the original
    query — embeddings already capture semantic equivalence, so expansion
    would just add noise.

    ``use_vector=False`` skips embeddings — set it during dev when no Voyage
    key is available and you don't want fake vectors polluting the ranking.

    ``use_trigram=False`` skips the fuzzy heading retriever. Trigram is a
    single-token typo/partial-title tool; on a multi-word query it fuzzy-matches
    unrelated headings (``apple`` ≈ ``appeal``) and RRF-unions them into the
    results, so callers doing precise multi-term search should turn it off.

    ``use_citation`` adds an exact reporter-citation retriever. It is a no-op
    unless the query actually contains a citation (e.g. "763 N.W.2d 862"), so it
    is on by default — it surfaces a case looked up by its cite, which no other
    retriever can (the cite lives in ``source_metadata``, not the body text).

    ``use_case_name`` adds a party-name + concept retriever (e.g. "Hansen joint
    physical care factors"). Also a no-op unless a likely party name is present,
    so on by default — it intersects the case name (decision heading) with the
    residual concept (FTS), surfacing the named case where the embedder/FTS alone
    can't isolate it from its progeny.

    ``metadata_contains`` adds a ``source_metadata @> {...}`` filter pushed into
    every retriever (pre-fusion), for caselaw facets like court / precedential
    status. Pair it with ``source_slug`` so the scoped node join is present and
    the jsonb_path_ops GIN index is used.

    ``weights`` overrides the per-retriever fusion weights; ``None`` uses the
    production default ``RETRIEVER_WEIGHTS`` (dense-dominant). Pass ``{}`` for
    plain equal-weight RRF — the eval harness uses this to A/B the two."""

    if not query.strip():
        return []

    expanded = expander.expand(query) if expander is not None else query

    rankings: dict[str, list[tuple[int, float]]] = {
        "fts": fts_search(
            expanded,
            limit=per_retriever,
            include_pending=include_pending,
            source_slug=source_slug,
            metadata_contains=metadata_contains,
        ),
    }
    if use_trigram:
        rankings["trigram"] = trigram_search(
            expanded,
            limit=per_retriever,
            include_pending=include_pending,
            source_slug=source_slug,
            metadata_contains=metadata_contains,
        )
    cite_hits: list[tuple[int, float]] = []
    if use_citation:
        cite_hits = citation_search(
            query,
            limit=per_retriever,
            include_pending=include_pending,
            source_slug=source_slug,
        )
    if use_case_name:
        name_hits = case_name_search(
            query,
            limit=per_retriever,
            include_pending=include_pending,
            source_slug=source_slug,
        )
        if name_hits:
            rankings["case_name"] = name_hits
    vector_chunk_map: dict[int, int] = {}
    if use_vector:
        rankings["vector"], vector_chunk_map = vector_search(
            query,
            limit=per_retriever,
            include_pending=include_pending,
            client=client,
            source_slug=source_slug,
            metadata_contains=metadata_contains,
            with_chunks=True,
        )

    fused = reciprocal_rank_fusion(
        rankings, weights=RETRIEVER_WEIGHTS if weights is None else weights
    )

    # Exact reporter-citation matches are known-item lookups (precision ~1.0), so
    # they take precedence over the fused ranking rather than being folded into
    # RRF — where a single high-confidence vote loses to several weak retrievers
    # agreeing on a near-miss (observed: an exact-cite case fused to rank ~8
    # behind FTS/trigram noise). Prepend them in match order, dedup, then fill
    # with the fused remainder. A citation-free query leaves ``cite_hits`` empty,
    # so this is a no-op for ordinary search.
    cite_set = {i for i, _ in cite_hits}
    top_score = (fused[0][1] + 1.0) if fused else 1.0
    ordered: list[tuple[int, float, dict[str, float]]] = [
        (i, top_score, {"citation": 1.0}) for i, _ in cite_hits
    ]
    ordered += [row for row in fused if row[0] not in cite_set]
    ordered = ordered[:limit]
    if not ordered:
        return []

    ids = [row[0] for row in ordered]
    rows = NodeVersion.objects.filter(id__in=ids).select_related("node")
    by_id = {r.id: r for r in rows}

    hits: list[SearchHit] = []
    for nv_id, score, components in ordered:
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
                # The winning chunk only exists when the dense retriever
                # surfaced this version; a cite/FTS-only hit keeps None.
                chunk_id=vector_chunk_map.get(nv.id),
            )
        )
    return hits


def search_iter_node_version_ids(
    hits: Iterable[SearchHit],
) -> list[int]:
    """Convenience for callers that just want the ID list."""
    return [h.node_version_id for h in hits]
