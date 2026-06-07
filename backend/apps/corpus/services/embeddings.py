"""Embedding job over NodeVersion rows.

The contract: a NodeVersion needs (re)embedding when ``content_hash`` differs
from ``embedding_source_hash``. That covers three cases:

    new row              -> embedding_source_hash == ""
    body amended         -> content_hash changed in writer
    embedding model swap -> caller bumps embedding_source_hash globally

Calls into ``voyage.EmbeddingClient`` so tests can swap in a fake. Writes the
embedding back along with the source hash; failures leave the row untouched
so the next run picks them up.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db.models import F, QuerySet
from django.db.models.functions import Mod

from apps.corpus.models import NodeChunk, NodeVersion

from .voyage import (
    INPUT_TYPE_DOCUMENT,
    EmbeddingClient,
    default_client,
)


log = logging.getLogger(__name__)


@dataclass
class EmbeddingRunResult:
    embedded: int
    skipped: int
    failed: int


def pending_versions(
    source_slugs: list[str] | None = None,
) -> QuerySet[NodeVersion]:
    """NodeVersions whose embedding is missing or stale.

    ``source_slugs`` scopes to one or more ``Source.slug`` values — e.g.
    ``["iowa-code", "iowa-court-rules"]`` to embed the statute/rules corpora
    without sweeping in the (much larger) caselaw corpus."""
    qs = NodeVersion.objects.exclude(content_hash=F("embedding_source_hash"))
    if source_slugs:
        qs = qs.filter(node__source__slug__in=source_slugs)
    return qs


def run_embedding_job(
    *,
    client: EmbeddingClient | None = None,
    batch_size: int = 64,
    limit: int | None = None,
    source_slugs: list[str] | None = None,
) -> EmbeddingRunResult:
    """Embed every pending NodeVersion. Idempotent: re-running picks up only
    rows whose content has changed since the last run.

    ``source_slugs`` restricts the job to the given sources (see
    ``pending_versions``)."""

    client = client or default_client()
    qs = pending_versions(source_slugs).order_by("id")
    if limit is not None:
        qs = qs[:limit]

    embedded = 0
    failed = 0
    skipped = 0

    batch: list[NodeVersion] = []
    for version in qs.iterator(chunk_size=batch_size):
        batch.append(version)
        if len(batch) >= batch_size:
            e, f = _process_batch(batch, client)
            embedded += e
            failed += f
            batch = []
    if batch:
        e, f = _process_batch(batch, client)
        embedded += e
        failed += f

    return EmbeddingRunResult(embedded=embedded, skipped=skipped, failed=failed)


def _process_batch(
    batch: list[NodeVersion], client: EmbeddingClient
) -> tuple[int, int]:
    texts = [_text_for_embedding(v) for v in batch]
    try:
        vectors = client.embed_texts(texts, input_type=INPUT_TYPE_DOCUMENT)
    except Exception:  # noqa: BLE001 — log and continue; next run retries
        log.exception("embedding batch failed (%d rows)", len(batch))
        return (0, len(batch))

    if len(vectors) != len(batch):
        log.error(
            "embedding client returned %d vectors for %d inputs; skipping batch",
            len(vectors),
            len(batch),
        )
        return (0, len(batch))

    for version, vector in zip(batch, vectors):
        version.embedding = vector
        version.embedding_source_hash = version.content_hash
        version.save(update_fields=["embedding", "embedding_source_hash"])

    return (len(batch), 0)


def _text_for_embedding(version: NodeVersion) -> str:
    """Concatenate heading and body so the embedding captures both. Heading
    is short and high-signal so it goes first."""
    heading = version.node.heading or ""
    return f"{heading}\n\n{version.body_text}".strip()


# ---------------------------------------------------------------------------
# Chunk embeddings (NodeChunk) — same contract as the NodeVersion job above,
# but over passage-level chunks. Caselaw is retrieved at chunk granularity; the
# whole-NodeVersion job stays for statutes/rules, which embed whole.
# ---------------------------------------------------------------------------

def pending_chunks(
    source_slugs: list[str] | None = None,
    *,
    shard: int | None = None,
    num_shards: int | None = None,
) -> QuerySet[NodeChunk]:
    """NodeChunks whose embedding is missing or stale (``content_hash`` differs
    from ``embedding_source_hash``). ``source_slugs`` scopes via
    chunk -> version -> node -> source.

    ``shard``/``num_shards`` partition the pending set by ``id % num_shards ==
    shard`` so several embed workers can run in parallel over disjoint rows with
    no coordination (the chunk pk is dense and stable, so the residue classes are
    even-sized and never overlap). Both must be given together."""
    qs = NodeChunk.objects.exclude(content_hash=F("embedding_source_hash"))
    if source_slugs:
        qs = qs.filter(version__node__source__slug__in=source_slugs)
    if num_shards is not None or shard is not None:
        if num_shards is None or shard is None:
            raise ValueError("shard and num_shards must be given together")
        if not (0 <= shard < num_shards):
            raise ValueError(f"shard {shard} out of range for num_shards {num_shards}")
        qs = qs.alias(_shard=Mod(F("id"), num_shards)).filter(_shard=shard)
    return qs


def run_chunk_embedding_job(
    *,
    client: EmbeddingClient | None = None,
    batch_size: int = 64,
    limit: int | None = None,
    source_slugs: list[str] | None = None,
    shard: int | None = None,
    num_shards: int | None = None,
) -> EmbeddingRunResult:
    """Embed every pending NodeChunk. Idempotent on ``content_hash``, mirroring
    ``run_embedding_job``. Chunks average ~750 tokens, so a batch of 64 is
    ~48k tokens — comfortably under voyage's per-request token cap (unlike whole
    opinions, where 64 would overflow it).

    Pass ``shard``/``num_shards`` to process only one id-residue slice, so N
    copies run concurrently for a ~N× speedup (bounded by Voyage's rate limit)."""

    client = client or default_client()
    qs = pending_chunks(source_slugs, shard=shard, num_shards=num_shards).order_by("id")
    if limit is not None:
        qs = qs[:limit]

    embedded = 0
    failed = 0

    batch: list[NodeChunk] = []
    for chunk in qs.iterator(chunk_size=batch_size):
        batch.append(chunk)
        if len(batch) >= batch_size:
            e, f = _process_chunk_batch(batch, client)
            embedded += e
            failed += f
            batch = []
    if batch:
        e, f = _process_chunk_batch(batch, client)
        embedded += e
        failed += f

    return EmbeddingRunResult(embedded=embedded, skipped=0, failed=failed)


def _process_chunk_batch(
    batch: list[NodeChunk], client: EmbeddingClient
) -> tuple[int, int]:
    texts = [_text_for_chunk(c) for c in batch]
    try:
        vectors = client.embed_texts(texts, input_type=INPUT_TYPE_DOCUMENT)
    except Exception:  # noqa: BLE001 — log and continue; next run retries
        log.exception("chunk embedding batch failed (%d rows)", len(batch))
        return (0, len(batch))

    if len(vectors) != len(batch):
        log.error(
            "embedding client returned %d vectors for %d chunk inputs; skipping batch",
            len(vectors),
            len(batch),
        )
        return (0, len(batch))

    for chunk, vector in zip(batch, vectors):
        chunk.embedding = vector
        chunk.embedding_source_hash = chunk.content_hash
        chunk.save(update_fields=["embedding", "embedding_source_hash"])

    return (len(batch), 0)


def _text_for_chunk(chunk: NodeChunk) -> str:
    """Reconstruct the exact text that ``build_chunks`` hashed into
    ``content_hash``: the case-meta header then the chunk body. Keeping this in
    lockstep with the chunker is what makes re-embed idempotency correct."""
    if chunk.context_header:
        return f"{chunk.context_header}\n\n{chunk.body_text}".strip()
    return chunk.body_text
