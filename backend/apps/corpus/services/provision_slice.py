"""Narrow a section's body text to the specific subsection a citation names.

Citations resolve only to the section Node (see ``citations.resolver``), so a
cite like ``§ 714H.5(4)`` grounds against the *entire* body of § 714H.5 —
every subsection (1) through (6). That blunt grounding is what lets a claim
about subsection (4) get matched against text from subsection (2), and lets the
same provision pick up inconsistent verdicts across a document.

This module slices the section body down to the cited subsection using the
Iowa Code's fixed outline convention. The hierarchy alternates number/letter
and switches delimiter style with depth:

    depth 1  subsection      "1."   "2."     number + dot
    depth 2  paragraph       "a."   "b."     lower-letter + dot
    depth 3  subparagraph    "(1)"  "(2)"    parenthesized number
    depth 4  subsubparagraph "(a)"  "(b)"    parenthesized lower-letter

Searching by *depth* (not by "first marker that matches the token") is what
keeps a ``(2)`` subparagraph nested inside subsection 1 from being mistaken for
subsection ``2.`` when resolving ``714.16(2)``.

The contract is deliberately conservative: ``slice_provision`` returns the
narrowed block only when every token resolves unambiguously, and ``None``
otherwise. Callers fall back to the full section body on ``None``, so a miss
degrades to today's behavior — never worse.
"""

from __future__ import annotations

import re

# Leading indent before a marker: spaces, tabs, and the non-breaking spaces the
# corpus uses for indentation ("\xa0\xa0(1)\xa0\xa0...").
_INDENT = r"[ \t\xa0]*"
# Whitespace that must follow a dotted marker (so "1.303" can't pose as "1.").
_WS = r"[ \t\xa0]"

_DOTTED_NUM = "dotted_num"
_DOTTED_ALPHA = "dotted_alpha"
_PAREN_NUM = "paren_num"
_PAREN_ALPHA = "paren_alpha"

# Iowa Code outline style at each citation depth. Depths beyond 4 are
# unsupported (return None → caller falls back to the full body).
_STYLE_BY_DEPTH = {
    1: _DOTTED_NUM,
    2: _DOTTED_ALPHA,
    3: _PAREN_NUM,
    4: _PAREN_ALPHA,
}

# Matches any marker at a given level, used to find where a block ends.
_SIBLING_RE = {
    _DOTTED_NUM: re.compile(rf"^{_INDENT}\d+\.(?={_WS})", re.MULTILINE),
    _DOTTED_ALPHA: re.compile(rf"^{_INDENT}[a-z]{{1,2}}\.(?={_WS})", re.MULTILINE),
    _PAREN_NUM: re.compile(rf"^{_INDENT}\(\d+\)", re.MULTILINE),
    _PAREN_ALPHA: re.compile(rf"^{_INDENT}\([a-z]{{1,2}}\)", re.MULTILINE),
}

# A token must look like its depth's style or the convention doesn't hold here.
_TOKEN_OK = {
    _DOTTED_NUM: re.compile(r"\d+$"),
    _DOTTED_ALPHA: re.compile(r"[A-Za-z]{1,2}$"),
    _PAREN_NUM: re.compile(r"\d+$"),
    _PAREN_ALPHA: re.compile(r"[A-Za-z]{1,2}$"),
}


def _marker_re(style: str, token: str) -> re.Pattern[str]:
    tok = re.escape(token)
    if style in (_DOTTED_NUM, _DOTTED_ALPHA):
        return re.compile(rf"^{_INDENT}{tok}\.(?={_WS})", re.MULTILINE | re.IGNORECASE)
    return re.compile(rf"^{_INDENT}\({tok}\)", re.MULTILINE | re.IGNORECASE)


def _slice_one(scope: str, style: str, token: str) -> str | None:
    """Return the block for ``token`` within ``scope``, or None if not found.

    The block runs from the token's marker to the next sibling marker of the
    same style (or the end of the scope). Children of the block are at a
    *different* style, so they never terminate it prematurely.
    """
    if not _TOKEN_OK[style].match(token):
        return None
    start_m = _marker_re(style, token).search(scope)
    if start_m is None:
        return None
    start = start_m.start()
    end = len(scope)
    for sib in _SIBLING_RE[style].finditer(scope, start_m.end()):
        end = sib.start()
        break
    return scope[start:end]


def slice_provision(body_text: str, subdivisions: tuple[str, ...]) -> str | None:
    """Narrow ``body_text`` to the subsection named by ``subdivisions``.

    ``subdivisions`` is the citation's subdivision tuple, outermost first —
    e.g. ``("2", "a", "1")`` for ``714.16(2)(a)(1)``. Returns the sliced block,
    or ``None`` if the body isn't enumerated, a token can't be located, the
    citation nests deeper than the known outline, or a token's type doesn't
    match its depth (a sign the convention doesn't hold here). Callers should
    fall back to the full ``body_text`` on ``None``.
    """
    if not subdivisions or not body_text:
        return None
    scope = body_text
    for depth, token in enumerate(subdivisions, start=1):
        style = _STYLE_BY_DEPTH.get(depth)
        if style is None:
            return None
        block = _slice_one(scope, style, token)
        if block is None:
            return None
        scope = block
    sliced = scope.strip()
    return sliced or None
