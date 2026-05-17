"""Tool implementations for the MCP server.

Each function here is the *pure* tool body — it takes JSON-able inputs,
calls into the corpus service layer, and returns a JSON-able dict. We
deliberately do NOT register these with FastMCP here, so they can be
imported and unit-tested without spinning up a full server.

Every response includes:
    ``official_url``   — link back to legis.iowa.gov for the section
    ``as_of_date``     — date the response was generated
    ``effective_from`` / ``effective_to`` on each version

So an LLM client can never accidentally cite stale text without having
seen the metadata that says when it was current. The brief calls this out
as non-negotiable: "every response includes official URL + 'as of [date]'
stamp + version metadata".

Ambiguity rule: when a citation doesn't resolve unambiguously we return
the candidate list. We never silently substitute.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.shortcuts import get_object_or_404

from apps.corpus.models import Node, NodeVersion, Source
from apps.corpus.services.lookups import (
    audit_brief,
    get_cross_references,
    get_definitions,
    get_section_at,
    get_section_history,
    list_recent_amendments,
    lookup_citation,
    official_url_for_node,
    validate_citations,
    verify_quotes,
)
from apps.corpus.services.search import hybrid_search


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _node_dict(node: Node) -> dict[str, Any]:
    # Structural context the model needs to reject out-of-context hits — e.g.
    # an appellate rule (Chapter 6) surfacing on a trial-court question. The
    # parent of a rule/section is its chapter.
    parent = node.parent
    chapter = (
        {"ordinal": parent.ordinal or parent.path, "heading": parent.heading}
        if parent is not None
        else None
    )
    return {
        "id": node.id,
        "path": node.path,
        "heading": node.heading,
        "source_slug": node.source.slug,
        "chapter": chapter,
        "division": node.source_metadata.get("division") or None,
        "is_repealed": node.is_repealed,
        "official_url": official_url_for_node(node),
        "citation": _render_citation(node),
    }


def _render_citation(node: Node) -> str:
    """Pretty citation string, per source.

    The section symbol is an Iowa Code convention; court rules (and other
    Tier 2 sources) cite as "<abbr> <number>" with no §. Using the source's
    own ``citation_abbreviation`` keeps a court rule from being mislabeled
    "Iowa Code § 32:1.7"."""
    abbr = node.source.citation_abbreviation
    if node.source.slug == "iowa-code":
        return f"{abbr} § {node.path}"
    return f"{abbr} {node.path}"


def _version_dict(v: NodeVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "body_text": v.body_text,
        "effective_from": v.effective_from.isoformat(),
        "effective_to": v.effective_to.isoformat() if v.effective_to else None,
        "enacted_by": v.enacted_by,
        "review_status": v.review_status,
        "content_hash": v.content_hash,
    }


def _today() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _resolve_lookup(citation: str, source_slug: str | None):
    """Resolve a citation against the right corpus.

    ``lookup_citation`` defaults to the Iowa Code, so a Court Rule citation
    like "1.303" would silently miss (chat then reports a "technical issue"
    and falls back to a truncated search snippet). When the chat is scoped we
    resolve against that source; when it isn't, we try every source and
    return the first hit, keeping the Iowa Code result as the fallback so
    candidate near-misses and parse errors stay meaningful.
    """
    sources = Source.objects.all()
    if source_slug:
        sources = sources.filter(slug=source_slug)
    # slug is unique only per jurisdiction, so a slug can match more than one
    # Source — try each and return the first that actually resolves rather
    # than betting on .first().
    first_result = None
    for src in sources.order_by("slug", "id"):
        r = lookup_citation(citation, source=src)
        if r.parse_error:
            return r  # a parse failure is source-independent
        if r.found:
            return r
        if first_result is None:
            first_result = r
    if first_result is not None:
        return first_result
    return lookup_citation(citation)


def lookup_citation_tool(
    citation: str, *, source_slug: str | None = None
) -> dict[str, Any]:
    """Look up a precise citation. Never fuzzy.

    ``source_slug`` scopes resolution to one corpus (e.g.
    ``"iowa-court-rules"``); when omitted, every source is tried.

    Three response shapes:

    * Section-level hit: ``found: true`` + ``section`` populated.
    * Chapter-level hit (e.g. "Chapter 714H"): ``found: true`` + ``chapter``
      populated with the chapter heading and an ordered list of section
      Nodes so the caller can render a TOC and follow up on specific
      sections.
    * Miss: ``found: false`` + ``candidates`` listing same-chapter
      near-misses. Never a silent substitution.
    """
    result = _resolve_lookup(citation, source_slug)
    today = _today()
    base: dict[str, Any] = {
        "as_of_date": today,
        "citation": {
            "raw": result.citation.raw,
            "chapter": result.citation.chapter,
            "section": result.citation.section,
            "subdivisions": list(result.citation.subdivisions),
        },
        "parse_error": result.parse_error,
        "section": None,
        "chapter": None,
        "candidates": [],
    }
    if not result.found:
        base["found"] = False
        base["candidates"] = [_node_dict(n) for n in result.candidates]
        return base

    base["found"] = True
    if result.citation.is_chapter_only:
        base["chapter"] = {
            "node": _node_dict(result.node),
            "sections": [_node_dict(n) for n in result.sections],
        }
    else:
        base["section"] = {
            "node": _node_dict(result.node),
            "version": _version_dict(result.version),
        }
    return base


def search_statutes_tool(
    query: str,
    *,
    limit: int = 20,
    use_vector: bool = True,
    source_slug: str | None = None,
) -> dict[str, Any]:
    """Hybrid search — FTS + trigram + vector, RRF-fused.

    ``source_slug`` (e.g. ``"iowa-court-rules"``) scopes the search to a
    single corpus; ``None`` searches everything."""
    if not query or not query.strip():
        return {
            "query": query,
            "hits": [],
            "as_of_date": _today(),
            "error": "query must not be empty",
        }
    hits = hybrid_search(
        query,
        limit=min(limit, 50),
        use_vector=use_vector,
        source_slug=source_slug,
    )
    nodes = {
        n.id: n
        for n in Node.objects.filter(id__in=[h.node_id for h in hits])
        .select_related("source", "parent")
    }
    out_hits = []
    for h in hits:
        node = nodes.get(h.node_id)
        if node is None:
            continue
        out_hits.append(
            {
                "node": _node_dict(node),
                "snippet": _snippet(h.body_text),
                "score": h.score,
                "component_scores": h.component_scores,
            }
        )
    return {
        "query": query,
        "hits": out_hits,
        "as_of_date": _today(),
    }


def get_version_history_tool(section_id: int) -> dict[str, Any]:
    node = _get_node(section_id)
    versions = get_section_history(node)
    return {
        "node": _node_dict(node),
        "versions": [_version_dict(v) for v in versions],
        "as_of_date": _today(),
    }


def get_section_at_date_tool(section_id: int, on_date: str) -> dict[str, Any]:
    node = _get_node(section_id)
    parsed_date = dt.date.fromisoformat(on_date)
    version = get_section_at(node, parsed_date)
    if version is None:
        return {
            "node": _node_dict(node),
            "version": None,
            "on_date": on_date,
            "as_of_date": _today(),
            "error": "no version effective on that date",
        }
    return {
        "node": _node_dict(node),
        "version": _version_dict(version),
        "on_date": on_date,
        "as_of_date": _today(),
    }


def get_cross_references_tool(section_id: int) -> dict[str, Any]:
    node = _get_node(section_id)
    rows = get_cross_references(node)
    return {
        "node": _node_dict(node),
        "references": [
            {
                "direction": r.direction,
                "other": _node_dict(r.other_node) if r.other_node else None,
                "external_text": r.external_text,
                "kind": r.kind,
            }
            for r in rows
        ],
        "as_of_date": _today(),
    }


def get_definitions_tool(
    term: str, *, chapter: str | None = None
) -> dict[str, Any]:
    hits = get_definitions(term, chapter=chapter)
    return {
        "term": term,
        "chapter": chapter,
        "definitions": [
            {
                "term": h.term,
                "definition": h.definition,
                "node": _node_dict(h.node),
                "version_id": h.version.id,
            }
            for h in hits
        ],
        "as_of_date": _today(),
    }


def list_recent_amendments_tool(
    since: str, *, limit: int = 100
) -> dict[str, Any]:
    parsed_since = dt.date.fromisoformat(since)
    rows = list_recent_amendments(parsed_since, limit=limit)
    return {
        "since": since,
        "amendments": [
            {
                "node": _node_dict(r.node),
                "version": _version_dict(r.version),
                "change_kind": r.change_kind,
            }
            for r in rows
        ],
        "as_of_date": _today(),
    }


# Max chars of section body returned per validation item. Big enough to
# carry the substantive content (definitions, elements, exceptions) so the
# LLM can compare against the brief's characterization, small enough that
# a 30-cite brief still produces a manageable response.
VALIDATION_BODY_EXCERPT_MAX = 800


def _body_excerpt(text: str, max_chars: int = VALIDATION_BODY_EXCERPT_MAX) -> str:
    """Truncate body text on a word boundary, preserving newlines so the
    LLM can still see the section's structural indentation."""
    text = text.rstrip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Back up to the last whitespace boundary so we don't slice mid-word.
    last_space = cut.rfind(" ")
    if last_space > max_chars - 80:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def validate_citations_tool(text: str) -> dict[str, Any]:
    """Bulk-check every Iowa Code citation in a chunk of text.

    Workflow attorneys actually have: paste a paragraph (or a whole brief)
    and get back, for each cited section, whether it's still good law,
    repealed, or never existed. The output is structured so an LLM can
    summarize ("3 of 4 cites valid; one was repealed in 2019") and so a
    UI can highlight problems inline using ``span``.

    Each ``valid`` item carries a ``body_excerpt`` (~800 chars of the
    section's actual text). That makes this tool useful for *substantive*
    review too — the LLM can compare what the brief says about a section
    against what the section actually says, and flag mischaracterizations
    in the same response that confirms the cite resolves.

    Per-item shape::

        {
          "raw":       "Iowa Code § 714.16",
          "span":      [12, 32],            # byte offsets in the input
          "status":    "valid"
                       | "repealed"
                       | "not_found"
                       | "parse_error",
          "citation":  {chapter, section, subdivisions, ...} | null,
          "node":      {...} | null,        # the resolved Node, when found
          "version":   {...} | null,        # the current version (valid only)
          "body_excerpt": "..." | null,     # first ~800 chars (valid only)
          "candidates":[{...}, ...],        # for not_found
          "parse_error": "..."              # for parse_error
        }
    """

    report = validate_citations(text)
    items: list[dict[str, Any]] = []
    for item in report.items:
        out: dict[str, Any] = {
            "raw": item.raw,
            "span": [item.span[0], item.span[1]],
            "status": item.status,
            "citation": (
                {
                    "raw": item.citation.raw,
                    "chapter": item.citation.chapter,
                    "section": item.citation.section,
                    "subdivisions": list(item.citation.subdivisions),
                }
                if item.citation
                else None
            ),
            "node": _node_dict(item.node) if item.node else None,
            "version": _version_dict(item.version) if item.version else None,
            "body_excerpt": (
                _body_excerpt(item.version.body_text) if item.version else None
            ),
            "candidates": [_node_dict(n) for n in item.candidates],
            "parse_error": item.parse_error,
        }
        items.append(out)

    return {
        "as_of_date": _today(),
        "summary": {
            "total": report.total,
            "valid": report.count("valid"),
            "repealed": report.count("repealed"),
            "not_found": report.count("not_found"),
            "parse_error": report.count("parse_error"),
        },
        "items": items,
    }


