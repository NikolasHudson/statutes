"""Embedding job behavior — backfill, idempotency, batching."""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, tag

from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeChunk,
    NodeType,
    NodeVersion,
    Source,
)
from apps.corpus.services.embeddings import (
    pending_chunks,
    pending_versions,
    run_chunk_embedding_job,
    run_embedding_job,
)
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


@tag("postgres")
class ChunkEmbeddingJobTests(TestCase):
    def setUp(self):
        j = Jurisdiction.objects.create(slug="j", name="J", abbreviation="J")
        self.source = Source.objects.create(
            jurisdiction=j, slug="s", name="S", citation_abbreviation="S"
        )
        self.nt = NodeType.objects.create(
            source=self.source, key="section", label_singular="Section", level=1
        )
        node = Node.objects.create(
            source=self.source, node_type=self.nt, ordinal="1", path="1.1", heading="H"
        )
        self.version = NodeVersion.objects.create(
            node=node, body_text="body", effective_from=dt.date(2026, 1, 1), content_hash="h"
        )

    def _make_chunk(self, ordinal: int, body: str) -> NodeChunk:
        return NodeChunk.objects.create(
            version=self.version,
            ordinal=ordinal,
            body_text=body,
            context_header="Case (Court 2020) — Opinion",
            char_start=0,
            char_end=len(body),
            token_count=len(body.split()),
            content_hash=f"chash-{ordinal}",
        )

    def test_pending_chunks_excludes_already_embedded(self):
        a = self._make_chunk(0, "alpha")
        b = self._make_chunk(1, "beta")
        b.embedding_source_hash = b.content_hash
        b.save(update_fields=["embedding_source_hash"])
        self.assertEqual(set(pending_chunks().values_list("id", flat=True)), {a.id})

    def test_run_chunk_job_writes_back_vector_and_hash(self):
        c = self._make_chunk(0, "alpha body")
        result = run_chunk_embedding_job(client=FakeEmbeddingClient(), batch_size=8)
        self.assertEqual(result.embedded, 1)
        c.refresh_from_db()
        self.assertEqual(c.embedding_source_hash, c.content_hash)
        self.assertIsNotNone(c.embedding)
        self.assertEqual(len(list(c.embedding)), 1024)

    def test_chunk_job_is_idempotent(self):
        self._make_chunk(0, "alpha")
        self._make_chunk(1, "beta")
        run_chunk_embedding_job(client=FakeEmbeddingClient())
        result = run_chunk_embedding_job(client=FakeEmbeddingClient())
        self.assertEqual(result.embedded, 0)

    def test_chunk_job_batches(self):
        for i in range(5):
            self._make_chunk(i, f"body-{i}")
        result = run_chunk_embedding_job(client=FakeEmbeddingClient(), batch_size=2)
        self.assertEqual(result.embedded, 5)

    def test_shards_partition_pending_without_overlap_or_gaps(self):
        ids = {self._make_chunk(i, f"body-{i}").id for i in range(11)}
        n = 4
        seen = []
        for s in range(n):
            seen += list(pending_chunks(shard=s, num_shards=n).values_list("id", flat=True))
        # Every pending chunk handled exactly once across the shards.
        self.assertEqual(sorted(seen), sorted(ids))
        self.assertEqual(len(seen), len(set(seen)))

    def test_sharded_run_embeds_only_its_slice(self):
        chunks = [self._make_chunk(i, f"body-{i}") for i in range(8)]
        run_chunk_embedding_job(client=FakeEmbeddingClient(), shard=0, num_shards=4)
        for c in chunks:
            c.refresh_from_db()
            embedded = c.embedding is not None
            self.assertEqual(embedded, c.id % 4 == 0)
