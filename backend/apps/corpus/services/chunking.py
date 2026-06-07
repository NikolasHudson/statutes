"""Structure-aware chunking of NodeVersion bodies into NodeChunk rows.

Why chunk (see ``NodeChunk`` docstring): one vector per whole opinion is too
coarse and silently truncates over voyage-law-2's 16k-token cap. We cut each
opinion into passage-sized, overlapping chunks so the vector index can retrieve
the specific paragraph that states a rule.

The module is split so the algorithm stays pure and testable while the DB and
tokenizer bits are injected:

- ``chunk_body``         — pure: text + a ``count_tokens`` callable -> ordered
                           ``ChunkSpan`` slices (char offsets, no DB, no voyage).
- ``format_header`` /
  ``header_for_version``  — build the case-meta context prefix.
- ``build_chunks``       — orchestration: prepend the header, hash, and return
                           *unsaved* ``NodeChunk`` instances for one NodeVersion.
- ``voyage_token_counter`` — a cached ``count_tokens`` backed by the real
                           voyage-law-2 tokenizer (local HF tokenizer).

Chunking is per-NodeVersion, which means lead/concurrence/dissent never share a
chunk — they are already separate opinion nodes, so that boundary is free.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Callable

from apps.corpus.models import NodeChunk


log = logging.getLogger(__name__)

# Defaults. ~800 tokens (~2.9k chars at the measured 3.67 chars/token for this
# corpus) is a starting point, not gospel — chunk size is the single biggest
# retrieval-quality knob, so tune target/overlap on the eval harness before a
# full run. Overlap carries cross-boundary reasoning into the next chunk.
DEFAULT_TARGET_TOKENS = 800
DEFAULT_OVERLAP_TOKENS = 120

# A blank line is a paragraph boundary: the caselaw parser's _normalize() caps
# runs at "\n\n", so two-or-more newlines reliably separate paragraphs. The
# sentence split is a *coarse fallback*, used only to break a single paragraph
# that alone exceeds the token budget (block quotes, long string cites).
_PARA_RE = re.compile(r"\n{2,}")
_SENT_RE = re.compile(r"(?<=[.?!])\s+")

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class ChunkSpan:
    """A contiguous slice of the source body. ``text == body[char_start:char_end]``."""

    ordinal: int
    text: str
    char_start: int
    char_end: int
    token_count: int  # tokens of the raw span (the embedded token count is computed later)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _trim(body: str, start: int, end: int) -> tuple[int, int]:
    """Shrink [start, end) to drop leading/trailing whitespace so a stored span
    equals ``body[start:end]`` with no ragged edges."""
    while start < end and body[start].isspace():
        start += 1
    while end > start and body[end - 1].isspace():
        end -= 1
    return start, end


def _split_span(
    body: str, start: int, end: int, pattern: re.Pattern
) -> list[tuple[int, int]]:
    """Split ``body[start:end]`` on ``pattern``, returning trimmed (s, e) spans
    (absolute offsets into ``body``), dropping whitespace-only pieces."""
    spans: list[tuple[int, int]] = []
    pos = start
    for m in pattern.finditer(body, start, end):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < end:
        spans.append((pos, end))
    out: list[tuple[int, int]] = []
    for s, e in spans:
        s, e = _trim(body, s, e)
        if s < e:
            out.append((s, e))
    return out


def _hard_split(
    body: str, start: int, end: int, tok: int, target: int, count_tokens: TokenCounter
) -> list[tuple[int, int, int]]:
    """Last-resort even char-split of a single unit (a sentence with no usable
    boundaries) that still exceeds ``target``. Proportional by characters, which
    is approximate in tokens but bounded well under the 16k model cap."""
    n = max(1, math.ceil(tok / target))
    span = end - start
    out: list[tuple[int, int, int]] = []
    for i in range(n):
        ws = start + (span * i) // n
        we = start + (span * (i + 1)) // n
        ws, we = _trim(body, ws, we)
        if ws < we:
            out.append((ws, we, count_tokens(body[ws:we])))
    return out


def _units(
    body: str, count_tokens: TokenCounter, target: int
) -> list[tuple[int, int, int]]:
    """Break the body into contiguous packing units (start, end, tokens), each
    at most ``target`` tokens: paragraphs first, then sentences for an oversized
    paragraph, then a hard char-split for an oversized sentence."""
    units: list[tuple[int, int, int]] = []
    for ps, pe in _split_span(body, 0, len(body), _PARA_RE):
        tok = count_tokens(body[ps:pe])
        if tok <= target:
            units.append((ps, pe, tok))
            continue
        for ss, se in _split_span(body, ps, pe, _SENT_RE):
            stok = count_tokens(body[ss:se])
            if stok <= target:
                units.append((ss, se, stok))
            else:
                units.extend(_hard_split(body, ss, se, stok, target, count_tokens))
    return units


def chunk_body(
    body: str,
    *,
    count_tokens: TokenCounter,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkSpan]:
    """Pack a body into overlapping, paragraph-aligned chunks of ~``target_tokens``.

    Greedy: fill a chunk with whole units up to the budget (never splitting a
    unit), then start the next chunk a few units back so the trailing
    ~``overlap_tokens`` of one chunk re-open the next. Chunks are contiguous and
    overlapping — ``chunks[k+1].char_start <= chunks[k].char_end`` always."""
    body = body or ""
    if not body.strip():
        return []
    units = _units(body, count_tokens, target_tokens)
    if not units:
        return []

    n = len(units)
    raw: list[tuple[int, int, int]] = []  # (char_start, char_end, token_estimate)
    i = 0
    while i < n:
        # Pack forward. The ``j == i`` guard guarantees at least one unit even if
        # it alone meets/exceeds target (units are already <= target).
        j = i
        tok = 0
        while j < n and (j == i or tok + units[j][2] <= target_tokens):
            tok += units[j][2]
            j += 1
        raw.append((units[i][0], units[j - 1][1], tok))
        if j >= n:
            break
        # Step back from the last packed unit to seed overlap into the next chunk.
        ov = 0
        k = j - 1
        while k > i and ov + units[k][2] <= overlap_tokens:
            ov += units[k][2]
            k -= 1
        i = max(k + 1, i + 1)  # always make progress

    return [
        ChunkSpan(
            ordinal=ordinal,
            text=body[cs:ce],
            char_start=cs,
            char_end=ce,
            token_count=tok,
        )
        for ordinal, (cs, ce, tok) in enumerate(raw)
    ]


# ---------------------------------------------------------------------------
# Case-meta context header
# ---------------------------------------------------------------------------

def format_header(
    *, case_name: str, citation: str, court_name: str, year: str, opinion_label: str
) -> str:
    """Compose a one-line caption, e.g.
    ``State v. Smith, 987 N.W.2d 123 (Supreme Court of Iowa 2019) — Lead Opinion``.
    Each part is optional; the separators only appear when both sides exist."""
    head = (case_name or "").strip()
    citation = (citation or "").strip()
    if citation:
        head = f"{head}, {citation}" if head else citation
    paren = " ".join(p for p in ((court_name or "").strip(), (year or "").strip()) if p)
    if paren:
        head = f"{head} ({paren})" if head else f"({paren})"
    opinion_label = (opinion_label or "").strip()
    if opinion_label:
        head = f"{head} — {opinion_label}" if head else opinion_label
    return head


def header_for_version(version) -> str:
    """Derive the context header for a caselaw NodeVersion.

    Case-level facts (name, citation, court, year) live on the *decision* node's
    ``source_metadata`` — for an opinion that is ``node.parent``; for a
    head-matter version the decision node *is* the version's own node. The
    opinion's type/author is its node heading. Expects ``node`` and
    ``node__parent`` to be select_related'd (otherwise this lazily queries)."""
    node = version.node
    is_opinion = node.parent_id is not None
    decision = node.parent if is_opinion else node
    md = (getattr(decision, "source_metadata", None) or {}) if decision else {}

    citations = md.get("citations") or []
    case_name = (
        md.get("case_name")
        or md.get("case_name_short")
        or md.get("case_name_full")
        or (decision.heading if decision else "")
    )
    # Opinion node heading is e.g. "Lead Opinion (Cady, C.J.)"; a head-matter
    # version sits on the decision node, whose heading is the case name itself.
    opinion_label = node.heading if is_opinion else "Head Matter"
    return format_header(
        case_name=case_name,
        citation=citations[0] if citations else "",
        court_name=md.get("court_name") or "",
        year=(md.get("date_filed") or "")[:4],
        opinion_label=opinion_label,
    )


