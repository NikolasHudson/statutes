"""#2 build_caselaw_citation_graph — CL citation-map → CASELAW_GRAPH edges + depth.

Drives the command over a tiny plain-CSV citation-map fixture (``open_bulk_csv``
reads a non-.bz2 path raw) against a handful of factory-built Iowa cases, and
asserts: in-corpus edges land with the right ``weight=depth``, out-of-corpus /
self / sibling rows are skipped, the ``caselaw_link`` (#1) edges are untouched,
the rebuild is idempotent, and ``--dry-run`` writes nothing.
"""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, tag

from apps.api.tests._factories import make_caselaw_case
from apps.corpus.models import (
    CrossReference,
    CrossReferenceKind,
    CrossReferenceSource,
    Node,
    NodeVersion,
    ReviewStatus,
)

_HEADER = "id,depth,cited_opinion_id,citing_opinion_id\n"


@tag("postgres")
class BuildCitationGraphTests(TestCase):
    def setUp(self):
        # Three standalone cases (cluster, opinion): A(1000,10) B(2000,20) C(3000,30).
        self.dec_a, self.op_a, self.ver_a = make_caselaw_case(cl_cluster_id=1000, cl_opinion_id=10)
        self.dec_b, self.op_b, self.ver_b = make_caselaw_case(cl_cluster_id=2000, cl_opinion_id=20)
        self.dec_c, self.op_c, self.ver_c = make_caselaw_case(cl_cluster_id=3000, cl_opinion_id=30)
        # A two-opinion decision for the sibling case: op40 (lead) + op41 (dissent).
        self.dec_d, self.op_d40, self.ver_d40 = make_caselaw_case(cl_cluster_id=4000, cl_opinion_id=40)
        self.op_d41 = Node.objects.create(
            source=self.op_d40.source, node_type=self.op_d40.node_type,
            parent=self.dec_d, ordinal="021", path="cl-cluster-4000/op-41",
            heading="Dissent", source_metadata={"cl_opinion_id": 41},
        )
        NodeVersion.objects.create(
            node=self.op_d41, body_text="dissent", effective_from=dt.date(2020, 1, 1),
            content_hash="d41", review_status=ReviewStatus.APPROVED,
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _citation_map(self, rows: list[tuple[int, int, int, int]]) -> str:
        """rows = [(id, depth, cited_clid, citing_clid), ...] → path to a .csv."""
        path = Path(self.tmp.name) / "citation-map.csv"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(_HEADER)
            for rid, depth, cited, citing in rows:
                fh.write(f"{rid},{depth},{cited},{citing}\n")
        return str(path)

    def _run(self, rows, **kw):
        call_command("build_caselaw_citation_graph", "--citation-map", self._citation_map(rows), **kw)

    def test_builds_in_corpus_edges_with_depth(self):
        self._run([
            (1, 3, 10, 20),       # B cites A ×3  → edge, weight 3
            (2, 1, 20, 30),       # C cites B ×1  → edge, weight 1
            (3, 5, 99999, 20),    # B cites non-corpus → skipped
            (4, 2, 10, 88888),    # non-corpus cites A → skipped
            (5, 1, 40, 41),       # dissent → lead, same decision → sibling skip
            (6, 1, 10, 10),       # A cites A → self skip
        ])
        edges = CrossReference.objects.filter(source=CrossReferenceSource.CASELAW_GRAPH)
        self.assertEqual(edges.count(), 2)

        b_to_a = edges.get(from_version=self.ver_b)
        self.assertEqual(b_to_a.to_node_id, self.op_a.pk)   # opinion-level target
        self.assertEqual(b_to_a.weight, 3)
        self.assertEqual(b_to_a.kind, CrossReferenceKind.INTERNAL)

        c_to_b = edges.get(from_version=self.ver_c)
        self.assertEqual(c_to_b.to_node_id, self.op_b.pk)
        self.assertEqual(c_to_b.weight, 1)

    def test_does_not_touch_caselaw_link_edges(self):
        link = CrossReference.objects.create(
            from_version=self.ver_b, to_node=self.op_a,
            kind=CrossReferenceKind.INTERNAL,
            source=CrossReferenceSource.CASELAW_LINK,
        )
        self._run([(1, 2, 10, 20)])
        self.assertTrue(CrossReference.objects.filter(pk=link.pk).exists())
        self.assertEqual(
            CrossReference.objects.filter(source=CrossReferenceSource.CASELAW_GRAPH).count(), 1
        )

    def test_idempotent_rebuild(self):
        rows = [(1, 3, 10, 20), (2, 1, 20, 30)]
        self._run(rows)
        self._run(rows)
        self.assertEqual(
            CrossReference.objects.filter(source=CrossReferenceSource.CASELAW_GRAPH).count(), 2
        )

    def test_non_positive_depth_falls_back_to_one(self):
        # A corrupt negative depth must not crash the PositiveIntegerField insert.
        self._run([(1, -5, 10, 20)])
        edge = CrossReference.objects.get(source=CrossReferenceSource.CASELAW_GRAPH)
        self.assertEqual(edge.weight, 1)

    def test_dry_run_writes_nothing(self):
        self._run([(1, 3, 10, 20)], dry_run=True)
        self.assertEqual(
            CrossReference.objects.filter(source=CrossReferenceSource.CASELAW_GRAPH).count(), 0
        )
