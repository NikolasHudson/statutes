"""Tests for citation_links — the inline cross-reference primitive that
backs both the reader's clickable citations and the CrossReference
backfill command.

The contract that matters: only link a citation we're *sure* about
(don't turn every bare number in statutory prose into a link), never
link a dead target, and never link a section to itself.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from django.test import TestCase

from apps.api.tests._factories import make_iowa_corpus_minimal
from apps.corpus.models import Node, NodeType, NodeVersion, ReviewStatus
from apps.corpus.services.lookups import (
    citation_links,
    reset_default_source_cache,
)


def _section(source, chapter, section_t, ordinal, path, heading, *, body, repealed=False):
    node = Node.objects.create(
        source=source,
        node_type=section_t,
        parent=chapter,
        ordinal=ordinal,
        path=path,
        heading=heading,
        is_repealed=repealed,
    )
    NodeVersion.objects.create(
        node=node,
        body_text=body,
        effective_from=dt.date(2025, 1, 1),
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        review_status=ReviewStatus.APPROVED,
    )
    return node


class CitationLinksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Factory gives us source, chapter 714, section 714.16 (+ version).
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()
        cls.chapter = cls.section.parent
        cls.section_t = NodeType.objects.get(source=cls.source, key="section")
        cls.chapter_t = NodeType.objects.get(source=cls.source, key="chapter")

        cls.s8 = _section(
            cls.source, cls.chapter, cls.section_t,
            "8", "714.8", "Theft defined", body="Theft is the taking of...",
        )
        cls.s99 = _section(
            cls.source, cls.chapter, cls.section_t,
            "99", "714.99", "Old provision", body="Superseded text.",
            repealed=True,
        )
        # Chapter nodes carry no version — that's legitimate, not "dead".
        cls.ch232 = Node.objects.create(
            source=cls.source, node_type=cls.chapter_t,
            ordinal="232", path="232", heading="Juvenile justice",
        )
        cls.ch30 = Node.objects.create(
            source=cls.source, node_type=cls.chapter_t,
            ordinal="30", path="30", heading="Liens",
        )
        # Series-citation targets.
        for ordinal in ("497", "498", "499", "501", "501A", "9H", "9I"):
            Node.objects.create(
                source=cls.source, node_type=cls.chapter_t,
                ordinal=ordinal, path=ordinal, heading=f"Chapter {ordinal}",
            )
        cls.s41 = _section(
            cls.source, cls.chapter, cls.section_t,
            "1", "714.1", "First", body="...",
        )
        cls.s42 = _section(
            cls.source, cls.chapter, cls.section_t,
            "2", "714.2", "Second", body="...",
        )

    def setUp(self):
        reset_default_source_cache()

    def _paths(self, body, exclude=None):
        links = citation_links(
            body, source=self.source, exclude_node_id=exclude
        )
        return {link.target_path for link in links}

    def test_links_section_reference(self):
        paths = self._paths("A person who violates section 714.8 is guilty.")
        self.assertEqual(paths, {"714.8"})

    def test_dotted_reference_links_without_a_sigil(self):
        # "714.8" is section-shaped (has the separator) → confident.
        self.assertEqual(self._paths("see 714.8 generally"), {"714.8"})

    def test_chapter_reference_needs_a_sigil(self):
        # Bare "30" in prose is not a citation; "chapter 232" is.
        paths = self._paths(
            "Penalty of not more than 30 dollars. As used in chapter 232."
        )
        self.assertEqual(paths, {"232"})

    def test_repealed_target_is_not_linked(self):
        self.assertEqual(self._paths("See section 714.99 for prior law."), set())

    def test_self_reference_is_excluded(self):
        paths = self._paths(
            "Nothing in section 714.16 limits section 714.8.",
            exclude=self.section.id,
        )
        self.assertEqual(paths, {"714.8"})

    def test_unresolvable_citation_is_dropped(self):
        self.assertEqual(self._paths("compare section 714.404 (does not exist)"), set())

    def test_raw_substring_is_preserved_for_frontend_matching(self):
        links = citation_links(
            "violates section 714.8 today", source=self.source
        )
        self.assertEqual(len(links), 1)
        # The reader matches on this exact phrase, so it must be the
        # substring as it appeared, not a normalized render.
        self.assertEqual(links[0].raw, "section 714.8")
        self.assertEqual(links[0].target_node_id, self.s8.id)

    def test_series_chapter_list_links_every_member(self):
        body = (
            "an association of persons organized under chapter 497, 498, "
            "or 499; or a cooperative organized under chapter 501 or 501A."
        )
        self.assertEqual(
            self._paths(body),
            {"497", "498", "499", "501", "501A"},
        )

    def test_series_handles_letter_suffixed_chapters(self):
        self.assertEqual(
            self._paths("including but not limited to chapters 9H and 9I."),
            {"9H", "9I"},
        )

    def test_series_section_list_links_dotted_members(self):
        self.assertEqual(
            self._paths("as provided in sections 714.1, 714.2 and 714.16."),
            {"714.1", "714.2", "714.16"},
        )

    def test_series_does_not_link_ranges(self):
        # "through" is not an enumeration — expanding "497 through 499"
        # would have to invent 498. We link the lone sigil-led endpoint
        # (Pass 1) and nothing else; the range members stay plain text.
        paths = self._paths("organized under chapter 497 through 499")
        self.assertEqual(paths, {"497"})
        self.assertNotIn("498", paths)
        self.assertNotIn("499", paths)

    def test_resolution_is_batched_constant_query_count(self):
        body = (
            "section 714.8 and chapter 232 and section 714.8 again and "
            "chapter 232 once more and section 714.99."
        )
        # Two queries total regardless of citation count: one to resolve
        # the distinct paths, one for the live-version check.
        with self.assertNumQueries(2):
            citation_links(body, source=self.source)
