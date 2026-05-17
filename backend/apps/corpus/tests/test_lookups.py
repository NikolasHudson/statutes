"""Unit tests for service-layer lookup helpers that don't need a DB.

The DB-touching paths (``lookup_citation``, chapter-only resolution, etc.)
are exercised end-to-end in the MCP tool tests and the API route tests
against a real fixture, so this file just covers pure helpers."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.corpus.services.lookups import _natural_path_key


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