def verify_quote_tool(
    text: str, citation: str | None = None
) -> dict[str, Any]:
    """Check whether quoted passages in ``text`` actually appear in their
    cited sections.

    Each quoted span (delimited by straight or curly double quotes) is
    paired with the nearest citation in the surrounding text — or with
    the explicitly supplied ``citation`` if given — and FTS-matched
    against that section's body. Returns per-quote:

        {
          "quote": "...",
          "span": [start, end],            # offsets in the input text
          "status": "exact" | "fuzzy"
                  | "not_found" | "no_citation"
                  | "section_unresolved",
          "match_score": 0.0..1.0,
          "citation": {...} | null,
          "node":     {...} | null,
          "closest_passage": "..."         # excerpt of the section text
        }

    Use this to fact-check quoted statutory language in a brief — it
    catches paraphrases, attribution errors, and invented quotes
    deterministically, without LLM judgment.
    """
    report = verify_quotes(text, citation_text=citation)
    items = []
    for q in report.items:
        items.append(
            {
                "quote": q.quote,
                "span": [q.span[0], q.span[1]],
                "status": q.status,
                "match_score": q.match_score,
                "citation": (
                    {
                        "raw": q.citation.raw,
                        "chapter": q.citation.chapter,
                        "section": q.citation.section,
                        "subdivisions": list(q.citation.subdivisions),
                    }
                    if q.citation
                    else None
                ),
                "node": _node_dict(q.node) if q.node else None,
                "closest_passage": q.closest_passage,
            }
        )
    return {
        "as_of_date": _today(),
        "summary": {
            "total": report.total,
            "exact": report.count("exact"),
            "fuzzy": report.count("fuzzy"),
            "not_found": report.count("not_found"),
            "no_citation": report.count("no_citation"),
            "section_unresolved": report.count("section_unresolved"),
        },
        "items": items,
    }


