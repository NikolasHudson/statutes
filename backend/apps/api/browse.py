"""Read-only corpus browser.

Public (no API key): this is just a navigable table of contents over text
that is already public law. It only ever exposes the *approved*, currently
effective version of a node — pending ingests stay invisible here exactly as
they do everywhere else.

Shape is deliberately tree-shaped so a thin UI can drill:
    sources → chapters → rules/sections → content
"""

from __future__ import annotations

import hashlib
import json

from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router

from apps.corpus.models import Node, Source
from apps.corpus.services.lookups import (
    citation_links,
    current_version,
    lookup_citation,
    official_url_for_node,
)
from apps.corpus.services.search import hybrid_search

browse_router = Router()

# Browse only ever serves approved, currently-effective public law, and that
# only changes when an admin approves an ingest. So let Cloudflare (and the
# browser) absorb repeat reads: a short shared-cache TTL caps staleness to a
# minute while killing the per-navigation origin/DB hit, and a payload ETag
# lets a revalidation come back as a 32-byte 304.
_BROWSE_CACHE_CONTROL = "public, s-maxage=60, stale-while-revalidate=600"


def _cached_json(request, payload) -> HttpResponse:
    """Serialize ``payload`` with an ETag + cache headers, and short-circuit
    to ``304 Not Modified`` when the client's If-None-Match still matches.

    Returned directly from a Ninja operation, which passes HttpResponse
    instances through untouched (no double serialization)."""
    body = json.dumps(payload, separators=(",", ":"), default=str)
    etag = f'"{hashlib.sha1(body.encode()).hexdigest()[:16]}"'

    if request.headers.get("If-None-Match") == etag:
        resp: HttpResponse = HttpResponseNotModified()
    else:
        # safe=False: list_sources returns a top-level JSON array.
        resp = JsonResponse(
            payload, safe=False, json_dumps_params={"default": str}
        )
    resp["ETag"] = etag
    resp["Cache-Control"] = _BROWSE_CACHE_CONTROL
    return resp


def _citation(node: Node) -> str:
    abbr = node.source.citation_abbreviation
    return f"{abbr} {node.path}".strip()


def _official_url(node: Node) -> str:
    """Prefer the chapter PDF we captured at ingest (the Court Rules URL
    template needs an edition date the generic helper can't fill). Fall back
    to the source template for sources that format cleanly (Iowa Code)."""
    if node.source_metadata.get("chapter_pdf_url"):
        return node.source_metadata["chapter_pdf_url"]
    if node.parent_id and node.parent and node.parent.source_metadata.get(
        "chapter_pdf_url"
    ):
        return node.parent.source_metadata["chapter_pdf_url"]
    return official_url_for_node(node)


@browse_router.get("/sources", auth=None)
def list_sources(request):
    """Every source with its top-level node count, for the landing list."""
    out = []
    for s in Source.objects.select_related("jurisdiction").all():
        types = {nt.key: nt for nt in s.node_types.all()}
        top_key = "chapter" if "chapter" in types else min(
            types.values(), key=lambda nt: nt.level
        ).key if types else None
        leaf_keys = [k for k in ("rule", "section") if k in types]
        out.append(
            {
                "slug": s.slug,
                "name": s.name,
                "abbreviation": s.citation_abbreviation,
                "jurisdiction": s.jurisdiction.name,
                "chapters": Node.objects.filter(
                    source=s, node_type__key=top_key
                ).count()
                if top_key
                else 0,
                "entries": Node.objects.filter(
                    source=s, node_type__key__in=leaf_keys, is_repealed=False
                ).count(),
                "entry_label": types[leaf_keys[0]].label_plural
                if leaf_keys
                else "Entries",
            }
        )
    return _cached_json(request, out)


@browse_router.get("/sources/{slug}/chapters", auth=None)
def list_chapters(request, slug: str):
    """Chapters (top level) for a source, each with its child count."""
    source = get_object_or_404(Source, slug=slug)
    chapters = (
        Node.objects.filter(source=source, node_type__key="chapter")
        .annotate(
            child_count=Count(
                "children",
                filter=Q(children__is_repealed=False),
            )
        )
        .order_by("path")
    )
    # path is a string ("1".."70"); sort numerically for a sane TOC.
    rows = sorted(chapters, key=lambda n: _intkey(n.ordinal))
    return _cached_json(request, {
        "source": {"slug": source.slug, "name": source.name},
        "chapters": [
            {
                "id": c.id,
                "ordinal": c.ordinal,
                "heading": c.heading,
                "reserved": c.is_repealed,
                "child_count": c.child_count,
            }
            for c in rows
        ],
    })


