"""ORM → schema adapters.

Kept separate from ``schemas.py`` so the schema file stays a pure type
declaration that can be imported by the MCP server, generated SDKs, and
tests without pulling in the ORM."""

from __future__ import annotations

import datetime as dt

from apps.citations.parser import Citation
from apps.corpus.models import Node, NodeVersion
from apps.corpus.services.lookups import (
    AmendmentRow,
    CrossRefRow,
    DefinitionHit,
    LookupResult,
    ValidationItem,
    ValidationReport,
    official_url_for_node,
)
from apps.corpus.services.search import SearchHit

from .schemas import (
    AmendmentOut,
    CitationOut,
    ChapterOut,
    CrossRefOut,
    DefinitionOut,
    HistoryOut,
    LookupOut,
    NodeRef,
    SearchHitOut,
    SectionOut,
    ValidateResponse,
    ValidationItemOut,
    ValidationSummary,
    VersionOut,
)


def node_ref(node: Node) -> NodeRef:
    return NodeRef(
        id=node.id,
        path=node.path,
        heading=node.heading,
        source_slug=node.source.slug,
        is_repealed=node.is_repealed,
        official_url=official_url_for_node(node),
    )


def version_out(version: NodeVersion) -> VersionOut:
    return VersionOut(
        id=version.id,
        body_text=version.body_text,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        enacted_by=version.enacted_by,
        review_status=version.review_status,
        content_hash=version.content_hash,
    )


def section_out(node: Node, version: NodeVersion | None, as_of: dt.date) -> SectionOut:
    return SectionOut(
        node=node_ref(node),
        version=version_out(version) if version is not None else None,
        as_of_date=as_of,
    )


def citation_out(citation: Citation) -> CitationOut:
    return CitationOut(
        raw=citation.raw,
        chapter=citation.chapter,
        section=citation.section,
        subdivisions=list(citation.subdivisions),
    )


def lookup_out(result: LookupResult, as_of: dt.date) -> LookupOut:
    section = None
    chapter = None
    if result.found:
        # found implies node is set; whether it's section- or chapter-level
        # is determined by the Citation, not the node by itself.
        if result.citation.is_chapter_only:
            chapter = ChapterOut(
                node=node_ref(result.node),  # type: ignore[arg-type]
                sections=[node_ref(n) for n in result.sections],
                as_of_date=as_of,
            )
        else:
            section = section_out(result.node, result.version, as_of)  # type: ignore[arg-type]
    return LookupOut(
        found=result.found,
        citation=citation_out(result.citation),
        section=section,
        chapter=chapter,
        candidates=[node_ref(n) for n in result.candidates],
        parse_error=result.parse_error,
        as_of_date=as_of,
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _snippet(body: str, max_len: int = 280) -> str:
    body = body.strip().replace("\n", " ")
    if len(body) <= max_len:
        return body
    return body[: max_len - 1].rstrip() + "…"


def search_hit_out(hit: SearchHit, node: Node) -> SearchHitOut:
    return SearchHitOut(
        node=node_ref(node),
        snippet=_snippet(hit.body_text),
        score=hit.score,
        component_scores=hit.component_scores,
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def history_out(
    node: Node, versions: list[NodeVersion], as_of: dt.date
) -> HistoryOut:
    return HistoryOut(
        node=node_ref(node),
        versions=[version_out(v) for v in versions],
        as_of_date=as_of,
    )


# ---------------------------------------------------------------------------
# Cross refs
# ---------------------------------------------------------------------------


def cross_ref_out(row: CrossRefRow) -> CrossRefOut:
    return CrossRefOut(
        direction=row.direction,
        other=node_ref(row.other_node) if row.other_node is not None else None,
        external_text=row.external_text,
        kind=row.kind,
    )


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


def definition_out(hit: DefinitionHit) -> DefinitionOut:
    return DefinitionOut(
        term=hit.term,
        definition=hit.definition,
        node=node_ref(hit.node),
        version_id=hit.version.id,
    )


# ---------------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------------


def amendment_out(row: AmendmentRow) -> AmendmentOut:
    return AmendmentOut(
        node=node_ref(row.node),
        version=version_out(row.version),
        change_kind=row.change_kind,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_VALIDATION_BODY_EXCERPT_MAX = 800


def _validation_body_excerpt(body: str) -> str:
    body = body.rstrip()
    if len(body) <= _VALIDATION_BODY_EXCERPT_MAX:
        return body
    cut = body[:_VALIDATION_BODY_EXCERPT_MAX]
    last_space = cut.rfind(" ")
    if last_space > _VALIDATION_BODY_EXCERPT_MAX - 80:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def validation_item_out(item: ValidationItem) -> ValidationItemOut:
    return ValidationItemOut(
        raw=item.raw,
        span=[item.span[0], item.span[1]],
        status=item.status,
        citation=citation_out(item.citation) if item.citation else None,
        node=node_ref(item.node) if item.node else None,
        version=version_out(item.version) if item.version else None,
        body_excerpt=(
            _validation_body_excerpt(item.version.body_text)
            if item.version else None
        ),
        candidates=[node_ref(n) for n in item.candidates],
        parse_error=item.parse_error,
    )


def validate_response(report: ValidationReport, as_of: dt.date) -> ValidateResponse:
    return ValidateResponse(
        summary=ValidationSummary(
            total=report.total,
            valid=report.count("valid"),
            repealed=report.count("repealed"),
            not_found=report.count("not_found"),
            parse_error=report.count("parse_error"),
        ),
        items=[validation_item_out(i) for i in report.items],
        as_of_date=as_of,
    )
