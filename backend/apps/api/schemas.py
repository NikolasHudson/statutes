"""Pydantic/Ninja schemas for the public API.

Every response that includes statute text carries:
    - ``official_url``  — link back to legis.iowa.gov
    - ``as_of_date``    — the date the response was generated
    - ``effective_from`` / ``effective_to`` on each version

So a caller can never accidentally cite stale text without having seen the
metadata that says *when* it was current.
"""

from __future__ import annotations

import datetime as dt

from ninja import Schema


# ---------------------------------------------------------------------------
# Core building blocks
# ---------------------------------------------------------------------------


class NodeRef(Schema):
    """Lightweight pointer to a Node — the bits a caller needs to fetch
    more or render a citation."""

    id: int
    path: str
    heading: str
    source_slug: str
    is_repealed: bool
    official_url: str


class VersionOut(Schema):
    """A single NodeVersion. Includes everything required to display the
    text along with provenance."""

    id: int
    body_text: str
    effective_from: dt.date
    effective_to: dt.date | None
    enacted_by: str
    review_status: str
    content_hash: str


class SectionOut(Schema):
    """A node + its currently effective version, the most common payload."""

    node: NodeRef
    version: VersionOut | None
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


class CitationOut(Schema):
    raw: str
    chapter: str
    section: str | None
    subdivisions: list[str]


class ChapterOut(Schema):
    """Chapter-level lookup result. Chapter nodes have no NodeVersion of
    their own, so we return the chapter Node plus the ordered list of
    sections in that chapter so callers can render a table of contents."""

    node: NodeRef
    sections: list[NodeRef]
    as_of_date: dt.date


class LookupOut(Schema):
    """Result of GET /api/lookup/{citation}.

    Three possible shapes:

    * ``found`` is true + ``section`` populated — section-level hit.
    * ``found`` is true + ``chapter`` populated — chapter-only hit (e.g.
      "Chapter 714H").
    * ``found`` is false + ``candidates`` populated with near-misses.

    The contract from the brief: never silently substitute. Ambiguous
    input returns candidates, never a guess.
    """

    found: bool
    citation: CitationOut
    section: SectionOut | None = None
    chapter: ChapterOut | None = None
    candidates: list[NodeRef]
    parse_error: str | None
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchRequest(Schema):
    query: str
    limit: int = 20
    use_vector: bool = True


class SearchHitOut(Schema):
    node: NodeRef
    snippet: str
    score: float
    component_scores: dict[str, float]


class SearchResponse(Schema):
    query: str
    expanded_query: str | None
    hits: list[SearchHitOut]
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# History + point-in-time
# ---------------------------------------------------------------------------


class HistoryOut(Schema):
    node: NodeRef
    versions: list[VersionOut]
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# Cross references
# ---------------------------------------------------------------------------


class CrossRefOut(Schema):
    direction: str  # "outgoing" | "incoming"
    other: NodeRef | None
    external_text: str
    kind: str


class CrossRefsResponse(Schema):
    node: NodeRef
    references: list[CrossRefOut]
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


class DefinitionOut(Schema):
    term: str
    definition: str
    node: NodeRef
    version_id: int


class DefinitionsResponse(Schema):
    term: str
    chapter: str | None
    definitions: list[DefinitionOut]
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# Recent amendments
# ---------------------------------------------------------------------------


class AmendmentOut(Schema):
    node: NodeRef
    version: VersionOut
    change_kind: str  # "new" | "amended" | "repealed"


class AmendmentsResponse(Schema):
    since: dt.date
    amendments: list[AmendmentOut]
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------


class ValidateRequest(Schema):
    text: str


class ValidationItemOut(Schema):
    """One citation found in the input text plus its resolution status.

    ``span`` is ``[start, end]`` byte offsets so a UI can highlight the
    cite in place. ``status`` is one of ``valid`` / ``repealed`` /
    ``not_found`` / ``parse_error`` (see service-layer constants).
    ``body_excerpt`` carries the first ~800 chars of the section's body
    text on ``valid`` items so an LLM caller can compare the brief's
    characterization against the actual statutory language in one pass."""

    raw: str
    span: list[int]
    status: str
    citation: CitationOut | None = None
    node: NodeRef | None = None
    version: VersionOut | None = None
    body_excerpt: str | None = None
    candidates: list[NodeRef] = []
    parse_error: str | None = None


class ValidationSummary(Schema):
    total: int
    valid: int
    repealed: int
    not_found: int
    parse_error: int


class ValidateResponse(Schema):
    summary: ValidationSummary
    items: list[ValidationItemOut]
    as_of_date: dt.date


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorOut(Schema):
    detail: str