def audit_brief_tool(
    text: str, since: str | None = None
) -> dict[str, Any]:
    """One-call structural + substantive review of a passage of brief text.

    Composes ``validate_citations`` (does each cite resolve / is it still
    in force?), ``verify_quote`` (does each quoted passage actually
    appear in its cited section?), and a freshness check (have any cited
    sections been amended since ``since``? — passed as an ISO date).

    The intended use case is "paste opposing counsel's brief, get back
    every problem in one round-trip": dead cites, mischaracterizations,
    misquotes, and post-filing amendments — all surfaced together so the
    LLM can produce a single coherent critique.

    Response shape::

        {
          "summary":      {...},  # flat counts
          "validation":   {...},  # full validate_citations payload
          "quotes":       {...},  # full verify_quote payload
          "amended_since":[...],  # cited sections changed after `since`
          "tables": {             # pre-rendered Markdown
            "summary":       "...",
            "citations":     "...",
            "quotes":        "...",
            "amended_since": "..."
          }
        }

    The ``tables`` field carries Markdown tables suitable for rendering
    verbatim — useful when the caller wants a ready-to-paste audit
    instead of re-formatting the structured payload.
    """
    parsed_since: dt.date | None = None
    if since:
        parsed_since = dt.date.fromisoformat(since)

    report = audit_brief(text, since=parsed_since)

    # We re-use the existing tool serializers to avoid drift.
    validation_payload = validate_citations_tool(text)
    verify_payload = verify_quote_tool(text)

    amended = [
        {
            "node": _node_dict(row.node),
            "version": _version_dict(row.new_version),
        }
        for row in report.amended_since
    ]

    summary = {
        "total_citations": validation_payload["summary"]["total"],
        "valid_citations": validation_payload["summary"]["valid"],
        "repealed_citations": validation_payload["summary"]["repealed"],
        "missing_citations": validation_payload["summary"]["not_found"],
        "total_quotes": verify_payload["summary"]["total"],
        "exact_quotes": verify_payload["summary"]["exact"],
        "fuzzy_quotes": verify_payload["summary"]["fuzzy"],
        "missed_quotes": verify_payload["summary"]["not_found"],
        "amended_since_count": len(amended),
    }

    return {
        "as_of_date": _today(),
        "since": since,
        "validation": validation_payload,
        "quotes": verify_payload,
        "amended_since": amended,
        "summary": summary,
        # Pre-rendered Markdown so the LLM (or a UI) can paste it verbatim
        # rather than re-formatting the structured payload.
        "tables": {
            "citations": _citations_table(validation_payload["items"]),
            "quotes": _quotes_table(verify_payload["items"]),
            "amended_since": _amended_table(amended, since),
            "summary": _summary_table(summary),
        },
    }


