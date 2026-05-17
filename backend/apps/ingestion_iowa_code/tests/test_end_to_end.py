"""End-to-end ingest test against the real DB.

Uses TransactionTestCase so the seed-data migration runs in fixture setup.
Tagged 'postgres' so a developer without Docker running can skip via:

    python manage.py test --exclude-tag postgres
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from django.test import TransactionTestCase, tag

from apps.citations.parser import parse as parse_citation
from apps.citations.resolver import resolve as resolve_citation
from apps.corpus.models import Node, NodeVersion, ReviewStatus
from apps.ingestion_iowa_code.differ import diff_against_db
from apps.ingestion_iowa_code.parser import parse_probe_json
from apps.ingestion_iowa_code.validators import validate
from apps.ingestion_iowa_code.writer import (
    apply_changeset,
    get_iowa_code_source,
    persist_raw_input,
)


SAMPLE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "samples" / "iowa_code_probe.json"
)


@tag("postgres")
class IngestEndToEndTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.payload_bytes = SAMPLE_PATH.read_bytes()
        self.payload = json.loads(self.payload_bytes.decode("utf-8"))
        self.parsed = parse_probe_json(self.payload)
        self.source = get_iowa_code_source()

    def _ingest(self, payload_bytes: bytes, parsed) -> None:
        cs = diff_against_db(parsed, self.source)
        validate(parsed, cs)
        raw = persist_raw_input(
            payload_bytes=payload_bytes,
            source_kind="probe_json",
            code_year=parsed.code_year,
            fetched_from="test",
            storage_dir=Path("/tmp/iowa_corpus_test_raw"),
        )
        apply_changeset(parsed=parsed, changeset=cs, raw=raw)

    def test_first_ingest_creates_all_nodes(self):
        self._ingest(self.payload_bytes, self.parsed)

        chapters = Node.objects.filter(
            source=self.source, node_type__key="chapter"
        )
        self.assertEqual(chapters.count(), 11)
        sections = Node.objects.filter(
            source=self.source, node_type__key="section"
        )
        self.assertEqual(sections.count(), 756)
        self.assertEqual(NodeVersion.objects.count(), 756)
        self.assertEqual(
            NodeVersion.objects.filter(
                review_status=ReviewStatus.PENDING
            ).count(),
            756,
        )

    def test_re_ingest_is_idempotent(self):
        self._ingest(self.payload_bytes, self.parsed)
        self._ingest(self.payload_bytes, self.parsed)

        # Still 756 versions — no duplicates.
        self.assertEqual(NodeVersion.objects.count(), 756)
        # All current.
        self.assertEqual(
            NodeVersion.objects.filter(effective_to__isnull=True).count(),
            756,
        )

    def test_amendment_closes_prior_version_and_opens_new_one(self):
        self._ingest(self.payload_bytes, self.parsed)

        # Mutate section 1.1's body, re-ingest.
        amended = json.loads(self.payload_bytes.decode("utf-8"))
        amended["samples"][0]["sections"][0]["body_text"] = (
            "AMENDED " + amended["samples"][0]["sections"][0]["body_text"]
        )
        amended_bytes = json.dumps(amended).encode("utf-8")
        amended_parsed = parse_probe_json(amended)

        self._ingest(amended_bytes, amended_parsed)

        node_1_1 = Node.objects.get(source=self.source, path="1.1")
        versions = list(node_1_1.versions.order_by("id"))
        self.assertEqual(len(versions), 2)
        prior, current = versions
        self.assertIsNotNone(prior.effective_to, "prior version not closed")
        self.assertIsNone(current.effective_to, "current version not open-ended")
        self.assertNotEqual(prior.content_hash, current.content_hash)

    def test_citation_resolves_after_ingest(self):
        self._ingest(self.payload_bytes, self.parsed)

        cit = parse_citation("Iowa Code § 1.1")
        node = resolve_citation(cit, self.source)
        self.assertIsNotNone(node)
        self.assertEqual(node.path, "1.1")
        self.assertEqual(node.heading, "State boundaries")

    def test_chapter_only_citation_resolves_to_chapter_node(self):
        self._ingest(self.payload_bytes, self.parsed)
        cit = parse_citation("Iowa Code ch. 232")
        node = resolve_citation(cit, self.source)
        self.assertIsNotNone(node)
        self.assertEqual(node.path, "232")
        self.assertEqual(node.node_type.key, "chapter")
