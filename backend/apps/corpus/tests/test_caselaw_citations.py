"""#4 ReporterCitation + #1 CrossReference backfill, Court seed, source_metadata GIN.

Drives the two post-ingest commands (load_case_citations,
backfill_caselaw_cross_references) over temp JSONL fixtures, then asserts the
resolver/edge behaviour, idempotency, source-scoping, the seeded courts, and the
JSONB GIN index.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, tag

from apps.api.tests._factories import make_caselaw_case, make_iowa_caselaw_source
from apps.corpus.models import (
    Court,
    CrossReference,
    CrossReferenceKind,
    CrossReferenceSource,
    Node,
    NodeVersion,
    ReporterCitation,
    ReviewStatus,
)


def _write_jsonl(dir_path: Path, name: str, rows: list[dict]) -> None:
    with (dir_path / name).open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


@tag("postgres")
class LoadCaseCitationsTests(TestCase):
    def setUp(self):
        # cluster 1000 is in-slice; 9999 is not.
        self.decision, _, _ = make_caselaw_case(cl_cluster_id=1000, cl_opinion_id=10)
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _citations(self, rows):
        _write_jsonl(self.dir, "citations.jsonl", rows)

    def test_populates_and_resolves(self):
        self._citations([
            {"cl_citation_id": 1, "cl_cluster_id": 1000,
             "reporter": "N.W.2d", "volume": "759", "page": "3", "type": 3},
            {"cl_citation_id": 2, "cl_cluster_id": 9999,  # out of slice
             "reporter": "N.W.2d", "volume": "100", "page": "5", "type": 3},
        ])
        call_command("load_case_citations", "--in-dir", str(self.dir))
        self.assertEqual(ReporterCitation.objects.count(), 2)
        in_slice = ReporterCitation.objects.get(cl_citation_id=1)
        self.assertEqual(in_slice.to_node_id, self.decision.pk)
        out_slice = ReporterCitation.objects.get(cl_citation_id=2)
        self.assertIsNone(out_slice.to_node_id)  # unresolved, still stored

    def test_idempotent_reload(self):
        self._citations([
            {"cl_citation_id": 1, "cl_cluster_id": 1000,
             "reporter": "N.W.2d", "volume": "759", "page": "3", "type": 3},
        ])
        call_command("load_case_citations", "--in-dir", str(self.dir))
        call_command("load_case_citations", "--in-dir", str(self.dir))
        self.assertEqual(ReporterCitation.objects.count(), 1)

    def test_to_node_set_null_on_decision_delete(self):
        # Deleting the cited Node must NULL to_node, not delete the citation row
        # (it remains a valid reporter→cluster fact, re-resolved on reload).
        self._citations([
            {"cl_citation_id": 1, "cl_cluster_id": 1000,
             "reporter": "N.W.2d", "volume": "759", "page": "3", "type": 3},
        ])
        call_command("load_case_citations", "--in-dir", str(self.dir))
        self.decision.delete()
        row = ReporterCitation.objects.get(cl_citation_id=1)  # still exists
        self.assertIsNone(row.to_node_id)

    def test_ambiguous_triple_keeps_both_rows(self):
        # Same (reporter, volume, page) for two different clusters → both stored
        # (cl_citation_id is the unique key), no IntegrityError.
        make_caselaw_case(cl_cluster_id=2000, cl_opinion_id=20)
        self._citations([
            {"cl_citation_id": 1, "cl_cluster_id": 1000,
             "reporter": "N.W.2d", "volume": "1", "page": "1", "type": 3},
            {"cl_citation_id": 2, "cl_cluster_id": 2000,
             "reporter": "N.W.2d", "volume": "1", "page": "1", "type": 3},
        ])
        call_command("load_case_citations", "--in-dir", str(self.dir))
        self.assertEqual(
            ReporterCitation.objects.filter(
                reporter="N.W.2d", volume="1", page="1"
            ).count(),
            2,
        )


@tag("postgres")
class BackfillCaselawCrossRefTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _opinions(self, rows):
        _write_jsonl(self.dir, "opinions.jsonl", rows)

    def _op_row(self, cl_opinion_id, cl_cluster_id, html):
        return {
            "cl_opinion_id": cl_opinion_id, "cl_cluster_id": cl_cluster_id,
            "node_path": f"cl-cluster-{cl_cluster_id}/op-{cl_opinion_id}",
            "html_with_citations": html,
        }

    def test_opinion_link_makes_internal_edge(self):
        cited_dec, cited_op, _ = make_caselaw_case(cl_cluster_id=100, cl_opinion_id=111)
        _, citing_op, citing_ver = make_caselaw_case(cl_cluster_id=200, cl_opinion_id=222)
        self._opinions([
            self._op_row(111, 100, "<p>leading case</p>"),
            self._op_row(222, 200, '<p>See <a href="/opinion/111/x/">prior</a>.</p>'),
        ])
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))

        edges = CrossReference.objects.filter(source=CrossReferenceSource.CASELAW_LINK)
        self.assertEqual(edges.count(), 1)
        edge = edges.get()
        self.assertEqual(edge.from_version_id, citing_ver.pk)  # the OPINION version
        self.assertEqual(edge.to_node_id, cited_op.pk)
        self.assertEqual(edge.kind, CrossReferenceKind.INTERNAL)

    def test_unresolved_opinion_link_makes_external_edge(self):
        _, _, citing_ver = make_caselaw_case(cl_cluster_id=200, cl_opinion_id=222)
        self._opinions([
            self._op_row(222, 200,
                         '<p>See <a href="/opinion/88888/gone/">Lost Case</a>.</p>'),
        ])
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))
        edge = CrossReference.objects.get(source=CrossReferenceSource.CASELAW_LINK)
        self.assertIsNone(edge.to_node_id)
        self.assertEqual(edge.kind, CrossReferenceKind.EXTERNAL)
        self.assertEqual(edge.external_text, "Lost Case")

    def test_reporter_link_unambiguous_internal_ambiguous_external(self):
        cited_dec, _, _ = make_caselaw_case(cl_cluster_id=100, cl_opinion_id=111)
        # one unambiguous reporter cite → the cited decision
        ReporterCitation.objects.create(
            cl_citation_id=1, cl_cluster_id=100, reporter="N.W.2d",
            volume="759", page="3", to_node=cited_dec,
        )
        # an ambiguous triple (two cases) → dropped from resolver → external
        other_dec, _, _ = make_caselaw_case(cl_cluster_id=300, cl_opinion_id=333)
        for cid, dec in ((2, cited_dec), (3, other_dec)):
            ReporterCitation.objects.create(
                cl_citation_id=cid, cl_cluster_id=dec.source_metadata["cl_cluster_id"],
                reporter="N.W.2d", volume="500", page="9", to_node=dec,
            )
        _, _, citing_ver = make_caselaw_case(cl_cluster_id=200, cl_opinion_id=222)
        self._opinions([
            self._op_row(222, 200,
                         '<a href="/c/N.W.2d/759/3/">759 N.W.2d 3</a> '
                         '<a href="/c/N.W.2d/500/9/">500 N.W.2d 9</a>'),
        ])
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))

        internal = CrossReference.objects.filter(
            source=CrossReferenceSource.CASELAW_LINK, to_node__isnull=False
        )
        external = CrossReference.objects.filter(
            source=CrossReferenceSource.CASELAW_LINK, to_node__isnull=True
        )
        self.assertEqual(internal.count(), 1)
        self.assertEqual(internal.get().to_node_id, cited_dec.pk)
        self.assertEqual(external.count(), 1)
        self.assertEqual(external.get().external_text, "500 N.W.2d 9")

    def test_self_reference_skipped(self):
        _, citing_op, citing_ver = make_caselaw_case(cl_cluster_id=200, cl_opinion_id=222)
        self._opinions([
            self._op_row(222, 200, '<a href="/opinion/222/self/">itself</a>'),
        ])
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))
        self.assertEqual(
            CrossReference.objects.filter(
                source=CrossReferenceSource.CASELAW_LINK
            ).count(),
            0,
        )

    def test_sibling_opinion_link_skipped(self):
        # A concurrence linking the lead opinion of the SAME decision is an
        # intra-case reference, not a citation to outside authority.
        _, lead_op, _ = make_caselaw_case(cl_cluster_id=200, cl_opinion_id=201)
        # second opinion (concurrence) under the SAME decision (cluster 200)
        src, _, opinion_t = make_iowa_caselaw_source()
        decision = Node.objects.get(path="cl-cluster-200")
        concur = Node.objects.create(
            source=src, node_type=opinion_t, parent=decision, ordinal="030",
            path="cl-cluster-200/op-202", heading="Concurrence",
            source_metadata={"cl_opinion_id": 202},
        )
        NodeVersion.objects.create(
            node=concur, body_text="I concur.", effective_from=dt.date(2020, 1, 1),
            content_hash="h", review_status=ReviewStatus.APPROVED,
        )
        self._opinions([
            self._op_row(201, 200, "<p>lead</p>"),
            self._op_row(202, 200, '<a href="/opinion/201/lead/">the lead op</a>'),
        ])
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))
        self.assertEqual(
            CrossReference.objects.filter(
                source=CrossReferenceSource.CASELAW_LINK
            ).count(),
            0,  # sibling link to the same decision is skipped
        )

    def test_long_external_text_does_not_crash(self):
        # Regression: an unbounded external_text would overflow the partial
        # unique btree index (row-size limit) and abort the chunk.
        _, _, citing_ver = make_caselaw_case(cl_cluster_id=200, cl_opinion_id=222)
        huge = "X" * 6000  # unresolved link with a giant display
        self._opinions([
            self._op_row(222, 200, f'<a href="/opinion/77777/g/">{huge}</a>'),
        ])
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))
        edge = CrossReference.objects.get(source=CrossReferenceSource.CASELAW_LINK)
        self.assertIsNone(edge.to_node_id)
        self.assertLessEqual(len(edge.external_text), 400)

    def test_idempotent_and_source_scoped(self):
        cited_dec, cited_op, _ = make_caselaw_case(cl_cluster_id=100, cl_opinion_id=111)
        _, _, citing_ver = make_caselaw_case(cl_cluster_id=200, cl_opinion_id=222)
        # a pre-existing #2 graph edge on the same from_version must survive #1.
        graph_edge = CrossReference.objects.create(
            from_version=citing_ver, to_node=cited_op,
            kind=CrossReferenceKind.INTERNAL,
            source=CrossReferenceSource.CASELAW_GRAPH, weight=4,
        )
        self._opinions([
            self._op_row(111, 100, "<p>leading case</p>"),
            self._op_row(222, 200, '<a href="/opinion/111/x/">prior</a>'),
        ])
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))
        call_command("backfill_caselaw_cross_references", "--in-dir", str(self.dir))

        self.assertEqual(
            CrossReference.objects.filter(
                source=CrossReferenceSource.CASELAW_LINK
            ).count(),
            1,  # not doubled by the second run
        )
        self.assertTrue(CrossReference.objects.filter(pk=graph_edge.pk).exists())


@tag("postgres")
class CourtSeedTests(TestCase):
    def test_iowa_courts_seeded_with_levels(self):
        # Assert the REAL CourtListener slug 'iowa' (not 'iowasupct').
        supreme = Court.objects.get(court_id="iowa")
        self.assertEqual(supreme.level, 1)
        appeals = Court.objects.get(court_id="iowactapp")
        self.assertEqual(appeals.level, 2)
        self.assertFalse(Court.objects.filter(court_id="iowasupct").exists())
        # binding rank: supreme binds appellate
        self.assertLess(supreme.level, appeals.level)


@tag("postgres")
class SourceMetadataGinTests(TestCase):
    def test_gin_index_exists(self):
        with connection.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename='corpus_node' AND indexname='node_source_metadata_gin'"
            )
            row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertIn("gin", row[0].lower())
        self.assertIn("jsonb_path_ops", row[0])

    def test_containment_filter(self):
        make_caselaw_case(cl_cluster_id=1, cl_opinion_id=1,
                          court_id="iowa", precedential_status="Published")
        make_caselaw_case(cl_cluster_id=2, cl_opinion_id=2,
                          court_id="iowactapp", precedential_status="Unpublished")
        self.assertEqual(
            Node.objects.filter(source_metadata__court_id="iowa").count(), 1
        )
        self.assertEqual(
            Node.objects.filter(source_metadata__precedential_status="Published").count(),
            1,
        )
