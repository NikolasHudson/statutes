"""Surface wiring for Iowa Acts: citation rendering, search kind/doc_type,
session-grouped browse. Mirrors test_iac_surface.py."""

import datetime as dt
import hashlib

from django.test import TestCase

from apps.corpus.models import Node, NodeVersion, ReviewStatus, Source
from apps.api.tests._factories import make_iowa_corpus_minimal


def make_acts_minimal():
    """Session → chapter → section slice (source seeded by migration 0024)."""
    src = Source.objects.get(slug="iowa-acts")
    types = {nt.key: nt for nt in src.node_types.all()}
    session = Node.objects.create(
        source=src, node_type=types["session"], ordinal="2024", path="2024",
        heading="2024 — 90th G.A., Regular GA",
    )
    chapter = Node.objects.create(
        source=src, node_type=types["chapter"], parent=session,
        ordinal="1170", path="2024.1170",
        heading="Boards, commissions, committees, councils…",
    )
    section = Node.objects.create(
        source=src, node_type=types["section"], parent=chapter,
        ordinal="53", path="2024.1170.53", heading="2.69",
        source_metadata={"kind": "repeal", "edges": [
            {"code_ref": "2.69", "action": "repeal", "code_year": "2024"}
        ]},
    )
    body = "REPEAL.  Sections 2.69 and 3.20, Code 2024, are repealed."
    NodeVersion.objects.create(
        node=section, body_text=body, effective_from=dt.date(2024, 7, 1),
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        review_status=ReviewStatus.APPROVED,
    )
    return src, session, chapter, section


class ActsCitationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.src, cls.session, cls.chapter, cls.section = make_acts_minimal()

    def test_section_citation(self):
        from apps.corpus.services.corpus_tools import _render_citation

        self.assertEqual(
            _render_citation(self.section), "2024 Iowa Acts, ch. 1170, §53"
        )

    def test_chapter_citation(self):
        from apps.api.search_common import _citation

        self.assertEqual(_citation(self.chapter), "2024 Iowa Acts, ch. 1170")


class ActsSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_iowa_corpus_minimal()
        cls.src, _, _, cls.section = make_acts_minimal()

    def test_acts_doc_type_scopes_and_kind(self):
        resp = self.client.get(
            "/api/browse/search", {"q": "repealed", "doc_type": "acts"}
        )
        body = resp.json()
        self.assertEqual(body["scope"], "iowa-acts")
        hit = body["results"][0]
        self.assertEqual(hit["kind"], "acts")
        self.assertEqual(hit["citation"], "2024 Iowa Acts, ch. 1170, §53")


class ActsBrowseTierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_acts_minimal()

    def test_chapters_grouped_by_session(self):
        resp = self.client.get("/api/browse/sources/iowa-acts/chapters")
        body = resp.json()
        self.assertEqual(body["group_label"], "Sessions")
        self.assertEqual(len(body["agencies"]), 1)
        self.assertEqual(body["agencies"][0]["ordinal"], "2024")
        self.assertEqual(
            [c["ordinal"] for c in body["agencies"][0]["chapters"]], ["1170"]
        )


class ActsCitationParserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_acts_minimal()

    def test_resolve_endpoint_round_trips(self):
        resp = self.client.get(
            "/api/browse/resolve",
            {"source": "iowa-acts", "cite": "2024 Iowa Acts, ch. 1170, §53"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["path"], "2024.1170.53")
