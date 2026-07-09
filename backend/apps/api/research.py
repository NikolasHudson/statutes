"""Authenticated research search — the intent-routed search surface.

The public ``/api/browse/search`` stays keyword-only, edge-cached and
unlogged (an unauthenticated box must not run up a Voyage bill). This
endpoint is its signed-in sibling and routes by what the query *is*:

* **citation** ("714.16", "998 N.W.2d 646") — pinned exact document, then
  keyword follow-on results.
* **boolean** (terms-and-connectors) — pure keyword via ``fts_search_paged``:
  a deterministic, exhaustive match set with an honest total and true deep
  pagination. No vector, no reranker — that is the contract connectors imply.
* **natural** (everything else) — the production dense pipeline
  (``retrieve_context``: hybrid pool → Voyage rerank → cluster dedup), depth
  capped at ``NATURAL_DEPTH`` reranked results. Quoted phrases inside a
  natural query become hard contains-filters on the pool.

Responses are per-user work products: ``Cache-Control: private, no-store``
(never the browse edge cache). Every call is logged unattributed via
``record_search_log`` — the SearchLog table is what sequences connector
support and ranking work.
"""

from __future__ import annotations

import html
import re
import time
from collections import Counter

from django.db import DatabaseError
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from ninja import Router

from apps.api.search_common import (
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    SEARCH_MIN_QUERY_LEN,
    _DOC_TYPE_SLUG,
    _normalize_fts_query,
    _resolve_reporter_citation,
    _search_row,
)
from apps.api.session_auth import session_auth
from apps.api.trace_capture import record_search_log
from apps.corpus.models import Court, CrossReference, Node, Source
from apps.corpus.services.lookups import lookup_citation
from apps.corpus.services.retrieval import (
    _treatment_for,
    retrieve_context,
    treatment_payload,
)
from apps.corpus.services.search import fts_search_paged, search_facets_fts
from apps.corpus.services.search_intent import (
    MODE_BOOLEAN,
    MODE_CITATION,
    MODE_NATURAL,
    classify_query,
)

research_router = Router()

# Natural mode returns the reranked pool, not an exhaustive match set — depth
# is capped by how many candidates the cross-encoder sees. 50 ≈ five pages;
# past that the UI offers the terms-and-connectors mode, which paginates the
# full match set.
NATURAL_DEPTH = 50
NATURAL_POOL = 100

# URL `mode` values (short, shareable) → classifier overrides.
_MODE_PARAM = {"tc": MODE_BOOLEAN, "boolean": MODE_BOOLEAN, "natural": MODE_NATURAL}
# URL `sort` values → fts_search_paged order keys. Natural mode is
# relevance-only in Phase 1 (a date-sorted top-50 pool would be misleading).
_SORT_ORDER = {"relevance": "rank", "date_desc": "date_desc", "date_asc": "date_asc"}


def _no_store(payload: dict, status: int = 200) -> HttpResponse:
    """Search results are per-user work product: keep every cache out."""
    resp = JsonResponse(payload, status=status)
    resp["Cache-Control"] = "private, no-store"
    return resp


def _pin_citation(q: str, effective_source: str | None, scope_source) -> dict | None:
    """Resolve a citation-shaped query to its pinned exact row, or None.
    Mirrors the public browse short-circuit; best-effort — a parser quirk must
    never take down search."""
    try:
        lr = lookup_citation(q, source=scope_source)
        if (
            lr.found
            and lr.node is not None
            and lr.version is not None
            and not lr.citation.is_chapter_only
        ):
            node = Node.objects.select_related("source", "node_type", "parent").get(
                pk=lr.node.id
            )
            return _search_row(node, lr.version.body_text, q, exact=True)
    except Exception:  # noqa: BLE001 — degrade, never 500
        pass
    if effective_source in (None, "iowa-caselaw"):
        try:
            dec_id = _resolve_reporter_citation(q)
            if dec_id is not None:
                node = Node.objects.select_related(
                    "source", "node_type", "parent"
                ).get(pk=dec_id)
                return _search_row(node, "", q, exact=True)
        except Exception:  # noqa: BLE001
            pass
    return None


