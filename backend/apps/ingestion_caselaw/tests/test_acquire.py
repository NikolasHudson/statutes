"""Golden tests for the Phase-1 acquire join + JSONL emission.

A tiny five-table fixture with a mix of Iowa and non-Iowa rows exercises the
court→docket→cluster→opinion/citation filter, the JSONL record shapes, type
coercion, byte-stable determinism, and the DB audit persistence.
"""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from ..acquire import persist_acquire_run, run_acquire

COURTS = (
    ["id", "full_name"],
    [
        ["iowa", "Supreme Court of Iowa"],
        ["iowactapp", "Court of Appeals of Iowa"],
        ["minn", "Supreme Court of Minnesota"],  # non-target
    ],
)
DOCKETS = (
    ["id", "court_id", "docket_number"],
    [
        ["100", "iowa", "12-3456"],
        ["101", "iowactapp", "A-22-001"],
        ["200", "minn", "M-1"],  # excluded: not an Iowa court
    ],
)
CLUSTER_COLS = [
    "id", "docket_id", "case_name", "case_name_short", "case_name_full",
    "date_filed", "precedential_status", "judges", "citation_count", "scdb_id",
    "slug", "syllabus", "headnotes", "summary", "disposition", "posture",
    "nature_of_suit",
]
CLUSTERS = (
    CLUSTER_COLS,
    [
        ["1000", "100", "State v. Smith", "Smith", "State v. John Smith",
         "2020-05-01", "Published", "Mansfield, J.", "3", "", "state-v-smith",
         "syllabus text", "", "", "affirmed", "", ""],
        ["1001", "101", "In re Doe", "Doe", "In re Doe", "2019-03-15",
         "Unpublished", "Per Curiam", "0", "", "in-re-doe", "", "", "", "", "", ""],
        ["2000", "200", "Minn v. X", "X", "Minn v. X", "2021-01-01", "Published",
         "", "1", "", "minn-v-x", "", "", "", "", "", ""],  # excluded
    ],
)
OPINION_COLS = [
    "id", "cluster_id", "type", "author_str", "author_id", "per_curiam",
    "joined_by_str", "page_count", "download_url", "extracted_by_ocr", "sha1",
    "plain_text", "html", "html_lawbox", "html_columbia", "html_anon_2020",
    "xml_harvard", "html_with_citations",
]
OPINIONS = (
    OPINION_COLS,
    [
        ["9000", "1000", "020lead", "Mansfield", "42", "f", "", "10",
         "http://x", "f", "abc", "Opinion text one", "", "", "", "", "", ""],
        ["9001", "1000", "040dissent", "Appel", "43", "f", "", "2", "", "f",
         "def", "Dissent text", "", "", "", "", "", ""],
        ["9002", "1001", "010combined", "", "", "t", "", "", "", "t", "ghi",
         "OCR body", "", "", "", "", "", ""],
        ["9003", "2000", "020lead", "", "", "f", "", "", "", "f", "jkl",
         "Minn opinion", "", "", "", "", "", ""],  # excluded
    ],
)
CITATIONS = (
    ["id", "cluster_id", "volume", "reporter", "page", "type"],
    [
        ["5000", "1000", "987", "N.W.2d", "123", "3"],
        ["5001", "1000", "100", "Iowa", "1", "2"],  # parallel cite
        ["5002", "1001", "999", "N.W.2d", "456", "3"],
        ["5003", "2000", "111", "N.W.2d", "222", "3"],  # excluded (minn cluster)
        ["5004", "1001", "500", "N.W.2d", "10", ""],  # nullable type -> JSON null
    ],
)