@browse_router.get("/chapters/{int:chapter_id}", auth=None)
def chapter_detail(request, chapter_id: int):
    """A chapter and the list of its children (rules / sections)."""
    chapter = get_object_or_404(
        Node.objects.select_related("source", "node_type"), pk=chapter_id
    )
    children = (
        Node.objects.filter(parent=chapter, is_repealed=False)
        # ``source`` is needed by _citation() for every child — without it the
        # list comprehension below issues one SELECT per child (N+1).
        .select_related("node_type", "source")
        .order_by("path")
    )
    rows = sorted(children, key=lambda n: _ordkey(n.ordinal))
    return _cached_json(request, {
        "id": chapter.id,
        "type": chapter.node_type.label_singular,
        "source_slug": chapter.source.slug,
        # ``path`` is the citation-native permalink key (#/<slug>/<path>);
        # for a chapter that's just the bare chapter number ("714").
        "path": chapter.path,
        "citation": _citation(chapter),
        "ordinal": chapter.ordinal,
        "heading": chapter.heading,
        "reserved": chapter.is_repealed,
        "official_url": _official_url(chapter),
        "metadata": chapter.source_metadata,
        "children": [
            {
                "id": n.id,
                "type": n.node_type.label_singular,
                "ordinal": n.ordinal,
                "citation": _citation(n),
                "heading": n.heading,
                "division": n.source_metadata.get("division", ""),
            }
            for n in rows
        ],
    })


@browse_router.get("/nodes/{int:node_id}", auth=None)
def node_detail(request, node_id: int):
    """A single node with its currently effective approved content."""
    node = get_object_or_404(
        # ``parent__source`` so _citation(node.parent) below doesn't fire an
        # extra SELECT for the parent's source.
        Node.objects.select_related(
            "source", "node_type", "parent", "parent__source"
        ),
        pk=node_id,
    )
    version = current_version(node)

    # Inline cross-reference links. Scoped to Iowa Code for now (Court Rules
    # use colon paths + a 2-level hierarchy the citation parser isn't tuned
    # for yet). Two extra queries, constant in the citation count — cheap
    # enough for an endpoint that's already edge-cached for a minute.
    cross_refs: list[dict] = []
    if version is not None and node.source.slug == "iowa-code":
        cross_refs = [
            {
                "text": link.raw,
                "path": link.target_path,
                "node_id": link.target_node_id,
            }
            for link in citation_links(
                version.body_text,
                source=node.source,
                exclude_node_id=node.id,
            )
        ]

    return _cached_json(request, {
        "id": node.id,
        "type": node.node_type.label_singular,
        "source": node.source.name,
        "source_slug": node.source.slug,
        # Citation-native permalink key — see chapter_detail.
        "path": node.path,
        "citation": _citation(node),
        "heading": node.heading,
        "chapter": (
            {"id": node.parent_id, "citation": _citation(node.parent)}
            if node.parent_id
            else None
        ),
        "division": node.source_metadata.get("division", ""),
        "official_url": _official_url(node),
        "history": node.source_metadata.get("history_brackets", []),
        "body_text": version.body_text if version else "",
        "effective_from": version.effective_from.isoformat() if version else None,
        "has_content": version is not None,
        "cross_refs": cross_refs,
    })


@browse_router.get("/resolve", auth=None)
def resolve_node(request, source: str, cite: str):
    """Resolve a citation to a node id, for citation-native permalinks.

    The router turns ``#/iowa-code/714.16`` into a call here, then opens
    the returned node through the normal node/chapter path. Mirrors the
    authenticated ``/api/lookup`` contract (never guesses — an unresolved
    cite comes back ``found:false`` with same-chapter candidates) but is
    public and shaped for the browser rather than for citation rendering.
    """
    src = Source.objects.filter(slug=source).first()
    if src is None:
        return _cached_json(request, {"found": False, "candidates": []})
    lr = lookup_citation(cite, source=src)
    if lr.found and lr.node is not None:
        return _cached_json(request, {
            "found": True,
            "node_id": lr.node.id,
            "path": lr.node.path,
            "is_chapter": lr.citation.is_chapter_only,
        })
    return _cached_json(request, {
        "found": False,
        "candidates": [
            {"node_id": n.id, "path": n.path, "heading": n.heading}
            for n in lr.candidates
        ],
    })


# Public browse search is keyword-only (FTS + trigram, RRF-fused) — no vector
# embeddings and no reranker, so an unauthenticated box can't run up a Voyage
# bill and stays instant. Semantic retrieval lives behind the authenticated
# chat surface, not here.
SEARCH_LIMIT_DEFAULT = 25
SEARCH_LIMIT_MAX = 50
# Don't fire a corpus query on a stray keystroke / single letter.
SEARCH_MIN_QUERY_LEN = 2
SNIPPET_CHARS = 240