def build_chunks(
    version,
    *,
    count_tokens: TokenCounter,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[NodeChunk]:
    """Return *unsaved* NodeChunk rows for one NodeVersion: chunk the body, then
    prepend the case-meta header to the embedded text and hash it.

    ``token_count`` and ``content_hash`` cover the *embedded* text (header +
    body), since that is what voyage sees and bills. The header is prepended to
    every chunk, so its tokens are reserved out of the body budget — ``target``
    is the size of the embedded chunk, not the body alone."""
    header = header_for_version(version)
    header_tokens = count_tokens(f"{header}\n\n") if header else 0
    body_target = max(1, target_tokens - header_tokens)
    spans = chunk_body(
        version.body_text,
        count_tokens=count_tokens,
        target_tokens=body_target,
        overlap_tokens=overlap_tokens,
    )
    chunks: list[NodeChunk] = []
    for span in spans:
        embedded = f"{header}\n\n{span.text}".strip() if header else span.text
        chunks.append(
            NodeChunk(
                version=version,
                ordinal=span.ordinal,
                body_text=span.text,
                context_header=header,
                char_start=span.char_start,
                char_end=span.char_end,
                token_count=count_tokens(embedded),
                content_hash=_hash(embedded),
                embedding_source_hash="",
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Token counting (real voyage tokenizer, cached)
# ---------------------------------------------------------------------------

_TOKEN_COUNTER: TokenCounter | None = None


def voyage_token_counter() -> TokenCounter:
    """Cached ``count_tokens(str) -> int`` backed by the real voyage-law-2
    tokenizer (a local HuggingFace tokenizer — no embedding API call). Falls
    back to a chars/4 estimate if voyageai or the tokenizer is unavailable so
    dry runs still work offline; the estimate is rough, so prefer the real one
    for any sizing that feeds a paid run."""
    global _TOKEN_COUNTER
    if _TOKEN_COUNTER is not None:
        return _TOKEN_COUNTER
    try:
        import voyageai

        from .voyage import _configured_model

        tokenizer = voyageai.Client(
            api_key=os.environ.get("VOYAGE_API_KEY") or "no-key-needed-for-tokenize"
        ).tokenizer(_configured_model())

        def _count(text: str) -> int:
            return len(tokenizer.encode(text).ids) if text else 0

        _TOKEN_COUNTER = _count
    except Exception:  # noqa: BLE001 — degrade to an estimate, don't crash dry runs
        log.warning("voyage tokenizer unavailable; using chars/4 token estimate")
        _TOKEN_COUNTER = lambda text: max(1, len(text) // 4) if text else 0  # noqa: E731
    return _TOKEN_COUNTER