def _write_csv(path: Path, spec) -> None:
    header, rows = spec
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _build_bulk_dir(base: Path) -> Path:
    bulk = base / "bulk"
    bulk.mkdir()
    _write_csv(bulk / "courts.csv", COURTS)
    _write_csv(bulk / "dockets.csv", DOCKETS)
    _write_csv(bulk / "opinion-clusters.csv", CLUSTERS)
    _write_csv(bulk / "opinions.csv", OPINIONS)
    _write_csv(bulk / "citations.csv", CITATIONS)
    return bulk


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class RunAcquireTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.bulk = _build_bulk_dir(self.base)
        self.out = self.base / "out"

    def test_filters_to_iowa_and_shapes_records(self):
        result = run_acquire(self.bulk, self.out)
        self.assertEqual(
            result.counts,
            {"dockets": 2, "clusters": 2, "citations": 4, "opinions": 3, "rejects": 0},
        )

        clusters = {c["cl_cluster_id"]: c for c in _read_jsonl(self.out / "clusters.jsonl")}
        self.assertEqual(set(clusters), {1000, 1001})
        self.assertNotIn(2000, clusters)  # minn cluster excluded
        self.assertEqual(clusters[1000]["node_path"], "cl-cluster-1000")
        self.assertEqual(clusters[1000]["court_id"], "iowa")
        self.assertEqual(clusters[1000]["court_name"], "Supreme Court of Iowa")
        self.assertEqual(clusters[1001]["court_id"], "iowactapp")
        self.assertEqual(clusters[1000]["citation_count"], 3)  # coerced to int
        self.assertEqual(clusters[1001]["precedential_status"], "Unpublished")

        opinions = {o["cl_opinion_id"]: o for o in _read_jsonl(self.out / "opinions.jsonl")}
        self.assertEqual(set(opinions), {9000, 9001, 9002})
        self.assertEqual(opinions[9000]["node_path"], "cl-cluster-1000/op-9000")
        self.assertEqual(opinions[9000]["author_id"], 42)       # int
        self.assertEqual(opinions[9000]["per_curiam"], False)   # "f" -> bool
        self.assertEqual(opinions[9002]["author_id"], None)     # "" -> null
        self.assertEqual(opinions[9002]["per_curiam"], True)    # "t" -> bool
        self.assertEqual(opinions[9002]["extracted_by_ocr"], True)
        self.assertEqual(opinions[9002]["page_count"], None)    # "" -> null
        self.assertEqual(opinions[9000]["plain_text"], "Opinion text one")

        citations = {c["cl_citation_id"]: c for c in _read_jsonl(self.out / "citations.jsonl")}
        self.assertEqual(set(citations), {5000, 5001, 5002, 5004})
        self.assertEqual(citations[5000]["type"], 3)        # int
        self.assertIsNone(citations[5004]["type"])          # nullable -> null, not rejected

        dockets = {d["docket_id"]: d for d in _read_jsonl(self.out / "dockets.jsonl")}
        self.assertEqual(set(dockets), {100, 101})
        self.assertEqual(dockets[100]["docket_number"], "12-3456")

        # Clean fixture -> empty rejects sidecar exists with zero rows.
        self.assertTrue((self.out / "rejects.jsonl").exists())
        self.assertEqual(_read_jsonl(self.out / "rejects.jsonl"), [])

        # No leftover .partial files.
        self.assertEqual(list(self.out.glob("*.partial")), [])

    def test_deterministic_byte_identical(self):
        out1 = self.base / "o1"
        out2 = self.base / "o2"
        r1 = run_acquire(self.bulk, out1)
        r2 = run_acquire(self.bulk, out2)
        self.assertEqual(set(r1.artifact_paths), set(r2.artifact_paths))
        for name in r1.artifact_paths:  # includes rejects.jsonl
            h1 = hashlib.sha256(r1.artifact_paths[name].read_bytes()).hexdigest()
            h2 = hashlib.sha256(r2.artifact_paths[name].read_bytes()).hexdigest()
            self.assertEqual(h1, h2, f"{name} not byte-identical across runs")

    def test_bad_row_routed_to_rejects(self):
        # An Iowa opinion (cluster 1000) with an empty NOT-NULL id -> _to_int
        # raises -> the row is routed to rejects.jsonl, not opinions.jsonl, and
        # the pass continues.
        bulk = self.base / "bulkbad"
        bulk.mkdir()
        _write_csv(bulk / "courts.csv", COURTS)
        _write_csv(bulk / "dockets.csv", DOCKETS)
        _write_csv(bulk / "opinion-clusters.csv", CLUSTERS)
        _write_csv(bulk / "citations.csv", CITATIONS)
        bad_opinions = (OPINION_COLS, OPINIONS[1] + [
            ["", "1000", "020lead", "X", "", "f", "", "", "", "f", "z",
             "orphan body", "", "", "", "", "", ""],  # empty id -> reject
        ])
        _write_csv(bulk / "opinions.csv", bad_opinions)

        out = self.base / "outbad"
        result = run_acquire(bulk, out)
        self.assertEqual(result.counts["rejects"], 1)
        self.assertEqual(result.counts["opinions"], 3)  # the 3 good Iowa opinions

        rejects = _read_jsonl(out / "rejects.jsonl")
        self.assertEqual(len(rejects), 1)
        self.assertEqual(rejects[0]["artifact"], "opinions")
        self.assertIn("ValueError", rejects[0]["error"])

    def test_missing_court_raises(self):
        # courts file without iowactapp -> the requested court is absent.
        bulk2 = self.base / "bulk2"
        bulk2.mkdir()
        _write_csv(bulk2 / "courts.csv", (["id", "full_name"], [["iowa", "Supreme Court of Iowa"]]))
        _write_csv(bulk2 / "dockets.csv", DOCKETS)
        _write_csv(bulk2 / "opinion-clusters.csv", CLUSTERS)
        _write_csv(bulk2 / "opinions.csv", OPINIONS)
        _write_csv(bulk2 / "citations.csv", CITATIONS)
        with self.assertRaises(ValueError):
            run_acquire(bulk2, self.base / "out2")


class PersistAcquireTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.bulk = _build_bulk_dir(self.base)

    def test_persists_raw_rows_and_run(self):
        from ..models import IngestionRun, RawIngestion

        storage = self.base / "raw"  # tmp storage dir — do not touch repo data/raw
        result = run_acquire(self.bulk, self.base / "out")
        run = persist_acquire_run(
            result, export_year=2026, fetched_from="test", storage_dir=storage
        )

        # Four payload artifacts -> four RawIngestion rows (rejects is audit-only).
        self.assertEqual(RawIngestion.objects.count(), 4)
        self.assertEqual(run.phase, "acquire")
        self.assertEqual(run.status, "pending")
        self.assertIsNotNone(run.finished_at)
        log = json.loads(run.log)
        self.assertEqual(log["counts"]["opinions"], 3)
        self.assertEqual(log["counts"]["rejects"], 0)
        self.assertEqual(set(log["artifacts"]), {"clusters", "opinions", "citations", "dockets"})

        # Each artifact snapshot lives at <storage_dir>/<content_hash>.bin.
        for raw in RawIngestion.objects.all():
            self.assertEqual(Path(raw.storage_path).parent, storage)
            self.assertTrue(Path(raw.storage_path).name.endswith(".bin"))
            self.assertTrue(Path(raw.storage_path).exists())

        # Idempotent: re-persisting the identical artifacts adds no new raw rows.
        persist_acquire_run(
            result, export_year=2026, fetched_from="test", storage_dir=storage
        )
        self.assertEqual(RawIngestion.objects.count(), 4)
        self.assertEqual(IngestionRun.objects.count(), 2)  # a second run row, same raws
