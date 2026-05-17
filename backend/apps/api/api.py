"""Public REST surface for the Iowa Legal Corpus.

Mirrors the MCP tool surface so that anything an LLM can do via MCP, a
human-built integration can do via HTTP. The only intentional asymmetry:
HTTP responses include rate-limit headers; the MCP transport doesn't.

Auth: ``X-API-Key`` header. Auth failure → 401. Tier doesn't include the
feature → 403. Quota exceeded → 429.
"""

from __future__ import annotations

import datetime as dt

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Query
from ninja.errors import HttpError

from apps.corpus.models import Node, NodeVersion
from apps.corpus.services.lookups import (
    get_cross_references,
    get_definitions,
    get_section_at,
    get_section_history,
    list_recent_amendments,
    lookup_citation,
    validate_citations,
)
from apps.corpus.services.search import hybrid_search

from .accounts import account_router, auth_router
from .auth import api_key_auth, enforce_rate_limit, require_feature
from .browse import browse_router
from .chat import chat_router
from .schemas import (
    AmendmentsResponse,
    CrossRefsResponse,
    DefinitionsResponse,
    ErrorOut,
    HistoryOut,
    LookupOut,
    SearchRequest,
    SearchResponse,
    SectionOut,
    ValidateRequest,
    ValidateResponse,
)
from .serializers import (
    amendment_out,
    cross_ref_out,
    definition_out,
    history_out,
    lookup_out,
    node_ref,
    search_hit_out,
    section_out,
    validate_response,
    version_out,
)


api = NinjaAPI(title="Iowa Legal Corpus", version="0.2")
api.add_router("", chat_router)
api.add_router("/auth", auth_router)
api.add_router("/account", account_router)
api.add_router("/browse", browse_router)


# ---------------------------------------------------------------------------
# Health (public, no auth)
# ---------------------------------------------------------------------------


@api.get("/health", auth=None)
def health(request):
    return {"status": "ok"}