def _search_snippet(body: str, query: str) -> str:
    """A ~240-char excerpt centered on the first query-term hit, so a result
    row shows *why* it matched rather than always the section's opening words.
    Falls back to a head excerpt when no term is found (e.g. a pure trigram
    fuzzy match)."""
    body = " ".join(body.split())
    if len(body) <= SNIPPET_CHARS:
        return body

    lowered = body.lower()
    pos = -1
    for term in (t for t in query.lower().split() if len(t) >= 3):
        pos = lowered.find(term)
        if pos != -1:
            break

    if pos == -1:
        return body[: SNIPPET_CHARS - 1].rsplit(" ", 1)[0].rstrip() + "…"

    start = max(0, pos - SNIPPET_CHARS // 3)
    end = min(len(body), start + SNIPPET_CHARS)
    snippet = body[start:end]
    if start > 0:
        snippet = "…" + snippet.split(" ", 1)[-1]
    if end < len(body):
        snippet = snippet.rsplit(" ", 1)[0] + "…"
    return snippet.strip()


def _search_row(
    node: Node, body_text: str, query: str, *, exact: bool = False
) -> dict:
    """Browse-shaped result row. ``node_id`` is all the UI needs to open the
    hit — it reuses the same node→chapter deep-link resolution the chat
    source cards use. ``body_text`` is passed in (the search hit already
    carries it) to avoid a per-row version query."""
    parent = node.parent
    return {
        "node_id": node.id,
        "type": node.node_type.label_singular,
        "citation": _citation(node),
        "source": node.source.name,
        "source_slug": node.source.slug,
        "chapter": (
            {"ordinal": parent.ordinal or parent.path, "heading": parent.heading}
            if parent is not None
            else None
        ),
        "heading": node.heading,
        "snippet": _search_snippet(body_text or "", query),
        "exact": exact,
    }


@browse_router.get("/search", auth=None)
def search(request, q: str, source: str | None = None, limit: int = SEARCH_LIMIT_DEFAULT):
    """Keyword search across the *approved, currently effective* corpus.

    Visibility is identical to the rest of browse: ``hybrid_search`` defaults
    to ``include_pending=False`` + ``review_status=approved``, so a pending
    ingest never leaks here.

    A citation-shaped query (``714.16``, ``32:1.10``) is short-circuited to an
    exact lookup and pinned as the top result — the retrievers index heading
    and body text but not ``node.path``, so a bare citation would otherwise
    rank poorly or miss."""
    q = (q or "").strip()
    limit = max(1, min(limit, SEARCH_LIMIT_MAX))
    scope_source = (
        Source.objects.filter(slug=source).first() if source else None
    )
    empty = {"query": q, "scope": source, "count": 0, "results": []}
    if len(q) < SEARCH_MIN_QUERY_LEN:
        return _cached_json(request, empty)

    results: list[dict] = []
    pinned_node_id: int | None = None

    # Exact-citation short-circuit. Best-effort: a parser quirk must never
    # take down keyword search, so swallow anything and fall through.
    try:
        lr = lookup_citation(q, source=scope_source)
        if (
            lr.found
            and lr.node is not None
            and lr.version is not None
            and not lr.citation.is_chapter_only
        ):
            node = (
                Node.objects.select_related("source", "node_type", "parent")
                .get(pk=lr.node.id)
            )
            results.append(
                _search_row(node, lr.version.body_text, q, exact=True)
            )
            pinned_node_id = node.id
    except Exception:  # noqa: BLE001 — search must degrade, never 500
        pass

    hits = hybrid_search(q, limit=limit, use_vector=False, source_slug=source)
    nodes = {
        n.id: n
        for n in Node.objects.filter(
            id__in=[h.node_id for h in hits]
        ).select_related("source", "node_type", "parent")
    }
    for h in hits:
        node = nodes.get(h.node_id)
        if node is None or node.id == pinned_node_id:
            continue
        results.append(_search_row(node, h.body_text, q))
        if len(results) >= limit:
            break

    # Search visibility is identical to the rest of browse (approved + current
    # only), so it earns the same edge cache. The ETag covers query + scope +
    # results, so the CDN keys per distinct query and a revalidation of a
    # repeated search comes back as a 304 instead of paying the retrievers.
    return _cached_json(
        request,
        {"query": q, "scope": source, "count": len(results), "results": results},
    )


def _intkey(s: str) -> tuple:
    try:
        return (0, int(s))
    except ValueError:
        return (1, s)


def _ordkey(s: str) -> tuple:
    """Sort rule ordinals like '1.402', '1.402A', '1.1001' naturally."""
    parts = []
    for chunk in s.replace(":", ".").split("."):
        if chunk.isdigit():
            parts.append((0, int(chunk), ""))
        else:
            head = "".join(c for c in chunk if c.isdigit())
            tail = "".join(c for c in chunk if not c.isdigit())
            parts.append((0, int(head) if head else 0, tail))
    return tuple(parts)
