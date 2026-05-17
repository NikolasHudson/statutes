"""Read-side helpers used by the public API and the MCP server.

Everything here is pure-read (no writes). Keep the views and MCP handlers
thin: they should be parameter validation + a call into one of these
functions + schema serialization, nothing else.

Visibility rule: by default we only show *approved* current versions.
Pending versions are admin-only. Pass ``include_pending=True`` from admin
tooling.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from django.db.models import Q

from apps.citations.parser import (
    Citation,
    CitationParseError,
    parse as parse_citation,
)
from apps.citations.resolver import resolve as resolve_citation
from apps.corpus.models import (
    CrossReference,
    Node,
    NodeVersion,
    ReviewStatus,
    Source,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _approved_filter(include_pending: bool) -> Q:
    if include_pending:
        return Q()
    return Q(review_status=ReviewStatus.APPROVED)


def official_url_for_node(node: Node, *, code_year: int | None = None) -> str:
    """Format the source's URL template against this node.

    The Iowa Code template uses ``{year}`` and ``{path}`` placeholders. Year
    defaults to the current year if not supplied — the legis.iowa.gov site
    aliases the most recent code year, so this is a safe default until we
    start tracking per-NodeVersion code years.
    """
    template = node.source.official_url_template or ""
    if not template:
        return ""
    year = code_year or dt.date.today().year
    try:
        return template.format(year=year, path=node.path)
    except (KeyError, IndexError):
        return ""


def current_version(node: Node, *, include_pending: bool = False) -> NodeVersion | None:
    """The version that is in effect today (effective_to IS NULL)."""
    qs = NodeVersion.objects.filter(node=node, effective_to__isnull=True).filter(
        _approved_filter(include_pending)
    )
    return qs.order_by("-effective_from", "-id").first()


# ---------------------------------------------------------------------------
# Citation lookup
# ---------------------------------------------------------------------------


@dataclass
class LookupResult:
    """Result of a citation lookup.

    The contract from the brief: never silently substitute. If the citation
    is ambiguous or doesn't resolve, return candidates instead of guessing.

    Two shapes for a successful result:

    * **Section-level** (e.g. "714.16") — ``node`` is the section, ``version``
      is the currently effective ``NodeVersion``, ``sections`` is empty.
    * **Chapter-level** (e.g. "Chapter 714H") — ``node`` is the chapter,
      ``version`` is None (chapter Nodes have no NodeVersion), and
      ``sections`` lists every section Node under the chapter so a caller
      can render a table of contents.
    """

    citation: Citation
    node: Node | None
    version: NodeVersion | None
    candidates: list[Node]  # populated when ``node`` is None and we have guesses
    sections: list[Node] = field(default_factory=list)  # populated for chapters
    parse_error: str | None = None

    @property
    def found(self) -> bool:
        if self.node is None:
            return False
        # Section-level lookups need a current version to be useful.
        # Chapter-level lookups are "found" as long as the chapter Node
        # exists — chapter Nodes legitimately have no version themselves.
        if self.citation.is_chapter_only:
            return True
        return self.version is not None


def lookup_citation(
    citation_text: str,
    *,
    source: Source | None = None,
    include_pending: bool = False,
) -> LookupResult:
    """Parse + resolve a citation string. Returns a LookupResult.

    Source defaults to Iowa Code; pass an explicit Source if you ever need
    to look up against another corpus (Tier 2)."""

    if source is None:
        source = _default_source()

    try:
        citation = parse_citation(citation_text)
    except CitationParseError as exc:
        return LookupResult(
            citation=Citation(chapter="", section=None, raw=citation_text),
            node=None,
            version=None,
            candidates=[],
            parse_error=str(exc),
        )

    node = resolve_citation(citation, source)
    if node is None:
        # Surface near-misses: same chapter prefix sections, helpful when
        # the user typed a section number that doesn't exist (yet?). We
        # cap at 5 — anything more and the caller is better off searching.
        candidates = list(
            Node.objects.filter(
                source=source,
                path__startswith=citation.chapter + ".",
            ).order_by("path")[:5]
        )
        return LookupResult(
            citation=citation, node=None, version=None, candidates=candidates
        )

    if citation.is_chapter_only:
        # Chapter Nodes don't carry a NodeVersion. Return the chapter plus
        # an ordered list of its sections so callers can render a TOC.
        sections = list(
            Node.objects.filter(
                source=source,
                path__startswith=citation.chapter + ".",
            )
        )
        sections.sort(key=_natural_path_key)
        return LookupResult(
            citation=citation,
            node=node,
            version=None,
            candidates=[],
            sections=sections,
        )

    version = current_version(node, include_pending=include_pending)
    return LookupResult(
        citation=citation,
        node=node,
        version=version,
        candidates=[],
    )


_NATURAL_KEY_RE = re.compile(r"(\d+)")


def _natural_path_key(node: Node) -> tuple:
    """Sort key for Node.path that orders ``714H.2`` before ``714H.10``.

    Default lexicographic order would sort ``714H.10`` before ``714H.2``;
    splitting on digit runs gives us a tuple where each numeric chunk is
    compared as an int."""
    parts = _NATURAL_KEY_RE.split(node.path)
    return tuple(int(p) if p.isdigit() else p for p in parts)


# ---------------------------------------------------------------------------
# History + point-in-time
# ---------------------------------------------------------------------------


def get_section_history(
    node: Node, *, include_pending: bool = False
) -> list[NodeVersion]:
    """All versions for a node, newest effective_from first."""
    return list(
        NodeVersion.objects.filter(node=node)
        .filter(_approved_filter(include_pending))
        .order_by("-effective_from", "-id")
    )


def get_section_at(
    node: Node, on_date: dt.date, *, include_pending: bool = False
) -> NodeVersion | None:
    """Version that was in effect on ``on_date``.

    Effective range is closed-open: ``[effective_from, effective_to)``. When
    ``effective_to`` is NULL, the version is current.
    """
    qs = NodeVersion.objects.filter(
        node=node, effective_from__lte=on_date
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=on_date)
    ).filter(_approved_filter(include_pending))
    return qs.order_by("-effective_from", "-id").first()


# ---------------------------------------------------------------------------
# Cross references
# ---------------------------------------------------------------------------


@dataclass
class CrossRefRow:
    direction: str  # "outgoing" or "incoming"
    other_node: Node | None  # None for outgoing externals
    external_text: str
    kind: str  # CrossReferenceKind value


def get_cross_references(
    node: Node, *, include_pending: bool = False
) -> list[CrossRefRow]:
    """Return both directions: refs from this node's current version going
    out, and refs from any other node coming in.

    The brief explicitly wants both — attorneys want to know "what does
    this section reference" and "what references this section"."""

    out: list[CrossRefRow] = []

    version = current_version(node, include_pending=include_pending)
    if version is not None:
        for xr in (
            CrossReference.objects.filter(from_version=version)
            .select_related("to_node", "to_node__source")
        ):
            out.append(
                CrossRefRow(
                    direction="outgoing",
                    other_node=xr.to_node,
                    external_text=xr.external_text,
                    kind=xr.kind,
                )
            )

    # Incoming: any reference whose to_node is us, where the from_version is
    # a current version (effective_to IS NULL). Refs from superseded
    # versions are noise. Visibility filter applies to the from_version's
    # review_status so unapproved from_versions stay hidden.
    incoming_qs = (
        CrossReference.objects.filter(
            to_node=node, from_version__effective_to__isnull=True
        )
        .select_related(
            "from_version",
            "from_version__node",
            "from_version__node__source",
        )
    )
    if not include_pending:
        incoming_qs = incoming_qs.filter(
            from_version__review_status=ReviewStatus.APPROVED
        )
    for xr in incoming_qs:
        out.append(
            CrossRefRow(
                direction="incoming",
                other_node=xr.from_version.node,
                external_text="",
                kind=xr.kind,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


# "X means Y" / "X is defined as Y" — Iowa drafting style is remarkably
# consistent here: each defined term is quoted (or an obvious noun phrase)
# followed by "means" / "shall mean" / "is defined as". We grab the
# following sentence as the definition body.
_DEFINITION_PATTERNS = [
    re.compile(
        r'(?P<term>'
        r'["“‘’\']'
        r'[^"”‘’\']{1,60}'
        r'["”‘’\']'
        r'|'
        r'[A-Za-z][A-Za-z0-9\-\s]{0,60}?'
        r')'
        r'\s+(?:means|shall\s+mean|is\s+defined\s+as)\s+'
        r'(?P<body>[^.]{1,400}\.)',
        re.IGNORECASE,
    ),
]


@dataclass
class DefinitionHit:
    term: str
    definition: str
    node: Node
    version: NodeVersion


def get_definitions(
    term: str,
    *,
    chapter: str | None = None,
    include_pending: bool = False,
    limit: int = 25,
) -> list[DefinitionHit]:
    """Find definitions of ``term`` across current versions.

    Heuristic: scan body_text for "<term> means …" patterns. Keeps the
    matches grounded in the actual statute language rather than relying on
    a hand-curated index.
    """

    needle = term.strip().strip('"').lower()
    if not needle:
        return []

    qs = NodeVersion.objects.filter(
        effective_to__isnull=True,
        body_text__icontains=needle,
    ).filter(_approved_filter(include_pending)).select_related("node", "node__source")
    if chapter:
        qs = qs.filter(node__path__startswith=chapter + ".")

    out: list[DefinitionHit] = []
    for nv in qs[: limit * 4]:  # over-fetch, the regex pass filters more
        for pattern in _DEFINITION_PATTERNS:
            for m in pattern.finditer(nv.body_text):
                matched = m.group("term").strip().lower()
                if needle not in matched:
                    continue
                body = m.group("body").strip()
                out.append(
                    DefinitionHit(
                        term=m.group("term").strip(),
                        definition=body,
                        node=nv.node,
                        version=nv,
                    )
                )
                if len(out) >= limit:
                    return out
    return out


# ---------------------------------------------------------------------------
# Recent amendments
# ---------------------------------------------------------------------------


@dataclass
class AmendmentRow:
    node: Node
    version: NodeVersion
    change_kind: str  # "new" | "amended" | "repealed"


def list_recent_amendments(
    since: dt.date,
    *,
    include_pending: bool = False,
    limit: int = 100,
) -> list[AmendmentRow]:
    """NodeVersions whose effective_from is >= ``since``.

    Classification:
        new       — node has only one approved version
        amended   — there is a prior version with effective_to == this
                    version's effective_from
        repealed  — node.is_repealed and this is the closing version
    """

    qs = (
        NodeVersion.objects.filter(effective_from__gte=since)
        .filter(_approved_filter(include_pending))
        .select_related("node", "node__source")
        .order_by("-effective_from", "-id")[:limit]
    )

    rows: list[AmendmentRow] = []
    for nv in qs:
        if nv.node.is_repealed and nv.effective_to is not None:
            kind = "repealed"
        elif NodeVersion.objects.filter(
            node=nv.node, effective_from__lt=nv.effective_from
        ).exists():
            kind = "amended"
        else:
            kind = "new"
        rows.append(AmendmentRow(node=nv.node, version=nv, change_kind=kind))
    return rows


# ---------------------------------------------------------------------------
# Citation validation (bulk)
# ---------------------------------------------------------------------------


# Allowed states for ValidationItem.status. Plain strings (not an Enum) so
# the dataclass serializes cleanly into the MCP/REST tool surface.
VALIDATION_VALID = "valid"
VALIDATION_REPEALED = "repealed"
VALIDATION_NOT_FOUND = "not_found"
VALIDATION_PARSE_ERROR = "parse_error"


@dataclass
class ValidationItem:
    """One citation pulled from free text, with resolution status.

    The ``raw`` field is the substring as it appeared in the input. Callers
    use ``span`` to highlight the cite in the original text. ``citation``
    is None when parsing fails outright."""

    raw: str
    span: tuple[int, int]
    status: str
    citation: Citation | None
    node: Node | None = None
    version: NodeVersion | None = None
    candidates: list[Node] = field(default_factory=list)
    parse_error: str | None = None


@dataclass
class ValidationReport:
    """Result of ``validate_citations`` over a single text input."""

    items: list[ValidationItem]

    @property
    def total(self) -> int:
        return len(self.items)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)


def validate_citations(
    text: str,
    *,
    source: Source | None = None,
    include_pending: bool = False,
) -> ValidationReport:
    """Scan ``text`` for Iowa Code citations and return their status.

    Pipeline:

      1. ``find_all`` from the citation parser walks the text and yields
         every citation-shaped substring. We re-find each match to recover
         the byte span so the caller can highlight in place.
      2. Each citation is resolved against the corpus.
      3. Status is derived from the resolution outcome:
           - ``valid``        — section with a current effective version,
                                or chapter Node found.
           - ``repealed``     — Node exists but no current version (or
                                ``Node.is_repealed`` flag is set).
           - ``not_found``    — no matching Node; we surface up to 5
                                same-chapter candidates as suggestions.
           - ``parse_error``  — parser couldn't read the substring.

    Returns the report; ranking/printing is the caller's job."""

    if source is None:
        source = _default_source()

    if not text or not text.strip():
        return ValidationReport(items=[])

    items: list[ValidationItem] = []

    for match in _ITER_RE.finditer(text):
        raw = match.group(0)
        # Skip whitespace-only or single-character matches the regex can
        # produce when a digit appears mid-word.
        if not raw.strip() or len(raw.strip()) < 2:
            continue
        span = (match.start(), match.end())

        try:
            citation = parse_citation(raw)
        except CitationParseError as exc:
            items.append(
                ValidationItem(
                    raw=raw,
                    span=span,
                    status=VALIDATION_PARSE_ERROR,
                    citation=None,
                    parse_error=str(exc),
                )
            )
            continue

        node = resolve_citation(citation, source)
        if node is None:
            candidates = list(
                Node.objects.filter(
                    source=source,
                    path__startswith=citation.chapter + ".",
                ).order_by("path")[:5]
            )
            items.append(
                ValidationItem(
                    raw=raw,
                    span=span,
                    status=VALIDATION_NOT_FOUND,
                    citation=citation,
                    candidates=candidates,
                )
            )
            continue

        # Chapter-only citations: chapter Nodes have no NodeVersion. We
        # treat the chapter Node existing as ``valid`` — that's already
        # the contract from the chapter-only lookup fix.
        if citation.is_chapter_only:
            items.append(
                ValidationItem(
                    raw=raw,
                    span=span,
                    status=(
                        VALIDATION_REPEALED if node.is_repealed
                        else VALIDATION_VALID
                    ),
                    citation=citation,
                    node=node,
                )
            )
            continue

        version = current_version(node, include_pending=include_pending)
        if version is None or node.is_repealed:
            items.append(
                ValidationItem(
                    raw=raw,
                    span=span,
                    status=VALIDATION_REPEALED,
                    citation=citation,
                    node=node,
                )
            )
            continue

        items.append(
            ValidationItem(
                raw=raw,
                span=span,
                status=VALIDATION_VALID,
                citation=citation,
                node=node,
                version=version,
            )
        )

    return ValidationReport(items=items)


# Reuse the parser's iterator regex. We import it directly because
# duplicating it here would let the two patterns drift out of sync.
from apps.citations.parser import _ITER_RE  # noqa: E402


# ---------------------------------------------------------------------------
# Quote verification
# ---------------------------------------------------------------------------


# Match both straight ASCII quotes and typographic curly quotes. We require
# at least 6 characters inside so we don't trip on apostrophe-S contractions
# or single-letter scare quotes.
_QUOTE_RE = re.compile(r'[“"]([^”"]{6,}?)[”"]')

# How far before/after a quote we'll scan for a citation. 400 chars is
# roughly two paragraphs in legal writing, generous enough to catch the
# common pattern "§ X.Y provides ... 'quoted text'" but tight enough that
# unrelated cites elsewhere in the brief don't get wrongly paired.
_QUOTE_CITATION_WINDOW = 400

# Fuzzy-match threshold. Below this we mark not_found instead of fuzzy.
# 0.85 catches typical OCR-induced or paraphrase-style misquotes while
# keeping false-positive "this kinda matches" assertions low.
_QUOTE_FUZZY_THRESHOLD = 0.85


# Allowed states for QuoteCheck.status — plain strings so the dataclass
# serializes cleanly through the tool surface.
QUOTE_EXACT = "exact"
QUOTE_FUZZY = "fuzzy"
QUOTE_NOT_FOUND = "not_found"
QUOTE_NO_CITATION = "no_citation"
QUOTE_SECTION_UNRESOLVED = "section_unresolved"


@dataclass
class QuoteCheck:
    """One quoted passage from the input plus its verification status.

    ``span`` is the byte range of the quoted text (without the surrounding
    quotation marks) so a UI can highlight the misquote in the original
    document. ``closest_passage`` carries the part of the section body
    that most closely matched, for fuzzy hits and near-misses."""

    quote: str
    span: tuple[int, int]
    citation: Citation | None
    node: Node | None
    status: str
    match_score: float
    closest_passage: str


@dataclass
class QuoteReport:
    items: list[QuoteCheck]

    @property
    def total(self) -> int:
        return len(self.items)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)


