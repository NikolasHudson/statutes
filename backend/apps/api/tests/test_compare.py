"""Edition comparison: the compare service and its public browse endpoints.

Builds a tiny multi-edition corpus directly (no ingest pipeline) covering the
four diff outcomes — amended, added, repealed, unchanged — then exercises both
``compare_editions``/``section_diff`` and the HTTP surface.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from django.core.cache import cache
from django.test import Client, TestCase, tag

from apps.corpus.models import Edition, Node, NodeVersion, ReviewStatus
from apps.corpus.services.editions import (
    compare_editions,
    diff_segments,
    section_diff,
)

from ._factories import make_iowa_corpus_minimal

D2025 = dt.date(2025, 1, 1)
D2026 = dt.date(2026, 4, 30)


def _section_type(src):
    return src.node_types.get(key="section")


def _ver(node, body, eff_from, eff_to=None):
    return NodeVersion.objects.create(
        node=node,
        body_text=body,
        effective_from=eff_from,
        effective_to=eff_to,
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        review_status=ReviewStatus.APPROVED,
    )


@tag("postgres")
class CompareEditionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        src, sec_amended, v_old = make_iowa_corpus_minimal()
        cls.src = src
        cls.chapter = sec_amended.parent

        # 714.16 already has a 2025 version from the factory; close it and add
        # a changed 2026 version -> amended.
        v_old.effective_to = D2026
        v_old.save(update_fields=["effective_to"])
        _ver(sec_amended, "Consumer fraud is strictly prohibited.", D2026)
        cls.amended = sec_amended

        sec_t = _section_type(src)
        # added: only exists from 2026.
        cls.added = Node.objects.create(
            source=src, node_type=sec_t, parent=cls.chapter,
            ordinal="50", path="714.50", heading="New offense",
        )
        _ver(cls.added, "A new prohibition.", D2026)

        # repealed: existed in 2025, gone by 2026.
        cls.repealed = Node.objects.create(
            source=src, node_type=sec_t, parent=cls.chapter,
            ordinal="99", path="714.99", heading="Old offense", is_repealed=True,
        )
        _ver(cls.repealed, "An old prohibition.", D2025, D2026)

        # unchanged: one open version spanning both editions.
        cls.unchanged = Node.objects.create(
            source=src, node_type=sec_t, parent=cls.chapter,
            ordinal="1", path="714.1", heading="Definitions",
        )
        _ver(cls.unchanged, "Definitions apply.", D2025)

        # A second chapter with NO prior-edition data loaded (only a 2026
        # version) — it must not pollute the "added" bucket.
        chap800 = Node.objects.create(
            source=src, node_type=src.node_types.get(key="chapter"),
            ordinal="800", path="800", heading="Uncovered chapter",
        )
        cls.uncovered = Node.objects.create(
            source=src, node_type=sec_t, parent=chap800,
            ordinal="1", path="800.1", heading="Only in 2026",
        )
        _ver(cls.uncovered, "Exists only in 2026.", D2026)

        Edition.objects.create(source=src, year=2025, label="Iowa Code 2025", as_of_date=D2025)
        Edition.objects.create(source=src, year=2026, label="Iowa Code 2026", as_of_date=D2026)

    def setUp(self):
        cache.clear()
        self.client = Client()

    def test_summary_classifies_each_outcome(self):
        s = compare_editions(self.src, 2025, 2026)
        self.assertEqual(s.counts, {"added": 1, "amended": 1, "repealed": 1, "unchanged": 1})
        self.assertEqual([r.path for r in s.amended], ["714.16"])
        self.assertEqual([r.path for r in s.added], ["714.50"])
        self.assertEqual([r.path for r in s.repealed], ["714.99"])

    def test_uncovered_chapter_is_not_reported_as_added(self):
        s = compare_editions(self.src, 2025, 2026)
        self.assertEqual(s.covered_chapters, 1)
        added_paths = [r.path for r in s.added]
        self.assertNotIn("800.1", added_paths, "unloaded chapter polluted 'added'")
        self.assertEqual(added_paths, ["714.50"])

    def test_section_diff_has_from_to_and_inserted_word(self):
        d = section_diff(self.amended, 2025, 2026)
        self.assertTrue(d["changed"])
        self.assertTrue(d["from"]["present"])
        self.assertTrue(d["to"]["present"])
        inserts = [seg["text"] for seg in d["diff"] if seg["op"] == "insert"]
        self.assertTrue(any("strictly" in t for t in inserts))

    def test_diff_segments_basic(self):
        segs = diff_segments("a b c", "a B c")
        ops = [s["op"] for s in segs]
        self.assertIn("delete", ops)
        self.assertIn("insert", ops)
        # Reassembling equal+insert reproduces the "to" text.
        to_text = "".join(s["text"] for s in segs if s["op"] in ("equal", "insert"))
        self.assertEqual(to_text, "a B c")

    def test_editions_endpoint_lists_and_defaults(self):
        body = self.client.get("/api/browse/editions", {"source": "iowa-code"}).json()
        self.assertEqual([e["year"] for e in body["editions"]], [2026, 2025])
        self.assertEqual(body["default"], {"from_year": 2025, "to_year": 2026})

    def test_compare_endpoint_returns_buckets(self):
        body = self.client.get(
            "/api/browse/compare",
            {"source": "iowa-code", "from_year": 2025, "to_year": 2026},
        ).json()
        self.assertEqual(body["counts"]["amended"], 1)
        self.assertEqual(body["amended"][0]["path"], "714.16")
        self.assertEqual(body["amended"][0]["chapter"], "714")

    def test_compare_section_endpoint(self):
        body = self.client.get(
            "/api/browse/compare/section",
            {"node_id": self.amended.id, "from_year": 2025, "to_year": 2026},
        ).json()
        self.assertEqual(body["path"], "714.16")
        self.assertTrue(body["changed"])
        self.assertIn("strictly", body["to"]["body_text"])

    def test_unknown_edition_does_not_500(self):
        resp = self.client.get(
            "/api/browse/compare",
            {"source": "iowa-code", "from_year": 1999, "to_year": 2026},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("error"), "unknown edition")
