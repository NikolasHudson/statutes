"""Name normalization shared by every resources dataset.

One function decides search quality for the business-entity dataset: the
stored ``name_normalized`` / ``agent_normalized`` columns and the incoming
query both pass through it, so they can only match if they agree. The rules:

* uppercase, drop every character that is not a letter, digit or space
  (so the source's quote-wrapped ``THE WOOD DOCTOR, L. C.`` loses its
  quotes and periods), and
  collapse runs of whitespace;
* then strip trailing entity-form tokens (``LLC``, ``INC``, ``CO`` …). The
  form is noise for matching — a searcher typing "wood doctor" should find
  "THE WOOD DOCTOR, L. C." and "Wood Doctor LLC" alike.

The awkward case the source is full of is a spaced-out form: ``L. C.``
becomes the tokens ``L C``, which must strip exactly like ``LC``. Hence the
run-of-single-letters pass below, which joins up to four trailing one-letter
tokens before testing them against the suffix set.

Stripping never returns an empty string: an entity legitimately named
``CO`` or ``LLC INC`` keeps its unstripped form rather than normalizing to
nothing (which would match everything).
"""

from __future__ import annotations

import re

# Entity-form tokens, in their joined (no-punctuation, no-space) spelling.
# "L L C" and "L. C." both reduce to a run of single letters that is joined
# before the lookup, so only the joined spellings need to be listed.
SUFFIX_TOKENS = frozenset(
    {
        "LLC",
        "LC",
        "INC",
        "INCORPORATED",
        "CORP",
        "CORPORATION",
        "CO",
        "COMPANY",
        "LTD",
        "LIMITED",
        "LLP",
        "LP",
        "PLLC",
        "PC",
        "PA",
    }
)

# Longest run of trailing single-letter tokens we will try to join. "PLLC"
# spelled out is four; nothing in SUFFIX_TOKENS is longer.
_MAX_LETTER_RUN = 4

_NOT_ALNUM_RE = re.compile(r"[^A-Z0-9]+")


def _tokens(value: str) -> list[str]:
    """Uppercase, strip punctuation, collapse whitespace, split."""
    return _NOT_ALNUM_RE.sub(" ", (value or "").upper()).split()


def _strip_suffix_tokens(tokens: list[str]) -> list[str]:
    """Drop trailing entity-form tokens, repeatedly ("FOO LTD CO" → "FOO")."""
    while tokens:
        # A spaced-out form first: the longest trailing run of single letters
        # whose concatenation is a known suffix ("L C" → "LC").
        joined_match = 0
        for n in range(min(_MAX_LETTER_RUN, len(tokens)), 1, -1):
            run = tokens[-n:]
            if all(len(t) == 1 for t in run) and "".join(run) in SUFFIX_TOKENS:
                joined_match = n
                break
        if joined_match:
            tokens = tokens[:-joined_match]
            continue
        if tokens[-1] in SUFFIX_TOKENS:
            tokens = tokens[:-1]
            continue
        break
    return tokens


def normalize_name(value: str) -> str:
    """Normalize an entity or agent name for storage and for querying."""
    tokens = _tokens(value)
    if not tokens:
        return ""
    stripped = _strip_suffix_tokens(list(tokens))
    # An entity actually named "LLC" keeps its name; normalizing it away would
    # leave a row that matches every query and no row that matches its own.
    return " ".join(stripped or tokens)