def verify_quotes(
    text: str,
    *,
    citation_text: str | None = None,
    source: Source | None = None,
    include_pending: bool = False,
    fuzzy_threshold: float = _QUOTE_FUZZY_THRESHOLD,
) -> QuoteReport:
    """Find quoted passages in ``text`` and verify each against the cited
    section's body.

    If ``citation_text`` is supplied it is used as the section for every
    quote (useful for "verify this quote against § X.Y"); otherwise we
    auto-pair each quote with the nearest citation in the surrounding
    text.

    Per-quote status:

      * ``exact``   — the quote (whitespace-normalized) appears in the body.
      * ``fuzzy``   — the closest passage matches above ``fuzzy_threshold``;
                      typical for OCR drift or quietly-paraphrased quotes.
      * ``not_found`` — no passage matched.
      * ``no_citation`` — couldn't pair the quote with a citation.
      * ``section_unresolved`` — citation didn't resolve in the corpus.
    """

    if source is None:
        source = _default_source()

    if not text or not text.strip():
        return QuoteReport(items=[])

    # Resolve an explicit citation once if provided.
    explicit_citation: Citation | None = None
    explicit_node: Node | None = None
    if citation_text:
        try:
            explicit_citation = parse_citation(citation_text)
            explicit_node = resolve_citation(explicit_citation, source)
        except CitationParseError:
            explicit_citation = None
            explicit_node = None

    items: list[QuoteCheck] = []
    for match in _QUOTE_RE.finditer(text):
        quote = match.group(1).strip()
        if not quote:
            continue
        span = (match.start(1), match.end(1))

        if explicit_citation is not None:
            citation = explicit_citation
            node = explicit_node
        else:
            citation, node = _nearest_citation(text, span, source)

        if node is None:
            items.append(
                QuoteCheck(
                    quote=quote,
                    span=span,
                    citation=citation,
                    node=None,
                    status=(
                        QUOTE_SECTION_UNRESOLVED
                        if citation is not None
                        else QUOTE_NO_CITATION
                    ),
                    match_score=0.0,
                    closest_passage="",
                )
            )
            continue

        version = current_version(node, include_pending=include_pending)
        if version is None:
            items.append(
                QuoteCheck(
                    quote=quote,
                    span=span,
                    citation=citation,
                    node=node,
                    status=QUOTE_SECTION_UNRESOLVED,
                    match_score=0.0,
                    closest_passage="",
                )
            )
            continue

        status, score, passage = _match_quote_against_body(
            quote, version.body_text, fuzzy_threshold
        )
        items.append(
            QuoteCheck(
                quote=quote,
                span=span,
                citation=citation,
                node=node,
                status=status,
                match_score=score,
                closest_passage=passage,
            )
        )

    return QuoteReport(items=items)