# ts_headline sentinels — control chars can't occur in body text, so splitting
# on them can never be confused by document content. No HTML crosses the wire:
# the client renders {text, hit} segments as plain text nodes.
_HL_START = "\x02"
_HL_STOP = "\x03"
_HEADLINE_OPTS = (
    f"StartSel={_HL_START}, StopSel={_HL_STOP}, "
    "MaxFragments=2, MaxWords=30, MinWords=10, FragmentDelimiter= … "
)


def _segments_from_sentinels(text: str) -> list[dict]:
    """Split sentinel-marked headline text into [{text, hit}, ...]."""
    segments: list[dict] = []
    for i, part in enumerate(text.split(_HL_START)):
        if i == 0:
            if part:
                segments.append({"text": part, "hit": False})
            continue
        hit, _, rest = part.partition(_HL_STOP)
        if hit:
            segments.append({"text": hit, "hit": True})
        if rest:
            segments.append({"text": rest, "hit": False})
    return segments


def _headline_segments(
    version_ids: list[int], tsquery: str, tsquery_func: str
) -> dict[int, list[dict]]:
    """Server-side highlighted snippets for one page of boolean-mode rows via
    ``ts_headline`` (the page is ≤ SEARCH_LIMIT_MAX rows, so the per-document
    parse cost stays bounded). Best-effort: on any failure the caller keeps
    the plain centered snippet."""
    if not version_ids:
        return {}
    if tsquery_func not in ("websearch_to_tsquery", "to_tsquery"):
        return {}
    from django.db import connection

    sql = f"""
        SELECT id, ts_headline('english', body_text,
                               {tsquery_func}('english', %s), %s)
        FROM corpus_nodeversion WHERE id = ANY(%s);
    """
    try:
        with connection.cursor() as cur:
            cur.execute(sql, [tsquery, _HEADLINE_OPTS, version_ids])
            return {
                int(vid): _segments_from_sentinels(text or "")
                for vid, text in cur.fetchall()
            }
    except Exception:  # noqa: BLE001 — highlighting must never break search
        return {}


def _mark_segments(text: str, query: str) -> list[dict]:
    """Mark query-term occurrences in an already-chosen snippet (natural mode:
    the chunk-aware passage snippet) into the same {text, hit} shape."""
    terms = [t for t in re.findall(r"[\w']+", query.lower()) if len(t) >= 3]
    if not text or not terms:
        return [{"text": text, "hit": False}] if text else []
    pattern = re.compile(
        "(" + "|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True)) + ")",
        re.IGNORECASE,
    )
    return [
        {"text": part, "hit": bool(pattern.fullmatch(part))}
        for part in pattern.split(text)
        if part
    ]


def _cited_by_counts(decision_ids: list[int]) -> dict[int, int]:
    """Distinct citing decisions per page decision, from the caselaw citation
    graph (edges are opinion→opinion; both sides aggregate through the parent
    decision). Graph edges arrive with the quarterly bulk reload, so very
    recent cases legitimately show no count yet."""
    if not decision_ids:
        return {}
    rows = (
        CrossReference.objects.filter(
            source="caselaw_graph", to_node__parent_id__in=decision_ids
        )
        .values("to_node__parent_id")
        .annotate(n=Count("from_version__node__parent_id", distinct=True))
    )
    return {r["to_node__parent_id"]: r["n"] for r in rows}