@api.get("/config", auth=None)
def public_config(request):
    """Frontend bootstrap config — currently just the MCP host the snippet
    generator should hand to Claude Desktop.

    On Codespaces, the forwarded URL is derivable from CODESPACE_NAME +
    GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN. Any explicit MCP_HOST env var
    wins so the same code works on a real deploy."""
    import os

    explicit = os.environ.get("MCP_HOST")
    if explicit:
        return {"mcp_host": explicit, "source": "explicit"}

    cs_name = os.environ.get("CODESPACE_NAME")
    cs_domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    cs_port = os.environ.get("MCP_HTTP_PORT", "8765")
    if cs_name and cs_domain:
        return {
            "mcp_host": f"https://{cs_name}-{cs_port}.{cs_domain}/mcp",
            "source": "codespaces",
        }

    return {"mcp_host": None, "source": "unset"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _attach_quota_headers(response, decision):
    """Add the standard X-RateLimit-* headers to a response."""
    if decision is None:
        return response
    if decision.remaining is not None:
        response["X-RateLimit-Remaining"] = str(decision.remaining)
        response["X-RateLimit-Reset"] = str(decision.reset_at_epoch)
    return response


def _gate(request, feature: str):
    """Run feature gate + rate limit. Returns the rate-limit decision so
    callers can attach headers."""
    api_key = request.auth
    require_feature(api_key, feature)
    return enforce_rate_limit(api_key)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@api.get(
    "/lookup/{citation}",
    response={200: LookupOut, 400: ErrorOut},
    auth=api_key_auth,
)
def lookup(request, citation: str, response: HttpResponse):
    """Precise citation lookup. Never fuzzy. If the input doesn't resolve,
    we return ``found: false`` plus same-chapter candidates so the caller
    can disambiguate — never a silent substitution."""
    decision = _gate(request, "lookup")
    today = dt.date.today()
    result = lookup_citation(citation)
    out = lookup_out(result, today)
    _attach_quota_headers(response, decision)
    return out


@api.post(
    "/search",
    response=SearchResponse,
    auth=api_key_auth,
)
def search(request, payload: SearchRequest, response: HttpResponse):
    """Hybrid search (FTS + trigram + vector, RRF-fused).

    ``use_vector=False`` skips the embedding retriever — useful for the
    free tier where we may not want to spend embedding budget on every
    query."""
    decision = _gate(request, "search")
    if not payload.query.strip():
        raise HttpError(400, "query must not be empty")

    today = dt.date.today()
    hits = hybrid_search(
        payload.query,
        limit=min(payload.limit, 50),
        use_vector=payload.use_vector,
    )
    nodes_by_id = {h.node_id: h for h in hits}
    rows = (
        Node.objects.filter(id__in=list(nodes_by_id))
        .select_related("source")
    )
    by_id = {r.id: r for r in rows}
    hit_outs = [
        search_hit_out(h, by_id[h.node_id])
        for h in hits
        if h.node_id in by_id
    ]
    out = SearchResponse(
        query=payload.query,
        expanded_query=None,
        hits=hit_outs,
        as_of_date=today,
    )
    _attach_quota_headers(response, decision)
    return out


@api.get(
    "/sections/{int:section_id}/history",
    response=HistoryOut,
    auth=api_key_auth,
)
def section_history(request, section_id: int, response: HttpResponse):
    decision = _gate(request, "history")
    node = _get_node(section_id)
    versions = get_section_history(node)
    out = history_out(node, versions, dt.date.today())
    _attach_quota_headers(response, decision)
    return out


@api.get(
    "/sections/{int:section_id}/at/{on_date}",
    response={200: SectionOut, 404: ErrorOut},
    auth=api_key_auth,
)
def section_at_date(request, section_id: int, on_date: dt.date, response: HttpResponse):
    """Point-in-time view: the version that was in effect on ``on_date``.

    404 if no version was effective then (e.g. before the section
    existed)."""
    decision = _gate(request, "at_date")
    node = _get_node(section_id)
    version = get_section_at(node, on_date)
    if version is None:
        raise HttpError(404, "no version effective on that date")
    out = section_out(node, version, on_date)
    _attach_quota_headers(response, decision)
    return out


@api.get(
    "/sections/{int:section_id}/cross-references",
    response=CrossRefsResponse,
    auth=api_key_auth,
)
def section_cross_references(request, section_id: int, response: HttpResponse):
    decision = _gate(request, "cross_refs")
    node = _get_node(section_id)
    rows = get_cross_references(node)
    out = CrossRefsResponse(
        node=node_ref(node),
        references=[cross_ref_out(r) for r in rows],
        as_of_date=dt.date.today(),
    )
    _attach_quota_headers(response, decision)
    return out


@api.get(
    "/definitions/{term}",
    response=DefinitionsResponse,
    auth=api_key_auth,
)
def definitions(
    request,
    term: str,
    response: HttpResponse,
    chapter: str | None = Query(None),
):
    decision = _gate(request, "definitions")
    hits = get_definitions(term, chapter=chapter)
    out = DefinitionsResponse(
        term=term,
        chapter=chapter,
        definitions=[definition_out(h) for h in hits],
        as_of_date=dt.date.today(),
    )
    _attach_quota_headers(response, decision)
    return out


@api.post(
    "/validate-citations",
    response={200: ValidateResponse, 400: ErrorOut},
    auth=api_key_auth,
)
def validate_citations_route(
    request, payload: ValidateRequest, response: HttpResponse
):
    """Bulk-check every Iowa Code citation in a chunk of text.

    The killer use case: paste a paragraph (or a whole brief), get back —
    per citation — whether it's still good law, was repealed, or never
    existed in the corpus. Each item carries a byte-span back into the
    original text so a UI can highlight problems in place.
    """
    decision = _gate(request, "validate")
    if not payload.text or not payload.text.strip():
        raise HttpError(400, "text must not be empty")
    # Cap input length to keep one request from chewing through the
    # quota; an entire 100-page brief is well under 250 KB of text.
    if len(payload.text) > 250_000:
        raise HttpError(400, "text exceeds 250,000 character limit")

    report = validate_citations(payload.text)
    out = validate_response(report, dt.date.today())
    _attach_quota_headers(response, decision)
    return out


@api.get(
    "/recent-amendments",
    response=AmendmentsResponse,
    auth=api_key_auth,
)
def recent_amendments(
    request,
    response: HttpResponse,
    since: dt.date = Query(...),
    limit: int = Query(100, ge=1, le=500),
):
    decision = _gate(request, "amendments")
    rows = list_recent_amendments(since, limit=limit)
    out = AmendmentsResponse(
        since=since,
        amendments=[amendment_out(r) for r in rows],
        as_of_date=dt.date.today(),
    )
    _attach_quota_headers(response, decision)
    return out


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _get_node(section_id: int) -> Node:
    return get_object_or_404(Node.objects.select_related("source"), pk=section_id)
