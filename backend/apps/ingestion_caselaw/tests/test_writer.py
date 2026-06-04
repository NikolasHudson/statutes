"""Writer tests against the corpus tables (uses the seeded iowa-caselaw source).

Covers: 2-level node tree, auto-APPROVED versions, effective_from = date_filed,
heading-before-version (FTS trigger), conditional head-matter version, empty-body
container, idempotent re-run, and amend (close-and-recreate).
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase

from apps.corpus.models import Node, NodeVersion, ReviewStatus

from ..parser import parse_decision, parse_opinion
from ..writer import (
    get_iowa_caselaw_source,
    get_node_types,
    load_open_version_hashes,
    write_decisions_batch,
    write_opinions_batch,
)
from .test_parser import _dec_record, _op_record


class WriterTests(TestCase):
    def setUp(self):
        self.source = get_iowa_caselaw_source()
        self.types = get_node_types(self.source)

    def _ingest(self, dec_records, op_records, open_hashes=None):
        if open_hashes is None:
            open_hashes = load_open_version_hashes(self.source)
        decisions = [parse_decision(r, citations=("987 N.W.2d 123",)) for r in dec_records]
        dcounts, cache = write_decisions_batch(decisions, self.source, self.types, open_hashes)
        opinions = [parse_opinion(r) for r in op_records]
        ocounts = write_opinions_batch(opinions, self.source, self.types, cache, open_hashes)
        return dcounts, ocounts

    def test_writes_two_level_tree_and_versions(self):
        dcounts, ocounts = self._ingest(
            [_dec_record(syllabus="The syllabus.")],
            [
                _op_record(cl_opinion_id=9000, node_path="cl-cluster-1000/op-9000",
                           type="020lead", plain_text="Lead body."),
                _op_record(cl_opinion_id=9001, node_path="cl-cluster-1000/op-9001",
                           type="040dissent", author_str="Appel", plain_text="Dissent body."),
                _op_record(cl_opinion_id=9002, node_path="cl-cluster-1000/op-9002",
                           type="030concurrence"),  # empty body -> container only
            ],
        )

        decision = Node.objects.get(source=self.source, path="cl-cluster-1000")
        self.assertEqual(decision.node_type.key, "decision")
        self.assertIsNone(decision.parent_id)
        self.assertEqual(decision.heading, "State v. Smith")
        self.assertEqual(decision.source_metadata["court_id"], "iowa")

        # Head-matter version on the decision node.
        head = NodeVersion.objects.get(node=decision)
        self.assertEqual(head.review_status, ReviewStatus.APPROVED)
        self.assertEqual(head.effective_from, dt.date(2020, 5, 1))
        self.assertIsNone(head.effective_to)
        self.assertIn("Syllabus", head.body_text)

        # Opinion child nodes.
        op_nodes = {n.path: n for n in Node.objects.filter(parent=decision)}
        self.assertEqual(set(op_nodes), {
            "cl-cluster-1000/op-9000", "cl-cluster-1000/op-9001", "cl-cluster-1000/op-9002",
        })
        self.assertEqual(op_nodes["cl-cluster-1000/op-9000"].heading, "Lead Opinion (Mansfield)")
        self.assertEqual(op_nodes["cl-cluster-1000/op-9001"].heading, "Dissent (Appel)")

        # Versions: lead + dissent have one; the empty concurrence has none.
        self.assertTrue(NodeVersion.objects.filter(
            node__path="cl-cluster-1000/op-9000", review_status=ReviewStatus.APPROVED).exists())
        self.assertEqual(NodeVersion.objects.filter(
            node__path="cl-cluster-1000/op-9002").count(), 0)

        self.assertEqual(dcounts["decisions_created"], 1)
        self.assertEqual(dcounts["head_added"], 1)
        self.assertEqual(ocounts["opinions_created"], 3)
        self.assertEqual(ocounts["op_added"], 2)
        self.assertEqual(ocounts["empty_body"], 1)

    def test_search_vector_populated_by_trigger(self):
        self._ingest(
            [_dec_record()],
            [_op_record(node_path="cl-cluster-1000/op-9000", plain_text="Searchable body.")],
        )
        self.assertTrue(NodeVersion.objects.filter(
            node__path="cl-cluster-1000/op-9000", search_vector__isnull=False).exists())

    def test_idempotent_rerun(self):
        recs_d = [_dec_record(syllabus="The syllabus.")]
        recs_o = [_op_record(node_path="cl-cluster-1000/op-9000", plain_text="Body.")]
        self._ingest(recs_d, recs_o)
        before = NodeVersion.objects.count()

        # Re-run with a freshly-loaded hash map (simulating a separate run).
        _, ocounts = self._ingest(recs_d, recs_o)
        self.assertEqual(NodeVersion.objects.count(), before)  # no new versions
        self.assertEqual(ocounts["op_unchanged"], 1)
        self.assertEqual(ocounts["op_added"], 0)

    def test_amend_closes_old_and_opens_new(self):
        self._ingest(
            [_dec_record()],
            [_op_record(node_path="cl-cluster-1000/op-9000", plain_text="Original body.")],
        )
        _, ocounts = self._ingest(
            [_dec_record()],
            [_op_record(node_path="cl-cluster-1000/op-9000", plain_text="Revised body.")],
        )
        self.assertEqual(ocounts["op_amended"], 1)

        versions = NodeVersion.objects.filter(node__path="cl-cluster-1000/op-9000")
        self.assertEqual(versions.count(), 2)
        self.assertEqual(versions.filter(effective_to__isnull=True).count(), 1)  # one open
        self.assertEqual(versions.filter(effective_to__isnull=True).first().body_text,
                         "Revised body.")

    def test_decision_without_date_skips_version(self):
        dcounts, _ = self._ingest([_dec_record(date_filed="", syllabus="x")], [])
        # Container node created, but no datable head-matter version.
        self.assertTrue(Node.objects.filter(path="cl-cluster-1000").exists())
        self.assertEqual(dcounts["head_added"], 0)

    def test_head_matter_idempotent_and_amend(self):
        d1, _ = self._ingest([_dec_record(syllabus="Syllabus A.")], [])
        self.assertEqual(d1["head_added"], 1)
        # Re-run unchanged.
        d2, _ = self._ingest([_dec_record(syllabus="Syllabus A.")], [])
        self.assertEqual(d2["head_unchanged"], 1)
        self.assertEqual(d2["head_added"], 0)
        # Changed syllabus -> amend.
        d3, _ = self._ingest([_dec_record(syllabus="Syllabus B.")], [])
        self.assertEqual(d3["head_amended"], 1)
        decision = Node.objects.get(path="cl-cluster-1000")
        versions = NodeVersion.objects.filter(node=decision)
        self.assertEqual(versions.count(), 2)
        self.assertEqual(versions.filter(effective_to__isnull=True).count(), 1)
        self.assertIn("Syllabus B.", versions.get(effective_to__isnull=True).body_text)

    def test_orphan_opinion_skipped(self):
        open_hashes = load_open_version_hashes(self.source)
        # Opinion whose cluster was never written -> orphan, no node created.
        opinions = [parse_opinion(_op_record(
            cl_cluster_id=7777, node_path="cl-cluster-7777/op-1", plain_text="x"))]
        counts = write_opinions_batch(opinions, self.source, self.types, {}, open_hashes)
        self.assertEqual(counts["orphan_skipped"], 1)
        self.assertFalse(Node.objects.filter(path="cl-cluster-7777/op-1").exists())
