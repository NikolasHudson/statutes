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

from apps.corpus.models import NodeVersion

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


def pending_versions() -> QuerySet[NodeVersion]:
    """NodeVersions whose embedding is missing or stale."""
    return NodeVersion.objects.exclude(content_hash=F("embedding_source_hash"))


def run_embedding_job(
    *,
    client: EmbeddingClient | None = None,
    batch_size: int = 64,
    limit: int | None = None,
) -> EmbeddingRunResult:
    """Embed every pending NodeVersion. Idempotent: re-running picks up only
    rows whose content has changed since the last run."""

    client = client or default_client()
    qs = pending_versions().order_by("id")
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
