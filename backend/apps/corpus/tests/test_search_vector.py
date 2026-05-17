"""Trigger-driven search_vector population.

These tests verify the Postgres-side wiring; they hit the real DB so they
need the postgres tag like the rest of the corpus tests."""

from __future__ import annotations

import datetime as dt

from django.db import connection
from django.test import TestCase, tag

from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    Source,
)


def _refresh_search_vector(version: NodeVersion) -> str:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT search_vector::text FROM corpus_nodeversion WHERE id = %s",
            [version.id],
        )
        return cur.fetchone()[0] or ""


@tag("postgres")
class SearchVectorTriggerTests(TestCase):
    def setUp(self):
        jurisdiction = Jurisdiction.objects.create(
            slug="testj", name="Testlandia", abbreviation="TL"
        )
        self.source = Source.objects.create(
            jurisdiction=jurisdiction,
            slug="test-code",
            name="Test Code",
            citation_abbreviation="T.C.",
        )
        self.section_type = NodeType.objects.create(
            source=self.source, key="section", label_singular="Section", level=1
        )

    def _make_version(self, *, heading: str, body: str) -> NodeVersion:
        node = Node.objects.create(
            source=self.source,
            node_type=self.section_type,
            ordinal="1",
            path="1.1",
            heading=heading,
        )
        return NodeVersion.objects.create(
            node=node,
            body_text=body,
            effective_from=dt.date(2026, 1, 1),
            content_hash="abc",
        )

    def test_trigger_populates_search_vector_on_insert(self):
        v = self._make_version(
            heading="Consumer fraud",
            body="A merchant who commits a deceptive practice violates this section.",
        )
        sv = _refresh_search_vector(v)
        # Tokens are stemmed by the english config: "fraud" -> "fraud",
        # "deceptive" -> "decept". Assert against stemmed forms with weight.
        self.assertIn("'fraud':2A", sv)
        self.assertIn("'decept':8B", sv)

    def test_trigger_rebuilds_when_body_text_changes(self):
        v = self._make_version(heading="Whatever", body="original text")
        original_sv = _refresh_search_vector(v)
        v.body_text = "completely different content about taxation"
        v.save(update_fields=["body_text"])
        new_sv = _refresh_search_vector(v)
        self.assertNotEqual(original_sv, new_sv)
        self.assertIn("'taxat'", new_sv)

    def test_node_heading_change_cascades_to_versions(self):
        v = self._make_version(heading="Old heading", body="body content")
        original_sv = _refresh_search_vector(v)
        self.assertIn("'old'", original_sv)

        node = v.node
        node.heading = "Replacement heading about garnishment"
        node.save(update_fields=["heading"])

        new_sv = _refresh_search_vector(v)
        self.assertNotIn("'old'", new_sv)
        self.assertIn("'garnish'", new_sv)