def _attach_row_extras(
    rows: list[dict],
    nodes_by_id: dict[int, Node],
    segments_by_version: dict[int, list[dict]] | None = None,
    version_by_node: dict[int, int] | None = None,
) -> None:
    """Phase-2 row enrichment, applied to one page of rows in place:
    treatment badge (only when a real flag exists), cited-by counts for
    cases, and server snippet segments when available."""
    case_ids = [r["case_id"] for r in rows if r["case_id"] is not None]
    cited = _cited_by_counts(case_ids)
    for r in rows:
        node = nodes_by_id.get(r["node_id"])
        r["cited_by"] = cited.get(r["case_id"]) if r["case_id"] else None
        r["treatment"] = None
        if node is not None and r["kind"] == "case":
            flag = _treatment_for(node)
            if flag.status != "unknown":
                r["treatment"] = treatment_payload(flag)
        if segments_by_version and version_by_node:
            segs = segments_by_version.get(version_by_node.get(r["node_id"], -1))
            if segs:
                r["snippet_segments"] = segs


def _rows_for_hits(hits, q: str) -> tuple[list[dict], dict[int, Node]]:
    """Hydrate SearchHit-shaped objects into browse-shaped rows (one node
    fetch for the batch). Also returns the node map so callers can enrich
    rows without refetching."""
    nodes = {
        n.id: n
        for n in Node.objects.filter(id__in=[h.node_id for h in hits]).select_related(
            "source", "node_type", "parent"
        )
    }
    rows = []
    for h in hits:
        node = nodes.get(h.node_id)
        if node is not None:
            rows.append(_search_row(node, h.body_text, q))
    return rows, nodes


def _facets_payload_exact(counts: dict, basis: str) -> dict:
    """Format ``search_facets_fts`` output (or Counter-equivalents) into the
    response shape — same court entry shape as /api/browse/cases facets."""
    courts = {
        c.court_id: c
        for c in Court.objects.filter(court_id__in=list(counts["courts"]))
    }
    return {
        "basis": basis,
        "doc_types": [
            {"slug": slug, "count": n}
            for slug, n in sorted(
                counts["sources"].items(), key=lambda kv: -kv[1]
            )
        ],
        "courts": [
            {
                "court_id": cid,
                "court_name": courts[cid].name if cid in courts else cid,
                "court_level": courts[cid].level if cid in courts else None,
                "count": n,
            }
            for cid, n in sorted(counts["courts"].items(), key=lambda kv: -kv[1])
        ],
        "statuses": [
            {"status": s, "count": n}
            for s, n in sorted(counts["statuses"].items(), key=lambda kv: -kv[1])
        ],
        "decades": [
            {"decade": d, "count": n}
            for d, n in sorted(counts["decades"].items())
        ],
    }