def _nearest_citation(
    text: str, span: tuple[int, int], source: Source
) -> tuple[Citation | None, Node | None]:
    """Find the citation closest to a quote span (within
    ``_QUOTE_CITATION_WINDOW`` chars on either side). Resolves the
    citation against the corpus."""
    start, end = span
    win_start = max(0, start - _QUOTE_CITATION_WINDOW)
    win_end = min(len(text), end + _QUOTE_CITATION_WINDOW)
    window = text[win_start:win_end]

    candidates: list[tuple[int, Citation, Node | None]] = []
    for m in _ITER_RE.finditer(window):
        raw = m.group(0)
        if not raw.strip() or len(raw.strip()) < 2:
            continue
        try:
            cit = parse_citation(raw)
        except CitationParseError:
            continue
        # Convert window-relative offsets back to text-relative.
        abs_start = win_start + m.start()
        abs_end = win_start + m.end()
        # Distance: gap between citation and the quote span.
        if abs_end < start:
            distance = start - abs_end
        elif abs_start > end:
            distance = abs_start - end
        else:
            distance = 0  # citation overlaps the quote span (unusual)
        node = resolve_citation(cit, source)
        candidates.append((distance, cit, node))

    if not candidates:
        return None, None

    # Prefer the closest *resolved* candidate; if none resolve, take the
    # closest parsed one so the caller still sees the intent.
    candidates.sort(key=lambda c: (c[2] is None, c[0]))
    return candidates[0][1], candidates[0][2]


