"""Embedding job behavior — backfill, idempotency, batching."""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, tag

from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    Source,
)
from apps.corpus.services.embeddings import pending_versions, run_embedding_job
from apps.corpus.services.voyage import FakeEmbeddingClient


@tag("postgres")
class EmbeddingJobTests(TestCase):
    def setUp(self):
        j = Jurisdiction.objects.create(slug="j", name="J", abbreviation="J")
        self.source = Source.objects.create(
            jurisdiction=j, slug="s", name="S", citation_abbreviation="S"
        )
        self.nt = NodeType.objects.create(
            source=self.source, key="section", label_singular="Section", level=1
        )

    def _make_version(self, ordinal: str, body: str) -> NodeVersion:
        node = Node.objects.create(
            source=self.source,
            node_type=self.nt,
            ordinal=ordinal,
            path=f"1.{ordinal}",
            heading=f"H {ordinal}",
        )
        return NodeVersion.objects.create(
            node=node,
            body_text=body,
            effective_from=dt.date(2026, 1, 1),
            content_hash=f"hash-{ordinal}",
        )

    def test_pending_versions_excludes_already_embedded(self):
        a = self._make_version("1", "alpha")
        b = self._make_version("2", "beta")
        b.embedding_source_hash = b.content_hash
        b.save(update_fields=["embedding_source_hash"])
        ids = set(pending_versions().values_list("id", flat=True))
        self.assertEqual(ids, {a.id})

    def test_run_embedding_job_writes_back_vector_and_hash(self):
        v = self._make_version("1", "alpha body")
        result = run_embedding_job(client=FakeEmbeddingClient(), batch_size=8)
        self.assertEqual(result.embedded, 1)
        v.refresh_from_db()
        self.assertEqual(v.embedding_source_hash, v.content_hash)
        self.assertIsNotNone(v.embedding)
        self.assertEqual(len(list(v.embedding)), 1024)

    def test_idempotent_second_run_does_nothing(self):
        self._make_version("1", "alpha")
        self._make_version("2", "beta")
        run_embedding_job(client=FakeEmbeddingClient())
        result = run_embedding_job(client=FakeEmbeddingClient())
        self.assertEqual(result.embedded, 0)

    def test_amended_content_re_embeds_only_that_row(self):
        a = self._make_version("1", "alpha")
        b = self._make_version("2", "beta")
        run_embedding_job(client=FakeEmbeddingClient())

        a.body_text = "completely new text"
        a.content_hash = "new-hash-a"
        a.save(update_fields=["body_text", "content_hash"])

        result = run_embedding_job(client=FakeEmbeddingClient())
        self.assertEqual(result.embedded, 1)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.embedding_source_hash, "new-hash-a")
        self.assertEqual(b.embedding_source_hash, "hash-2")

    def test_batch_size_smaller_than_pending_count(self):
        for i in range(5):
            self._make_version(str(i + 1), f"body-{i}")
        result = run_embedding_job(client=FakeEmbeddingClient(), batch_size=2)
        self.assertEqual(result.embedded, 5)
