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
import html
import json
import re

from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.db.models import Count, Q
from django.db.models.fields.json import KeyTextTransform
from django.shortcuts import get_object_or_404
from ninja import Router

from apps.corpus.models import (
    Court,
    CrossReference,
    Edition,
    Node,
    NodeVersion,
    ReporterCitation,
    ReviewStatus,
    Source,
)
from apps.corpus.services.editions import compare_editions, section_diff
from apps.corpus.services.lookups import (
    citation_links,
    current_version,
    lookup_citation,
    official_url_for_node,
)
from apps.corpus.services.search import hybrid_search
from apps.api.search_common import (
    SEARCH_FUSED_MAX,
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    SEARCH_MIN_QUERY_LEN,
    _citation,
    _DOC_TYPE_SLUG,
    _normalize_fts_query,
    _resolve_reporter_citation,
    _search_row,
)

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
    """Every source with its top-level node count, for the landing list.

    Sources come in two shapes the browser renders differently: statute-style
    sources have a ``chapter`` tier (browsed as a chapter index) while caselaw
    has none (browsed search-first). ``kind`` / ``has_chapters`` let the UI pick
    the right index without hard-coding slugs."""
    out = []
    for s in Source.objects.select_related("jurisdiction").all():
        types = {nt.key: nt for nt in s.node_types.all()}
        has_chapters = "chapter" in types
        # Leaf tier counted as "entries": statute sections / rules, or — for a
        # chapter-less source like caselaw — its top-level decisions.
        leaf_keys = [k for k in ("rule", "section", "decision") if k in types]
        out.append(
            {
                "slug": s.slug,
                "name": s.name,
                "abbreviation": s.citation_abbreviation,
                "jurisdiction": s.jurisdiction.name,
                "kind": "statutes" if has_chapters else "caselaw",
                "has_chapters": has_chapters,
                # A chapter-less source reports 0 chapters — previously it
                # miscounted every decision as a "chapter" (76k for caselaw).
                "chapters": Node.objects.filter(
                    source=s, node_type__key="chapter"
                ).count()
                if has_chapters
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
    """Chapters (top level) for a source, each with its child count.

    Three-level sources — a level-0 tier above chapters (IAC agencies, Acts
    sessions) — additionally get ``agencies``: the same chapter rows grouped
    under their top-tier parent, in parent order, so the UI can render a
    two-level TOC (``group_label`` names the tier: "Agencies", "Sessions").
    The flat ``chapters`` list is kept for those sources too (ordered
    group-first) so consumers that don't know about groups still get a
    usable index."""
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

    def _chapter_row(c: Node) -> dict:
        return {
            "id": c.id,
            "ordinal": c.ordinal,
            "heading": c.heading,
            "reserved": c.is_repealed,
            "child_count": c.child_count,
        }

    top_type = (
        source.node_types.filter(level=0).exclude(key="chapter").first()
    )
    agencies = (
        list(Node.objects.filter(source=source, node_type=top_type))
        if top_type
        else []
    )
    if agencies:
        # Agencies sort numerically; sessions ("2024", "2023X3") sort by
        # ordinal string DESCENDING so the newest session leads the TOC.
        if top_type.key == "session":
            agencies.sort(key=lambda a: a.ordinal, reverse=True)
        else:
            agencies.sort(key=lambda a: _intkey(a.ordinal))
        by_agency: dict[int, list[Node]] = {a.id: [] for a in agencies}
        for c in chapters:
            by_agency.setdefault(c.parent_id, []).append(c)
        for group in by_agency.values():
            group.sort(key=lambda n: _intkey(n.ordinal))
        agency_rows = [
            {
                "id": a.id,
                "ordinal": a.ordinal,
                "heading": a.heading,
                "chapters": [_chapter_row(c) for c in by_agency[a.id]],
            }
            for a in agencies
        ]
        return _cached_json(request, {
            "source": {"slug": source.slug, "name": source.name},
            "group_label": top_type.label_plural,
            "agencies": agency_rows,
            "chapters": [c for a in agency_rows for c in a["chapters"]],
        })

    # path is a string ("1".."70"); sort numerically for a sane TOC.
    rows = sorted(chapters, key=lambda n: _intkey(n.ordinal))
    return _cached_json(request, {
        "source": {"slug": source.slug, "name": source.name},
        "chapters": [_chapter_row(c) for c in rows],
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
    # iowa-admin-code is included so IAC rule bodies get links as soon as the
    # citation parser learns the em-dash rule form (Phase 3) — until then the
    # parser finds nothing in IAC text and this stays an empty list.
    if version is not None and node.source.slug in ("iowa-code", "iowa-admin-code"):
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


def _caselaw_official_url(node: Node) -> str:
    """CourtListener permalink for a decision, built from its source template
    plus the cluster id/slug in source_metadata (the generic ``{year}/{path}``
    helper can't fill the caselaw ``{cl_cluster_id}/{slug}`` template)."""
    md = node.source_metadata
    try:
        return node.source.official_url_template.format(
            cl_cluster_id=md.get("cl_cluster_id", ""),
            slug=md.get("slug", ""),
        )
    except (KeyError, IndexError, AttributeError):
        return ""


# A decision's text often arrives as a single "combined" opinion whose head is
# the formal caption (court / docket / parties / counsel) and whose body then
# duplicates the separately-stored lead + concurrences. Split that prefatory
# caption off so the UI can show it once (centered) without repeating the text.
_BYLINE_RE = re.compile(
    r"^[A-Z][A-Z.\s,'’-]{2,40},\s*"
    r"(?:Chief Justice|Justice|Judge|C\.?J\.?|P\.?J\.?|J\.)\.?$"
)
_RULE_RE = re.compile(r"^[_=–—-]{3,}$")


def _split_caption(text: str) -> tuple[str, str]:
    """Return ``(caption, body)`` — the prefatory caption matter and the opinion
    body after it. The boundary is the first author byline (e.g. "HECHT,
    Justice.") or, failing that, a horizontal rule. ``("", text)`` when neither
    is found."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if _BYLINE_RE.match(s):
            return "\n".join(lines[:i]).strip(), "\n".join(lines[i:])
        if _RULE_RE.match(s) and i > 0:
            return "\n".join(lines[:i]).strip(), "\n".join(lines[i + 1 :])
    return "", text


# Caselaw browse list (the search-first caselaw index's "recent decisions" +
# court facets). Distinct from the ``/cases/{int:node_id}`` detail route below —
# the int converter means a bare ``/cases`` never collides with it.
CASES_LIMIT_DEFAULT = 25
CASES_LIMIT_MAX = 100


@browse_router.get("/cases", auth=None)
def list_cases(
    request,
    court: str | None = None,
    status: str | None = None,
    year: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = CASES_LIMIT_DEFAULT,
    offset: int = 0,
    facets: bool = False,
):
    """Iowa caselaw decisions, newest first, for the caselaw index.

    ``court`` (CourtListener slug) and ``status`` (precedential) filter via
    indexed ``source_metadata`` containment (``@>`` → ``node_source_metadata_gin``);
    ``year`` or ``date_from``/``date_to`` bound ``date_filed``. Ordering and the
    range use ``KeyTextTransform`` (``->>``) so the partial functional index
    ``node_caselaw_date_filed`` is hit — the ``has_key`` filter matches its
    partial predicate so the planner can use it. ``has_more`` is computed with a
    +1 fetch to avoid a COUNT over ~76k rows. ``facets=true`` adds per-court
    decision counts. Public + edge-cached like the rest of browse."""
    src = Source.objects.filter(slug="iowa-caselaw").first()
    if src is None:
        return _cached_json(
            request,
            {"results": [], "limit": 0, "offset": 0, "has_more": False,
             "facets": None},
        )

    limit = max(1, min(limit, CASES_LIMIT_MAX))
    offset = max(0, offset)

    # Shared filters: source + decision + status + date bounds. Court is the
    # facet's pivot dimension, so it's applied to the page list only — the facet
    # counts honor every *other* active filter (date/status) so the chip numbers
    # match the list.
    base = Node.objects.filter(
        source=src,
        node_type__key="decision",
        # Matches the partial index predicate so the planner can use it; every
        # decision carries date_filed, so this never drops a real row.
        source_metadata__has_key="date_filed",
    ).annotate(_date_filed=KeyTextTransform("date_filed", "source_metadata"))
    if status:
        base = base.filter(source_metadata__contains={"precedential_status": status})
    if year:
        base = base.filter(
            _date_filed__gte=f"{year:04d}-01-01",
            _date_filed__lte=f"{year:04d}-12-31",
        )
    if date_from:
        base = base.filter(_date_filed__gte=date_from)
    if date_to:
        base = base.filter(_date_filed__lte=date_to)

    qs = base
    if court:
        qs = qs.filter(source_metadata__contains={"court_id": court})
    qs = qs.order_by("-_date_filed", "-id")

    # +1 fetch → has_more without paying a COUNT over the whole corpus.
    page = list(qs[offset : offset + limit + 1])
    has_more = len(page) > limit
    page = page[:limit]

    facet_rows = None
    if facets:
        fqs = base.annotate(_court=KeyTextTransform("court_id", "source_metadata"))
        facet_rows = [
            {"court_id": r["_court"], "count": r["n"]}
            for r in fqs.values("_court").annotate(n=Count("id")).order_by("-n")
            if r["_court"]
        ]

    # One batched Court lookup serving both the page rows and the facet rows.
    needed = {n.source_metadata.get("court_id", "") for n in page}
    if facet_rows:
        needed |= {r["court_id"] for r in facet_rows}
    courts = {
        c.court_id: c
        for c in Court.objects.filter(court_id__in=[c for c in needed if c])
    }

    def _court_name_level(cid: str) -> tuple[str, int | None]:
        c = courts.get(cid)
        return (c.name if c else cid, c.level if c else None)

    results = []
    for n in page:
        md = n.source_metadata
        cid = md.get("court_id", "")
        cname, clevel = _court_name_level(cid)
        results.append(
            {
                "id": n.id,
                "case_name": n.heading,
                "court_id": cid,
                "court_name": md.get("court_name", "") or cname,
                "court_level": clevel,
                "date_filed": md.get("date_filed", ""),
                "docket_number": md.get("docket_number", ""),
                "precedential_status": md.get("precedential_status", ""),
                "citations": list(md.get("citations", [])),
            }
        )

    facets_payload = None
    if facet_rows is not None:
        facets_payload = {
            "courts": [
                {
                    "court_id": r["court_id"],
                    "court_name": _court_name_level(r["court_id"])[0],
                    "court_level": _court_name_level(r["court_id"])[1],
                    "count": r["count"],
                }
                for r in facet_rows
            ]
        }

    return _cached_json(
        request,
        {
            "results": results,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "facets": facets_payload,
        },
    )


@browse_router.get("/cases/{int:node_id}", auth=None)
def case_detail(request, node_id: int):
    """One Iowa caselaw decision: case metadata + optional head-matter
    (syllabus/headnotes) + every opinion (lead/concurrence/dissent) with its
    text, plus the in-corpus cases it cites. Public + edge-cached like the
    rest of the browser; serves only approved, currently-effective text."""
    decision = get_object_or_404(
        Node.objects.select_related("source", "node_type"),
        pk=node_id,
        node_type__key="decision",
    )
    md = decision.source_metadata
    head = current_version(decision)  # head-matter version, or None when absent

    opinions = list(
        Node.objects.filter(parent=decision, node_type__key="opinion")
        .select_related("node_type")
        # ordinal is the 3-digit type prefix (010 lead → 020 → 030 concurrence
        # → 040 dissent …); path tie-breaks the opinions that share an ordinal.
        .order_by("ordinal", "path")
    )
    # One query for every opinion's current (open, approved) version, and one
    # for all their outgoing inline-citation edges — constant in the opinion
    # and citation counts (no per-opinion round trips).
    versions = {
        v.node_id: v
        for v in NodeVersion.objects.filter(
            node__in=opinions,
            effective_to__isnull=True,
            review_status=ReviewStatus.APPROVED,
        )
    }
    edges: dict[int, list[CrossReference]] = {}
    version_ids = [v.id for v in versions.values()]
    if version_ids:
        refs = (
            CrossReference.objects.filter(
                from_version_id__in=version_ids, source="caselaw_link"
            )
            .select_related("to_node", "to_node__parent", "to_node__node_type")
            .order_by("id")
        )
        for ref in refs:
            edges.setdefault(ref.from_version_id, []).append(ref)

    # A "combined" (ordinal 010) opinion that coexists with separate opinions is
    # a duplicate of them prefixed by the caption — render the separate opinions
    # and lift just the caption. A lone opinion usually embeds the caption too;
    # split it off so the caption shows once, centered, above a clean body.
    caption_block = ""
    body_overrides: dict[int, str] = {}
    render_opinions = opinions
    combined = next((o for o in opinions if o.ordinal == "010"), None)
    subs = [o for o in opinions if o.ordinal != "010"]
    if combined is not None and subs:
        cver = versions.get(combined.id)
        caption_block, _ = _split_caption(cver.body_text if cver else "")
        render_opinions = subs
    elif len(opinions) == 1:
        only = opinions[0]
        over = versions.get(only.id)
        cap, body_after = _split_caption(over.body_text if over else "")
        if cap:
            caption_block = cap
            body_overrides[only.id] = body_after

    opinion_rows = []
    cited_cases: dict[int, dict] = {}
    external_texts: set[str] = set()
    for op in render_opinions:
        ver = versions.get(op.id)
        for ref in edges.get(ver.id, []) if ver else []:
            if ref.to_node_id is not None:
                cited = ref.to_node
                # Internal edges point at the cited OPINION; the case page is
                # keyed by the DECISION, so resolve to that opinion's parent.
                case_node = (
                    cited.parent
                    if cited.node_type.key == "opinion"
                    else cited
                )
                if case_node and case_node.id != decision.id:
                    row = cited_cases.setdefault(
                        case_node.id,
                        {
                            "case_id": case_node.id,
                            "case_name": case_node.heading,
                            "count": 0,
                        },
                    )
                    row["count"] += 1
            else:
                txt = " ".join((ref.external_text or "").split())
                if txt:
                    external_texts.add(txt)
        opinion_rows.append(
            {
                "id": op.id,
                "heading": op.heading,
                "type": op.source_metadata.get("type", ""),
                "author_str": op.source_metadata.get("author_str", ""),
                "per_curiam": bool(op.source_metadata.get("per_curiam")),
                "body_text": body_overrides.get(
                    op.id, ver.body_text if ver else ""
                ),
                # Display-only rich structure with linked citations, when built.
                # Suppressed for the combined-only caption-strip case (its body
                # was overridden, so the segments wouldn't match).
                "body_segments": (
                    ver.body_segments
                    if ver and op.id not in body_overrides
                    else None
                ),
                "has_content": ver is not None,
            }
        )

    court = Court.objects.filter(court_id=md.get("court_id", "")).first()

    return _cached_json(request, {
        "id": decision.id,
        "type": decision.node_type.label_singular,
        "source": decision.source.name,
        "source_slug": decision.source.slug,
        "path": decision.path,
        "cl_cluster_id": md.get("cl_cluster_id"),
        # Node.heading is the (≤500-char) case name; case_name_full is uncapped.
        "case_name": decision.heading,
        "case_name_full": md.get("case_name_full", ""),
        "court_id": md.get("court_id", ""),
        "court_name": md.get("court_name", ""),
        "court_level": court.level if court else None,
        "date_filed": md.get("date_filed", ""),
        "docket_number": md.get("docket_number", ""),
        "precedential_status": md.get("precedential_status", ""),
        "judges": md.get("judges", ""),
        "disposition": md.get("disposition", ""),
        "posture": md.get("posture", ""),
        "nature_of_suit": md.get("nature_of_suit", ""),
        # This case's own reporter citations (how to cite it).
        "citations": list(md.get("citations", [])),
        "official_url": _caselaw_official_url(decision),
        # Prefatory caption (court / docket / parties / counsel), lifted from the
        # opinion text so the UI can render it once, centered. "" when none.
        "caption_block": caption_block,
        "head_matter": head.body_text if head else None,
        "opinions": opinion_rows,
        # In-corpus authorities this case cites, most-cited first.
        "cited_cases": sorted(
            cited_cases.values(), key=lambda r: (-r["count"], r["case_name"])
        ),
        "external_citation_count": len(external_texts),
    })


@browse_router.get("/editions", auth=None)
def list_editions(request, source: str):
    """Editions registered for a source, newest first, for the diff picker."""
    src = get_object_or_404(Source, slug=source)
    editions = list(Edition.objects.filter(source=src).order_by("-as_of_date"))
    rows = [
        {"year": e.year, "label": e.label, "as_of_date": e.as_of_date}
        for e in editions
    ]
    # Sensible default comparison: the two most recent editions (older→newer).
    default = None
    if len(editions) >= 2:
        default = {"from_year": editions[1].year, "to_year": editions[0].year}
    return _cached_json(request, {
        "source": {"slug": src.slug, "name": src.name},
        "editions": rows,
        "default": default,
    })


@browse_router.get("/compare", auth=None)
def compare(request, source: str, from_year: int, to_year: int):
    """Summary of what changed between two editions: added / amended / repealed.

    Bodies are not included — the summary is row-identity only (cheap even for
    the whole corpus). Open one section's diff via ``/compare/section``.
    """
    src = get_object_or_404(Source, slug=source)
    try:
        summary = compare_editions(src, from_year, to_year)
    except Edition.DoesNotExist:
        return _cached_json(request, {"error": "unknown edition", "source": source})

    def serialize(refs):
        return [
            {
                "node_id": r.node_id,
                "path": r.path,
                "citation": r.citation,
                "heading": r.heading,
                "chapter": r.chapter,
            }
            for r in refs
        ]

    return _cached_json(request, {
        "source": src.slug,
        "from_year": summary.from_year,
        "to_year": summary.to_year,
        "from_as_of": summary.from_as_of,
        "to_as_of": summary.to_as_of,
        "counts": summary.counts,
        "covered_chapters": summary.covered_chapters,
        "added": serialize(summary.added),
        "amended": serialize(summary.amended),
        "repealed": serialize(summary.repealed),
    })


@browse_router.get("/compare/section", auth=None)
def compare_section(request, node_id: int, from_year: int, to_year: int):
    """From/to body text and a word-level diff for a single section."""
    node = get_object_or_404(
        Node.objects.select_related("source", "node_type"), pk=node_id
    )
    try:
        payload = section_diff(node, from_year, to_year)
    except Edition.DoesNotExist:
        return _cached_json(request, {"error": "unknown edition"})
    return _cached_json(request, payload)


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


@browse_router.get("/search", auth=None)
def search(
    request,
    q: str,
    source: str | None = None,
    doc_type: str | None = None,
    court: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = SEARCH_LIMIT_DEFAULT,
    offset: int = 0,
):
    """Keyword search across the *approved, currently effective* corpus.

    Visibility is identical to the rest of browse: ``hybrid_search`` defaults
    to ``include_pending=False`` + ``review_status=approved``, so a pending
    ingest never leaks here.

    A citation-shaped query is short-circuited to an exact lookup and pinned as
    the top result: a statute cite (``714.16``, ``32:1.10``) via the citation
    parser, and a reporter cite (``998 N.W.2d 646``) via ``ReporterCitation`` →
    the case it names. The retrievers index heading + body text but not the
    citation, so a bare cite would otherwise rank poorly or miss.

    Paginated via ``offset`` + ``limit`` (page size); the response carries
    ``has_more``. Depth is bounded by ``SEARCH_FUSED_MAX``.

    Fielded filters (advanced search): ``doc_type`` scopes to one corpus
    (code/rules/cases); ``court``/``status`` filter caselaw via indexed
    ``source_metadata`` containment pushed *pre-fusion*; ``date_from``/``date_to``
    bound a decision's filing date (post-filter — ISO dates sort
    lexicographically). Any caselaw-only filter forces the cases scope. Caselaw
    rows are deduped to one per decision (multiple opinions of one case would
    otherwise repeat)."""
    q = (q or "").strip()
    limit = max(1, min(limit, SEARCH_LIMIT_MAX))
    offset = max(0, offset)

    # Resolve scope: explicit slug wins, else the doc_type alias; any
    # caselaw-only filter implies the cases scope.
    effective_source = source or _DOC_TYPE_SLUG.get((doc_type or "").lower())
    caselaw_filtered = bool(court or status or date_from or date_to)
    if caselaw_filtered:
        effective_source = "iowa-caselaw"

    scope_source = (
        Source.objects.filter(slug=effective_source).first()
        if effective_source
        else None
    )
    empty = {
        "query": q,
        "scope": effective_source,
        "count": 0,
        "total": 0,
        "results": [],
        "offset": offset,
        "limit": limit,
        "has_more": False,
    }
    if len(q) < SEARCH_MIN_QUERY_LEN:
        return _cached_json(request, empty)

    # court/status → indexed containment, pushed into every retriever.
    md: dict = {}
    if court:
        md["court_id"] = court
    if status:
        md["precedential_status"] = status
    metadata_contains = md or None

    results: list[dict] = []
    seen_case_ids: set[int] = set()
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
            pinned = _search_row(node, lr.version.body_text, q, exact=True)
            results.append(pinned)
            pinned_node_id = node.id
            if pinned["case_id"] is not None:
                seen_case_ids.add(pinned["case_id"])
    except Exception:  # noqa: BLE001 — search must degrade, never 500
        pass

    # Reporter-citation pin (caselaw): "998 N.W.2d 646" -> the case it names,
    # at the very top. Only when the scope permits caselaw; an ambiguous/missing
    # cite just falls through to keyword search.
    if pinned_node_id is None and effective_source in (None, "iowa-caselaw"):
        try:
            dec_id = _resolve_reporter_citation(q)
            if dec_id is not None:
                node = Node.objects.select_related(
                    "source", "node_type", "parent"
                ).get(pk=dec_id)
                pinned = _search_row(node, "", q, exact=True)
                results.append(pinned)
                pinned_node_id = node.id
                if pinned["case_id"] is not None:
                    seen_case_ids.add(pinned["case_id"])
        except Exception:  # noqa: BLE001 — search must degrade, never 500
            pass

    # Translate boolean operators for FTS, and gate the fuzzy trigram retriever:
    # it's a single-token typo tool, so on a multi-word query it only fuzzy-
    # matches unrelated headings (apple≈appeal) and pollutes the results. A
    # single-term query still gets trigram for typo/partial-title recall.
    fts_q = _normalize_fts_query(q)
    use_trigram = len(fts_q.split()) <= 1

    # A FIXED candidate pool per query (independent of the page) so every page
    # slices the same deterministically-ordered list — the basis for stable
    # pagination. Court/status are filtered pre-fusion (indexed); the date range
    # is post-filtered and caselaw opinions dedup to one row per decision, all of
    # which the full pool below absorbs.
    hits = hybrid_search(
        fts_q,
        limit=SEARCH_FUSED_MAX,
        per_retriever=SEARCH_FUSED_MAX,
        use_vector=False,
        use_trigram=use_trigram,
        source_slug=effective_source,
        metadata_contains=metadata_contains,
    )
    nodes = {
        n.id: n
        for n in Node.objects.filter(
            id__in=[h.node_id for h in hits]
        ).select_related("source", "node_type", "parent")
    }
    # `results` is the full ordered list (any pin is already at index 0); we
    # build one past the page end to know has_more, then slice the page.
    for h in hits:
        node = nodes.get(h.node_id)
        if node is None or node.id == pinned_node_id:
            continue
        row = _search_row(node, h.body_text, q)
        # Date-range post-filter (caselaw only; ISO dates sort chronologically).
        if (date_from or date_to) and row["kind"] == "case":
            df = row["date_filed"] or ""
            if date_from and df < date_from:
                continue
            if date_to and df > date_to:
                continue
        # Collapse multiple opinion hits of one decision to a single row.
        cid = row["case_id"]
        if cid is not None:
            if cid in seen_case_ids:
                continue
            seen_case_ids.add(cid)
        results.append(row)

    has_more = offset + limit < len(results)
    page = results[offset : offset + limit]

    # Search visibility is identical to the rest of browse (approved + current
    # only), so it earns the same edge cache. The ETag covers query + scope +
    # page + offset, so the CDN keys per distinct page and a revalidation comes
    # back as a 304 instead of paying the retrievers.
    return _cached_json(
        request,
        {
            "query": q,
            "scope": effective_source,
            "offset": offset,
            "limit": limit,
            "count": len(page),
            # Fused hits available across all pages (bounded by the retriever
            # depths), so the UI can say "Showing 11–20 of 63".
            "total": len(results),
            "has_more": has_more,
            "results": page,
        },
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