# ---------------------------------------------------------------------------
# Markdown table helpers
# ---------------------------------------------------------------------------


def _md_escape(text: str) -> str:
    """Escape pipe characters and collapse newlines so cells stay on one
    row in a Markdown table."""
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a GitHub-flavored Markdown table. Empty rows render as a
    single 'No data.' line so the LLM can tell the section ran but found
    nothing."""
    if not rows:
        return "_No items._"
    header_row = "| " + " | ".join(headers) + " |"
    sep_row = "|" + "|".join(["---"] * len(headers)) + "|"
    body_rows = [
        "| " + " | ".join(_md_escape(c) for c in r) + " |" for r in rows
    ]
    return "\n".join([header_row, sep_row] + body_rows)


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _citations_table(items: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for it in items:
        node = it.get("node")
        cit = it.get("citation") or {}
        candidate_paths = ", ".join(
            c["path"] for c in (it.get("candidates") or [])[:3]
        )
        rows.append(
            [
                it["status"],
                it["raw"],
                cit.get("chapter") or "",
                cit.get("section") or "",
                node["heading"] if node else "",
                node["official_url"] if node else "",
                candidate_paths,
            ]
        )
    return _md_table(
        [
            "Status",
            "As cited",
            "Chapter",
            "Section",
            "Heading",
            "Official URL",
            "Candidates (if missing)",
        ],
        rows,
    )


def _quotes_table(items: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for it in items:
        node = it.get("node")
        rows.append(
            [
                it["status"],
                f"{it['match_score']:.2f}",
                _truncate(it.get("quote", ""), 80),
                node["path"] if node else "",
                _truncate(it.get("closest_passage") or "", 100),
            ]
        )
    return _md_table(
        ["Status", "Score", "Quoted text", "Section", "Closest passage"],
        rows,
    )


def _amended_table(
    amended: list[dict[str, Any]], since: str | None
) -> str:
    if not amended:
        if since:
            return f"_No cited sections amended since {since}._"
        return "_No `since` date supplied; freshness check skipped._"
    rows = [
        [
            row["node"]["path"],
            row["node"]["heading"],
            row["version"]["effective_from"],
            row["node"]["official_url"],
        ]
        for row in amended
    ]
    return _md_table(
        ["Section", "Heading", "Effective from", "Official URL"], rows
    )


def _summary_table(summary: dict[str, Any]) -> str:
    rows = [
        ["Citations — total", str(summary["total_citations"])],
        ["Citations — valid", str(summary["valid_citations"])],
        ["Citations — repealed", str(summary["repealed_citations"])],
        ["Citations — missing", str(summary["missing_citations"])],
        ["Quotes — total", str(summary["total_quotes"])],
        ["Quotes — exact", str(summary["exact_quotes"])],
        ["Quotes — fuzzy", str(summary["fuzzy_quotes"])],
        ["Quotes — missed", str(summary["missed_quotes"])],
        ["Sections amended since", str(summary["amended_since_count"])],
    ]
    return _md_table(["Metric", "Count"], rows)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _get_node(section_id: int) -> Node:
    return get_object_or_404(
        Node.objects.select_related("source", "parent"), pk=section_id
    )


def _snippet(body: str, max_len: int = 280) -> str:
    body = body.strip().replace("\n", " ")
    if len(body) <= max_len:
        return body
    return body[: max_len - 1].rstrip() + "…"
