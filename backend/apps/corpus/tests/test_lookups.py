"""Unit tests for service-layer lookup helpers that don't need a DB.

The DB-touching paths (``lookup_citation``, chapter-only resolution, etc.)
are exercised end-to-end in the MCP tool tests and the API route tests
against a real fixture, so this file just covers pure helpers."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.corpus.services.lookups import _QUOTE_MIN_LEN, _QUOTE_RE, _natural_path_key


def _captured_quotes(text: str) -> list[str]:
    """Quoted spans the way ``verify_quotes`` consumes them: pair via
    ``_QUOTE_RE``, then drop sub-minimum fragments in post-processing."""
    out = []
    for m in _QUOTE_RE.finditer(text):
        grp = 1 if m.group(1) is not None else 2
        q = m.group(grp).strip()
        if len(q) >= _QUOTE_MIN_LEN:
            out.append(q)
    return out


class QuotePairingTests(SimpleTestCase):
    """A short quoted term (below the length floor) must NOT desync the
    pairing of the quotes around it. The length floor lives in
    post-processing, not in the regex, precisely so a 5-char term like
    "costs" is consumed as its own (discarded) match instead of binding its
    closing delimiter to the next quote's opener — which used to capture all
    the intervening analytical prose as phantom 'unverified quotations'."""

    def test_short_term_between_real_quotes_does_not_desync(self):
        text = (
            'The statute authorizes "reasonable attorney\'s fees." '
            'Because the chapter governs "costs" and nothing more, '
            'the court held "the plaintiff cannot recover post-offer fees."'
        )
        quotes = _captured_quotes(text)
        # The two real quotations survive; the prose between them is never
        # captured, and the sub-floor term "costs" is dropped.
        self.assertIn("reasonable attorney's fees.", quotes)
        self.assertIn("the plaintiff cannot recover post-offer fees.", quotes)
        self.assertNotIn("costs", quotes)
        for q in quotes:
            self.assertFalse(
                q.startswith("Because") or q.endswith("governs"),
                f"phantom prose captured as a quote: {q!r}",
            )

    def test_straight_quote_keeps_internal_curly_term_intact(self):
        # The two-branch design: a straight-quoted passage with an internal
        # curly-quoted term is ONE quote, not split at the inner term.
        text = 'Section 714.16 defines "an “advertisement” that misleads" broadly.'
        quotes = _captured_quotes(text)
        self.assertIn("an “advertisement” that misleads", quotes)


class _FakeNode:
    """Minimal stand-in for ``Node`` so we don't need a DB row."""

    def __init__(self, path: str):
        self.path = path


class NaturalPathKeyTests(SimpleTestCase):
    """Sections in the same chapter must sort by numeric chunks, not
    lexicographically. Naive ordering puts ``714H.10`` before ``714H.2``
    which is wrong for a TOC."""

    def test_sections_within_chapter_order_numerically(self):
        nodes = [_FakeNode(p) for p in ["714H.10", "714H.2", "714H.1", "714H.20"]]
        ordered = sorted(nodes, key=_natural_path_key)
        self.assertEqual(
            [n.path for n in ordered], ["714H.1", "714H.2", "714H.10", "714H.20"]
        )

    def test_chapters_with_letter_suffix_stay_grouped(self):
        nodes = [_FakeNode(p) for p in ["714.1", "714H.1", "714.2", "714H.2"]]
        ordered = sorted(nodes, key=_natural_path_key)
        # Chapter "714" sorts before "714H" because the numeric run "714"
        # matches first and then "" < "H" lexicographically.
        self.assertEqual(
            [n.path for n in ordered], ["714.1", "714.2", "714H.1", "714H.2"]
        )
