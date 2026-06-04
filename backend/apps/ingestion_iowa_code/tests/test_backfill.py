"""Backfill a prior Iowa Code edition behind already-loaded current data.

Exercises the four branches of ``backfill_edition`` against the real DB:
unchanged (backdate), changed (insert historical), repealed-between (create),
and added-after (leave alone). Tagged 'postgres' like the e2e ingest test.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from django.test import TransactionTestCase, tag

from apps.corpus.models import Edition, Node, NodeVersion, ReviewStatus
from apps.corpus.services.lookups import current_version, get_section_at
from apps.ingestion_iowa_code.backfill import backfill_edition
from apps.ingestion_iowa_code.differ import diff_against_db
from apps.ingestion_iowa_code.parser import parse_probe_json
from apps.ingestion_iowa_code.writer import (
    apply_changeset,
    get_iowa_code_source,
    persist_raw_input,
)


SAMPLE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "samples" / "iowa_code_probe.json"
)

CURRENT_AS_OF = dt.date(2026, 4, 30)
PRIOR_AS_OF = dt.date(2025, 1, 1)


@tag("postgres")
class BackfillEditionTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.sample = json.loads(SAMPLE_PATH.read_bytes())
        self.source = get_iowa_code_source()
        self._ingest_current()

        # Build the prior (2025) edition by mutating a copy of the sample.
        older = json.loads(SAMPLE_PATH.read_bytes())
        older["code_year"] = 2025
        ch0 = older["samples"][0]
        secs = ch0["sections"]
        self.assertGreaterEqual(len(secs), 3, "need a chapter with >=3 sections")

        # changed: section text differs in 2025
        self.changed_path = secs[0]["number"]
        secs[0]["body_text"] = "OLD 2025 TEXT. " + secs[0]["body_text"]

        # added-after: present now, absent from the 2025 edition
        self.added_after_path = secs[1]["number"]
        del secs[1]

        # unchanged: untouched section in a different chapter
        self.unchanged_path = older["samples"][1]["sections"][0]["number"]

        # repealed-between: present in 2025 only, no node in current store
        self.repealed_path = f"{ch0['chapter']}.9999"
        ch0["sections"].append(
            {
                "number": self.repealed_path,
                "heading": "Repealed since 2025",
                "body_text": "GONE BY 2026.",
                "history_brackets": [],
                "acts_citations": [],
                "referred_to_in": [],
                "citation_pdf_url": "",
                "citation_html_url": "",
                "source_rtf_url": "",
            }
        )

        self.older_parsed = parse_probe_json(older)
        Edition.objects.create(
            source=self.source, year=2026, label="Iowa Code 2026", as_of_date=CURRENT_AS_OF
        )

    def _ingest_current(self):
        parsed = parse_probe_json(self.sample)
        cs = diff_against_db(parsed, self.source)
        raw = persist_raw_input(
            payload_bytes=json.dumps(self.sample).encode(),
            source_kind="probe_json",
            code_year=parsed.code_year,
            fetched_from="test",
            storage_dir=Path("/tmp/iowa_corpus_test_raw"),
        )
        apply_changeset(parsed=parsed, changeset=cs, raw=raw, effective_from=CURRENT_AS_OF)
        # Approve so point-in-time lookups (which filter approved) can see them.
        NodeVersion.objects.update(review_status=ReviewStatus.APPROVED)

    def _backfill(self, **kw):
        return backfill_edition(
            parsed=self.older_parsed,
            source=self.source,
            as_of=PRIOR_AS_OF,
            next_as_of=CURRENT_AS_OF,
            **kw,
        )

    def test_changed_inserts_historical_version_behind_current(self):
        self._backfill()
        node = Node.objects.get(source=self.source, path=self.changed_path)
        versions = list(node.versions.order_by("effective_from"))
        self.assertEqual(len(versions), 2)
        old, current = versions
        self.assertEqual(old.effective_from, PRIOR_AS_OF)
        self.assertEqual(old.effective_to, CURRENT_AS_OF)
        self.assertIsNone(current.effective_to)
        self.assertIn("OLD 2025 TEXT", get_section_at(node, PRIOR_AS_OF).body_text)
        self.assertNotIn("OLD 2025 TEXT", get_section_at(node, CURRENT_AS_OF).body_text)
        # Historical rows carry no embedding.
        self.assertIsNone(old.embedding)

    def test_unchanged_backdates_existing_version(self):
        self._backfill()
        node = Node.objects.get(source=self.source, path=self.unchanged_path)
        versions = list(node.versions.all())
        self.assertEqual(len(versions), 1, "unchanged must not duplicate")
        self.assertEqual(versions[0].effective_from, PRIOR_AS_OF)
        self.assertIsNone(versions[0].effective_to)
        self.assertIsNotNone(get_section_at(node, PRIOR_AS_OF))

    def test_repealed_between_creates_repealed_node(self):
        self._backfill()
        node = Node.objects.get(source=self.source, path=self.repealed_path)
        self.assertTrue(node.is_repealed)
        self.assertIn("GONE BY 2026", get_section_at(node, PRIOR_AS_OF).body_text)
        # Closed-open: gone exactly at the next edition's as-of date.
        self.assertIsNone(get_section_at(node, CURRENT_AS_OF))
        self.assertIsNone(current_version(node))

    def test_added_after_is_left_untouched(self):
        report = self._backfill()
        node = Node.objects.get(source=self.source, path=self.added_after_path)
        self.assertEqual(node.versions.count(), 1)
        self.assertEqual(node.versions.get().effective_from, CURRENT_AS_OF)
        self.assertIsNone(get_section_at(node, PRIOR_AS_OF))
        self.assertGreaterEqual(report.added_after_skipped, 1)

    def test_report_counts(self):
        report = self._backfill()
        self.assertEqual(report.changed_inserted, 1)
        self.assertEqual(report.repealed_between_created, 1)
        self.assertGreaterEqual(report.unchanged_backdated, 1)
        self.assertEqual(report.year, 2025)

    def test_idempotent_second_run(self):
        self._backfill()
        before = NodeVersion.objects.count()
        report2 = self._backfill()
        self.assertEqual(NodeVersion.objects.count(), before, "second run added rows")
        # Everything now already extends back to PRIOR_AS_OF.
        self.assertEqual(report2.unchanged_backdated, 0)
        self.assertEqual(report2.changed_inserted, 0)
        self.assertGreater(report2.already_present, 0)

    def test_dry_run_writes_nothing(self):
        before = NodeVersion.objects.count()
        report = self._backfill(dry_run=True)
        self.assertEqual(NodeVersion.objects.count(), before)
        self.assertEqual(report.changed_inserted, 1)

    def test_unchanged_detection_ignores_stale_stored_hash(self):
        # Stored content_hash can predate later normalization and no longer
        # match its own body_text. An unchanged section with a stale hash must
        # still be detected as unchanged (compared by body, not stored hash).
        node = Node.objects.get(source=self.source, path=self.unchanged_path)
        node.versions.update(content_hash="stale-deadbeef")
        report = self._backfill()
        self.assertEqual(node.versions.count(), 1, "false amendment created a row")
        self.assertEqual(node.versions.get().effective_from, PRIOR_AS_OF)
        self.assertGreaterEqual(report.unchanged_backdated, 1)

    def test_as_of_must_precede_next(self):
        with self.assertRaises(ValueError):
            backfill_edition(
                parsed=self.older_parsed,
                source=self.source,
                as_of=CURRENT_AS_OF,
                next_as_of=CURRENT_AS_OF,
            )