def _match_quote_against_body(
    quote: str, body: str, fuzzy_threshold: float
) -> tuple[str, float, str]:
    """Return (status, score, closest_passage). Passage is excerpted from
    the original body so the caller sees the actual statutory language."""
    import difflib

    norm_quote = _collapse_ws(quote).lower()
    norm_body = _collapse_ws(body).lower()

    if norm_quote in norm_body:
        return QUOTE_EXACT, 1.0, _excerpt_around(body, quote)

    # Split the body into roughly sentence-sized chunks and pick the one
    # closest to the quote. Iowa Code sections are short enough that this
    # O(n*m) scan is plenty fast.
    chunks = [c.strip() for c in re.split(r"(?<=[.\n])\s+", body) if c.strip()]
    if not chunks:
        return QUOTE_NOT_FOUND, 0.0, ""

    best_ratio = 0.0
    best_chunk = ""
    for chunk in chunks:
        ratio = difflib.SequenceMatcher(
            None, _collapse_ws(chunk).lower(), norm_quote, autojunk=False
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_chunk = chunk

    passage = best_chunk[:300] + ("…" if len(best_chunk) > 300 else "")
    if best_ratio >= fuzzy_threshold:
        return QUOTE_FUZZY, best_ratio, passage
    return QUOTE_NOT_FOUND, best_ratio, passage


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _excerpt_around(body: str, quote: str, context: int = 100) -> str:
    """Best-effort excerpt of the original-cased body containing the quote.
    Falls back to the quote itself if the lookup fails (e.g. internal
    whitespace differs by more than case)."""
    idx = body.lower().find(quote.lower())
    if idx < 0:
        return quote
    start = max(0, idx - context)
    end = min(len(body), idx + len(quote) + context)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return prefix + body[start:end] + suffix


# ---------------------------------------------------------------------------
# Brief audit (composite)
# ---------------------------------------------------------------------------


@dataclass
class AmendedSection:
    """A section that has been amended since some reference date.

    Used by ``audit_brief`` to flag cited sections whose text changed
    after the brief was filed — the attorney's argument may be relying
    on the prior version."""

    node: Node
    new_version: NodeVersion


@dataclass
class AuditReport:
    validation: ValidationReport
    quotes: QuoteReport
    amended_since: list[AmendedSection]
    since: dt.date | None


def audit_brief(
    text: str,
    *,
    since: dt.date | None = None,
    source: Source | None = None,
    include_pending: bool = False,
) -> AuditReport:
    """Composite review of a passage of brief text.

    Combines:

      * ``validate_citations`` — every cite's structural status.
      * ``verify_quotes`` — every "quoted span" matched against its
        cited section's actual body text.
      * Freshness check (when ``since`` is provided) — flags any cited
        section whose current text was enacted after that date, so the
        attorney can spot post-filing amendments that may undercut the
        brief's reasoning.
    """
    if source is None:
        source = _default_source()

    validation = validate_citations(
        text, source=source, include_pending=include_pending
    )
    quotes = verify_quotes(
        text, source=source, include_pending=include_pending
    )

    amended: list[AmendedSection] = []
    if since is not None:
        cited_ids = [
            item.node.id
            for item in validation.items
            if item.node is not None
        ]
        if cited_ids:
            recent = (
                NodeVersion.objects.filter(
                    node_id__in=cited_ids,
                    effective_from__gte=since,
                    effective_to__isnull=True,
                )
                .filter(_approved_filter(include_pending))
                .select_related("node", "node__source")
            )
            amended = [
                AmendedSection(node=v.node, new_version=v) for v in recent
            ]

    return AuditReport(
        validation=validation,
        quotes=quotes,
        amended_since=amended,
        since=since,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


_DEFAULT_SOURCE_CACHE: Source | None = None


def _default_source() -> Source:
    """Iowa Code source row. Cached at module level — it's seeded by
    migration so it doesn't change between requests."""
    global _DEFAULT_SOURCE_CACHE
    if _DEFAULT_SOURCE_CACHE is None:
        _DEFAULT_SOURCE_CACHE = Source.objects.select_related(
            "jurisdiction"
        ).get(jurisdiction__slug="iowa", slug="iowa-code")
    return _DEFAULT_SOURCE_CACHE


def reset_default_source_cache() -> None:
    """Tests that use TransactionTestCase nuke the seeded rows; call this
    from setUp/tearDown to drop our process-level cache."""
    global _DEFAULT_SOURCE_CACHE
    _DEFAULT_SOURCE_CACHE = None
