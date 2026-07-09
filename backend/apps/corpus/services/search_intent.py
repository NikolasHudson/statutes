"""Query-intent classification for the research search surface.

Attorneys type three different contracts into one box:

* **citation** — ``714.16`` / ``998 N.W.2d 646``: they want *that document*.
* **boolean** — terms-and-connectors (``waiver AND "mechanic's lien"``): they
  want a deterministic, exhaustive, auditable match set. Vector search cannot
  honor that contract, so boolean routes to pure keyword retrieval.
* **natural** — everything else: best results, ranked (hybrid + rerank).

This module is pure (no DB, no Django imports) so the routing rules are
unit-testable as a table. Citation detection here is *shape only* — the
endpoint does the authoritative resolution and downgrades an unresolvable
citation-shaped query back to keyword search.

Connectors we detect but do not yet execute (``/s``, ``/p``, ``w/n``) are
compiled as AND and reported in ``QueryIntent.unsupported`` so the UI can say
so explicitly — a wrong-but-confident result set is the trust-killer for
exactly the users who type connectors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MODE_CITATION = "citation"
MODE_BOOLEAN = "boolean"
MODE_NATURAL = "natural"

# tsquery compiler targets. Whitelisted function names — interpolated into SQL
# by fts_search_paged, so they must never come from user input.
FUNC_WEBSEARCH = "websearch_to_tsquery"
FUNC_TSQUERY = "to_tsquery"


@dataclass(frozen=True)
class QueryIntent:
    mode: str  # MODE_*
    mode_source: str  # "auto" | "user"
    raw: str
    phrases: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    unsupported: list[dict] = field(default_factory=list)
    tsquery: str | None = None  # boolean mode only
    tsquery_func: str | None = None  # FUNC_* (boolean mode only)

    def detection_payload(self) -> dict:
        """The additive ``detection`` object the API returns to the UI."""
        return {
            "operators": self.operators,
            "phrases": self.phrases,
            "unsupported": self.unsupported,
        }


# --------------------------------------------------------------------- shapes

# Statute/rule-shaped cite: "714.16", "714", "32:1.10", "Chapter 714H",
# optionally with a leading section sign. Whole-query match only — an embedded
# cite stays in natural mode (the citation retriever still pins it).
_STATUTE_CITE_RE = re.compile(
    r"^\s*(?:§\s*)?(?:chapter\s+)?\d{1,4}[A-Z]{0,2}(?:[.:][\dA-Za-z.\-]+)?\s*$",
    re.IGNORECASE,
)

# Reporter cite ("998 N.W.2d 646") — same shape as the browse resolver.
_REPORTER_CITE_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s+(\d+[A-Za-z]?)\s*$")


def looks_like_citation(q: str) -> bool:
    """Shape-only check: is the ENTIRE query a statute or reporter citation?

    A reporter-shaped match additionally requires a reporter-ish middle run
    (letters + periods), otherwise "2019 tax 100"-style queries false-match.
    """
    if _STATUTE_CITE_RE.match(q):
        return True
    m = _REPORTER_CITE_RE.match(q)
    if m and re.fullmatch(r"[A-Za-z][\w.&\- ]*\.?", m.group(2).strip()):
        # Middle run must start with a letter and look like an abbreviation
        # (e.g. "N.W.2d", "Iowa", "F. Supp."), not arbitrary words+digits.
        return bool(re.search(r"[A-Za-z]", m.group(2)))
    return False


# ------------------------------------------------------------ boolean triggers

_UPPER_OP_RE = re.compile(r"\b(AND|OR|NOT)\b")
_AMP_PIPE_RE = re.compile(r"\s(&|\|)\s")
_PROX_RE = re.compile(r"(?:(?<=\s)|^)(/[sp]|w/\d{1,3}|/\d{1,3})(?=\s|$)", re.IGNORECASE)
_ROOT_RE = re.compile(r"\b([A-Za-z]{3,})!(?=\s|$|\))")
_PHRASE_RE = re.compile(r'"([^"]+)"')
_ONLY_PHRASES_RE = re.compile(r'^\s*(?:"[^"]*"\s*)+$')

_UNSUPPORTED_MESSAGES = {
    "/s": "The /s (same sentence) connector isn't supported yet — treated as AND.",
    "/p": "The /p (same paragraph) connector isn't supported yet — treated as AND.",
}


def _unsupported_entry(token: str) -> dict:
    lowered = token.lower()
    message = _UNSUPPORTED_MESSAGES.get(
        lowered,
        f"The {lowered} proximity connector isn't supported yet — treated as AND.",
    )
    return {"token": lowered, "treated_as": "AND", "message": message}


def _boolean_triggers(q: str) -> list[str]:
    """Return the operator tokens that make this a terms-and-connectors query,
    in order of appearance (empty list = natural)."""
    ops: list[str] = []
    # A fully-uppercase query is shouting, not connectors ("SLAYER RULE CASES").
    letters = [c for c in q if c.isalpha()]
    all_caps = bool(letters) and all(c.isupper() for c in letters)
    if not all_caps:
        ops.extend(m.group(1) for m in _UPPER_OP_RE.finditer(q))
    ops.extend(m.group(1) for m in _AMP_PIPE_RE.finditer(q))
    ops.extend(m.group(1).lower() for m in _PROX_RE.finditer(q))
    ops.extend(f"{m.group(1)}!" for m in _ROOT_RE.finditer(q))
    return ops


# ------------------------------------------------------------------- compiler


def _lexeme(word: str) -> str:
    """Strip a raw token down to what to_tsquery can safely take unquoted."""
    return re.sub(r"[^\w]", "", word, flags=re.UNICODE)


_TOKEN_RE = re.compile(
    r"""
    "(?P<phrase>[^"]*)"
    | (?P<lparen>\()
    | (?P<rparen>\))
    | (?P<word>[^\s()"]+)
    """,
    re.VERBOSE,
)


def compile_boolean_tsquery(q: str) -> tuple[str, str, list[dict]]:
    """Compile a terms-and-connectors query.

    Returns ``(query_text, tsquery_func, unsupported)`` where ``query_text``
    is the argument for ``tsquery_func('english', %s)``.

    Simple queries (AND/OR/NOT/phrases/exclusions only) stay on
    ``websearch_to_tsquery``, which never raises on odd input. Grouping
    parens, root expanders (``negligen!``) and explicit ``&``/``|`` need
    ``to_tsquery`` syntax, which we assemble token-by-token with implicit
    AND between adjacent operands. Proximity connectors compile to AND and
    are reported in ``unsupported``.
    """
    unsupported = [_unsupported_entry(t) for t in dict.fromkeys(
        m.group(1).lower() for m in _PROX_RE.finditer(q)
    )]

    needs_tsquery = bool(
        "(" in q or ")" in q or _ROOT_RE.search(q) or _AMP_PIPE_RE.search(q)
        or _PROX_RE.search(q)
    )
    if not needs_tsquery:
        # websearch understands "phrases", -foo and or; map the UPPERCASE
        # operators onto that (same mapping the public browse endpoint uses).
        text = _PHRASE_RE.sub(lambda m: '"%s"' % m.group(1), q)
        text = re.sub(r"\bNOT\s+", "-", text)
        text = re.sub(r"\bAND\b", " ", text)
        text = re.sub(r"\bOR\b", " or ", text)
        return " ".join(text.split()), FUNC_WEBSEARCH, unsupported

    out: list[str] = []
    pending_not = False

    def emit_operand(operand: str) -> None:
        nonlocal pending_not
        # Implicit AND between adjacent operands ("dog (bite | attack)").
        if out and out[-1] not in {"&", "|", "!", "("}:
            out.append("&")
        if pending_not:
            out.append("!")
            pending_not = False
        out.append(operand)

    for m in _TOKEN_RE.finditer(q):
        if m.group("phrase") is not None:
            words = [w for w in (_lexeme(x) for x in m.group("phrase").split()) if w]
            if not words:
                continue
            emit_operand("(%s)" % "<->".join(words) if len(words) > 1 else words[0])
        elif m.group("lparen"):
            if out and out[-1] not in {"&", "|", "!", "("}:
                out.append("&")
            if pending_not:
                out.append("!")
                pending_not = False
            out.append("(")
        elif m.group("rparen"):
            # Drop a dangling operator before the close ("(a AND)").
            while out and out[-1] in {"&", "|", "!"}:
                out.pop()
            if out and out[-1] == "(":  # empty group — drop it entirely
                out.pop()
            elif out:
                out.append(")")
        else:
            word = m.group("word")
            upper = word.upper()
            if upper == "AND" or word == "&":
                if out and out[-1] not in {"&", "|", "!", "("}:
                    out.append("&")
            elif upper == "OR" or word == "|":
                if out and out[-1] not in {"&", "|", "!", "("}:
                    out.append("|")
            elif upper == "NOT":
                pending_not = True
            elif _PROX_RE.fullmatch(word):
                if out and out[-1] not in {"&", "|", "!", "("}:
                    out.append("&")
            elif root := _ROOT_RE.fullmatch(word):
                emit_operand(f"{_lexeme(root.group(1))}:*")
            else:
                lex = _lexeme(word)
                if lex:
                    emit_operand(lex)

    # Trim trailing operators; balance any unclosed groups.
    while out and out[-1] in {"&", "|", "!", "("}:
        out.pop()
    depth = 0
    for tok in out:
        depth += tok == "("
        depth -= tok == ")"
    out.extend(")" * depth)

    return " ".join(out), FUNC_TSQUERY, unsupported


# ------------------------------------------------------------------ classifier


def classify_query(
    q: str,
    *,
    mode_override: str | None = None,
    citation_ok: bool = True,
) -> QueryIntent:
    """Classify a search-box query. ``mode_override`` ("boolean"|"natural")
    forces the mode (``mode_source="user"``) while still reporting detected
    operators/phrases. ``citation_ok=False`` skips the citation shape check —
    the endpoint uses it to re-classify after a citation fails to resolve."""
    q = " ".join((q or "").split())
    phrases = [p.strip() for p in _PHRASE_RE.findall(q) if p.strip()]

    if mode_override in (MODE_BOOLEAN, MODE_NATURAL):
        operators = _boolean_triggers(q)
        if mode_override == MODE_BOOLEAN:
            tsquery, func, unsupported = compile_boolean_tsquery(q)
            return QueryIntent(
                mode=MODE_BOOLEAN, mode_source="user", raw=q, phrases=phrases,
                operators=operators, unsupported=unsupported,
                tsquery=tsquery, tsquery_func=func,
            )
        return QueryIntent(
            mode=MODE_NATURAL, mode_source="user", raw=q,
            phrases=phrases, operators=operators,
        )

    if citation_ok and looks_like_citation(q):
        return QueryIntent(mode=MODE_CITATION, mode_source="auto", raw=q)

    operators = _boolean_triggers(q)
    only_phrases = bool(phrases) and bool(_ONLY_PHRASES_RE.match(q))
    if operators or only_phrases:
        tsquery, func, unsupported = compile_boolean_tsquery(q)
        return QueryIntent(
            mode=MODE_BOOLEAN, mode_source="auto", raw=q, phrases=phrases,
            operators=operators or (["exact-phrase"] if only_phrases else []),
            unsupported=unsupported, tsquery=tsquery, tsquery_func=func,
        )

    return QueryIntent(
        mode=MODE_NATURAL, mode_source="auto", raw=q, phrases=phrases,
    )
