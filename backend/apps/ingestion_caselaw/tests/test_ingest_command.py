"""End-to-end: Phase-1 JSONL artifacts → ingest command → corpus rows."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.corpus.models import Node, NodeVersion


def _write_jsonl(path: Path, records):
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


class IngestCommandTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _write_jsonl(self.d / "clusters.jsonl", [
            {"cl_cluster_id": 1000, "node_path": "cl-cluster-1000", "docket_id": 100,
             "court_id": "iowa", "court_name": "Supreme Court of Iowa",
             "case_name": "State v. Smith", "case_name_short": "Smith",
             "case_name_full": "State v. John Smith", "date_filed": "2020-05-01",
             "precedential_status": "Published", "judges": "Mansfield",
             "citation_count": 3, "scdb_id": "", "slug": "s", "syllabus": "Syl.",
             "headnotes": "", "summary": "", "disposition": "", "posture": "",
             "nature_of_suit": ""},
        ])
        _write_jsonl(self.d / "opinions.jsonl", [
            {"cl_opinion_id": 9000, "cl_cluster_id": 1000,
             "node_path": "cl-cluster-1000/op-9000", "type": "020lead",
             "author_str": "Mansfield", "author_id": 42, "per_curiam": False,
             "joined_by_str": "", "page_count": 10, "download_url": "",
             "extracted_by_ocr": False, "sha1": "abc", "plain_text": "The opinion.",
             "html": "", "html_lawbox": "", "html_columbia": "", "html_anon_2020": "",
             "xml_harvard": "", "html_with_citations": ""},
        ])
        _write_jsonl(self.d / "citations.jsonl", [
            {"cl_citation_id": 5000, "cl_cluster_id": 1000, "volume": "987",
             "reporter": "N.W.2d", "page": "123", "type": 3},
        ])
        _write_jsonl(self.d / "dockets.jsonl", [
            {"docket_id": 100, "court_id": "iowa", "docket_number": "12-3456"},
        ])

    def test_dry_run_writes_nothing(self):
        call_command("ingest_iowa_caselaw", "--in-dir", str(self.d), "--dry-run")
        self.assertFalse(Node.objects.filter(path="cl-cluster-1000").exists())

    def test_ingest_creates_nodes_and_versions(self):
        call_command("ingest_iowa_caselaw", "--in-dir", str(self.d))

        decision = Node.objects.get(path="cl-cluster-1000")
        self.assertEqual(decision.source_metadata["citations"], ["987 N.W.2d 123"])
        self.assertEqual(decision.source_metadata["docket_number"], "12-3456")

        opinion = Node.objects.get(path="cl-cluster-1000/op-9000")
        self.assertEqual(opinion.parent_id, decision.pk)
        self.assertTrue(NodeVersion.objects.filter(
            node=opinion, body_text="The opinion.").exists())
        # Head-matter version on the decision (syllabus present).
        self.assertTrue(NodeVersion.objects.filter(node=decision).exists())

    def test_records_exactly_one_write_run(self):
        from apps.ingestion_caselaw.models import IngestionRun

        call_command("ingest_iowa_caselaw", "--in-dir", str(self.d))
        runs = IngestionRun.objects.filter(phase="write")
        self.assertEqual(runs.count(), 1)  # one consolidated run, not per-batch
        run = runs.first()
        self.assertEqual(run.nodes_added, 2)  # decision node + opinion node
        self.assertEqual(run.status, "approved")
        self.assertEqual(run.validation_errors, [])  # clean fixture
        self.assertEqual(run.last_cluster_id, 1000)

    def test_multi_batch_links_decisions_and_opinions(self):
        # Two decisions across batch-size=1, each with an opinion -> the
        # accumulated decision_cache must link opinions written in a later pass.
        _write_jsonl(self.d / "clusters.jsonl", [
            {"cl_cluster_id": cid, "node_path": f"cl-cluster-{cid}", "docket_id": 100,
             "court_id": "iowa", "court_name": "Supreme Court of Iowa",
             "case_name": f"Case {cid}", "case_name_short": "", "case_name_full": "",
             "date_filed": "2021-01-01", "precedential_status": "Published",
             "judges": "", "citation_count": 0, "scdb_id": "", "slug": "",
             "syllabus": "", "headnotes": "", "summary": "", "disposition": "",
             "posture": "", "nature_of_suit": ""}
            for cid in (1000, 1001)
        ])
        _write_jsonl(self.d / "opinions.jsonl", [
            {"cl_opinion_id": 9000 + i, "cl_cluster_id": cid,
             "node_path": f"cl-cluster-{cid}/op-{9000 + i}", "type": "020lead",
             "author_str": "", "author_id": None, "per_curiam": False,
             "joined_by_str": "", "page_count": None, "download_url": "",
             "extracted_by_ocr": False, "sha1": "", "plain_text": f"Body {cid}.",
             "html": "", "html_lawbox": "", "html_columbia": "", "html_anon_2020": "",
             "xml_harvard": "", "html_with_citations": ""}
            for i, cid in enumerate((1000, 1001))
        ])
        call_command("ingest_iowa_caselaw", "--in-dir", str(self.d), "--batch-size", "1")

        for cid in (1000, 1001):
            decision = Node.objects.get(path=f"cl-cluster-{cid}")
            opinion = Node.objects.get(path=f"cl-cluster-{cid}/op-{9000 + (cid - 1000)}")
            self.assertEqual(opinion.parent_id, decision.pk)
            self.assertTrue(NodeVersion.objects.filter(node=opinion).exists())

    def test_missing_file_errors(self):
        (self.d / "opinions.jsonl").unlink()
        with self.assertRaises(Exception):
            call_command("ingest_iowa_caselaw", "--in-dir", str(self.d))