@research_router.get("/search", auth=session_auth)
def research_search(
    request,
    q: str,
    mode: str | None = None,
    source: str | None = None,
    doc_type: str | None = None,
    court: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "relevance",
    facets: bool = False,
    limit: int = SEARCH_LIMIT_DEFAULT,
    offset: int = 0,
):
    started = time.monotonic()
    q = (q or "").strip()
    limit = max(1, min(limit, SEARCH_LIMIT_MAX))
    offset = max(0, offset)
    if sort not in _SORT_ORDER:
        sort = "relevance"

    # Scope resolution — identical rules to public browse: explicit slug wins,
    # else the doc_type alias; any caselaw-only filter implies the cases scope.
    effective_source = source or _DOC_TYPE_SLUG.get((doc_type or "").lower())
    if court or status or date_from or date_to:
        effective_source = "iowa-caselaw"
    scope_source = (
        Source.objects.filter(slug=effective_source).first()
        if effective_source
        else None
    )
    md: dict = {}
    if court:
        md["court_id"] = court
    if status:
        md["precedential_status"] = status
    metadata_contains = md or None

    intent = classify_query(q, mode_override=_MODE_PARAM.get(mode or ""))

    def payload(
        results: list[dict],
        total: int,
        *,
        total_exact: bool,
        facet_data: dict | None = None,
        sort_path: str = "ranked",
    ) -> dict:
        return {
            "query": q,
            "scope": effective_source,
            "offset": offset,
            "limit": limit,
            "count": len(results),
            "total": total,
            "has_more": offset + limit < total,
            "results": results,
            "mode": intent.mode,
            "mode_source": intent.mode_source,
            "detection": intent.detection_payload(),
            "total_exact": total_exact,
            "facets": facet_data,
            "sort": sort,
            # "keyword" when a date sort forced the deterministic path even
            # though the query classified as natural (a date-sorted top-50
            # reranked pool would be misleading; the full match set is honest).
            "sort_path": sort_path,
        }

    if len(q) < SEARCH_MIN_QUERY_LEN:
        return _no_store(payload([], 0, total_exact=True))

    filters_logged = {
        "source": source,
        "doc_type": doc_type,
        "court": court,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "sort": sort,
    }

    def log(result_count: int, total: int, total_exact: bool, error: str = "") -> None:
        record_search_log(
            user=getattr(request, "user", None),
            query=q,
            mode=intent.mode,
            mode_source=intent.mode_source,
            detection=intent.detection_payload(),
            filters=filters_logged,
            offset=offset,
            limit=limit,
            result_count=result_count,
            total=total,
            total_exact=total_exact,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=error,
        )

    # ---- citation mode: pinned exact document + keyword follow-on ----------
    pinned: dict | None = None
    if intent.mode == MODE_CITATION:
        pinned = _pin_citation(q, effective_source, scope_source)
        if pinned is None:
            # Shape matched but nothing resolved — it wasn't a citation after
            # all ("2019 tax 100"). Reclassify and fall through.
            intent = classify_query(
                q, mode_override=_MODE_PARAM.get(mode or ""), citation_ok=False
            )

    # ---- exhaustive keyword path: boolean mode, or a natural query whose
    # ---- date sort demands the complete match set --------------------------
    if intent.mode == MODE_BOOLEAN or (
        intent.mode == MODE_NATURAL and sort != "relevance"
    ):
        if intent.mode == MODE_BOOLEAN:
            tsq = intent.tsquery or ""
            func = intent.tsquery_func or "websearch_to_tsquery"
        else:
            # Date-sorting the top-50 reranked pool would silently hide
            # everything below the rerank ceiling; the deterministic keyword
            # set is complete, so it is the honest thing to sort.
            tsq = _normalize_fts_query(q)
            func = "websearch_to_tsquery"
        try:
            hits, total = fts_search_paged(
                tsq,
                tsquery_func=func,
                limit=limit,
                offset=offset,
                source_slug=effective_source,
                metadata_contains=metadata_contains,
                date_from=date_from,
                date_to=date_to,
                order=_SORT_ORDER[sort],
            )
        except DatabaseError:
            out = payload([], 0, total_exact=True, sort_path="keyword")
            out["error"] = (
                "Couldn't parse the terms-and-connectors query. Check the "
                "operators and try again."
            )
            log(0, 0, True, error="tsquery parse failure")
            return _no_store(out, status=400)
        rows, nodes = _rows_for_hits(hits, q)
        _attach_row_extras(
            rows,
            nodes,
            _headline_segments([h.node_version_id for h in hits], tsq, func),
            {h.node_id: h.node_version_id for h in hits},
        )
        facet_data = None
        if facets:
            facet_data = _facets_payload_exact(
                search_facets_fts(
                    tsq,
                    tsquery_func=func,
                    source_slug=effective_source,
                    metadata_contains=metadata_contains,
                    date_from=date_from,
                    date_to=date_to,
                ),
                "all_matches",
            )
        log(len(rows), total, True)
        return _no_store(
            payload(
                rows,
                total,
                total_exact=True,
                facet_data=facet_data,
                sort_path="keyword",
            )
        )

    # ---- citation / natural ------------------------------------------------
    if intent.mode == MODE_CITATION:
        # Keyword follow-on below the pin: what else mentions this citation.
        try:
            hits, total = fts_search_paged(
                _normalize_fts_query(q),
                limit=limit,
                offset=max(0, offset - 1),
                source_slug=effective_source,
                metadata_contains=metadata_contains,
                date_from=date_from,
                date_to=date_to,
            )
        except DatabaseError:
            hits, total = [], 0
        follow_rows, nodes = _rows_for_hits(hits, q)
        rows = [r for r in follow_rows if r["node_id"] != pinned["node_id"]]
        if offset == 0:
            rows = [pinned, *rows][:limit]
        pinned_node = Node.objects.select_related(
            "source", "node_type", "parent"
        ).filter(pk=pinned["node_id"]).first()
        if pinned_node is not None:
            nodes = {**nodes, pinned_node.id: pinned_node}
        _attach_row_extras(rows, nodes)
        results, total = rows, total + 1
        log(len(results), total, True)
        return _no_store(payload(results, total, total_exact=True, sort_path="keyword"))

    # Natural: the production dense pipeline. Quoted phrases hard-filter the
    # pool; depth is the reranked ceiling, so `total` is "top N", not a count.
    ctx = retrieve_context(
        q,
        source_slug=effective_source,
        use_vector=True,
        candidate_pool=NATURAL_POOL,
        display_limit=NATURAL_DEPTH,
        rerank=True,
        enrich_bodies=False,
        u_order=False,
        dedup_clusters=True,
        metadata_contains=metadata_contains,
        require_phrases=intent.phrases or None,
    )
    # Rows are built for the WHOLE pool (≤ NATURAL_DEPTH) before the date
    # filter and page slice: `date_filed` lives on the decision node, which
    # _search_row resolves, and `total` must reflect the filtered pool.
    # Facet counters run over the same filtered pool — labeled
    # `basis: "top_results"` because they describe the reranked pool, not the
    # whole corpus (that is boolean mode's job).
    nodes = {
        n.id: n
        for n in Node.objects.filter(
            id__in=[p.node_id for p in ctx.passages]
        ).select_related("source", "node_type", "parent")
    }
    rows = []
    fc: dict[str, Counter] = {
        "sources": Counter(), "courts": Counter(),
        "statuses": Counter(), "decades": Counter(),
    }
    for p in ctx.passages:
        node = nodes.get(p.node_id)
        if node is None:
            continue
        row = _search_row(node, "", q)
        # The pipeline's chunk-aware snippet beats a head excerpt: it is the
        # passage that actually matched (and, for caselaw, the winning chunk).
        # Escaped to keep the browse snippet contract (plain text, no markup);
        # segments carry the same text unescaped (the client renders them as
        # text nodes, never HTML).
        if p.snippet:
            row["snippet"] = html.escape(p.snippet)
            row["snippet_segments"] = _mark_segments(p.snippet, q)
        if (date_from or date_to) and row["kind"] == "case":
            df = row["date_filed"] or ""
            if date_from and df < date_from:
                continue
            if date_to and df > date_to:
                continue
        rows.append(row)
        fc["sources"][row["source_slug"]] += 1
        if row["kind"] == "case":
            decision = (
                node.parent
                if node.node_type.key == "opinion" and node.parent is not None
                else node
            )
            md = decision.source_metadata or {}
            if md.get("court_id"):
                fc["courts"][md["court_id"]] += 1
            if md.get("precedential_status"):
                fc["statuses"][md["precedential_status"]] += 1
            df = md.get("date_filed") or ""
            if len(df) >= 4 and df[:4].isdigit():
                fc["decades"][df[:3] + "0"] += 1

    total = len(rows)
    page = rows[offset : offset + limit]
    page_node_ids = {r["node_id"] for r in page}
    _attach_row_extras(page, {i: n for i, n in nodes.items() if i in page_node_ids})
    facet_data = (
        _facets_payload_exact({k: dict(v) for k, v in fc.items()}, "top_results")
        if facets
        else None
    )
    log(len(page), total, False)
    return _no_store(payload(page, total, total_exact=False, facet_data=facet_data))
