"""Thin Voyage AI embedding client.

Why thin: the rest of the codebase only needs ``embed_texts(list[str]) -> list[list[float]]``
— anything fancier (retries, streaming, batching headers) belongs in the
embedding job, not the wire layer.

In tests, override ``DEFAULT_CLIENT`` (or pass a stub into the embedding job)
so we never hit the network. The only state that matters is the embedding
dimension; we hard-code 1024 to match the ``NodeVersion.embedding`` column.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


VOYAGE_LAW_2 = "voyage-law-2"
EMBEDDING_DIM = 1024
INPUT_TYPE_DOCUMENT = "document"
INPUT_TYPE_QUERY = "query"


class EmbeddingClient(Protocol):
    """Anything we accept as an embedder. Lets tests inject fakes without
    monkey-patching the real client."""

    model: str

    def embed_texts(
        self, texts: list[str], *, input_type: str = INPUT_TYPE_DOCUMENT
    ) -> list[list[float]]:
        ...


@dataclass
class VoyageClient:
    """Real Voyage client. Imports ``voyageai`` lazily so the package does not
    explode in environments that haven't installed it (e.g. CI for unrelated
    test suites).

    ``max_retries`` is forwarded to the SDK, which uses tenacity exponential
    jitter (1s..16s) to retry on RateLimitError / ServiceUnavailableError /
    Timeout. The default of 0 means a single 429 propagates — for bulk jobs
    against published rate limits, set this to something like 5."""

    model: str = VOYAGE_LAW_2
    api_key: str | None = None
    max_retries: int = 5

    def embed_texts(
        self, texts: list[str], *, input_type: str = INPUT_TYPE_DOCUMENT
    ) -> list[list[float]]:
        import voyageai  # type: ignore

        client = voyageai.Client(
            api_key=self.api_key or os.environ.get("VOYAGE_API_KEY"),
            max_retries=self.max_retries,
        )
        result = client.embed(texts, model=self.model, input_type=input_type)
        return [list(vec) for vec in result.embeddings]


@dataclass
class FakeEmbeddingClient:
    """Deterministic embedder for tests and local dev without an API key.

    Hashes the input text into a 1024-dim float vector. The output is
    L2-normalized so cosine distance is meaningful, and identical inputs
    produce identical vectors so equality checks work."""

    model: str = "fake-deterministic-1024"
    dim: int = EMBEDDING_DIM

    def embed_texts(
        self, texts: list[str], *, input_type: str = INPUT_TYPE_DOCUMENT
    ) -> list[list[float]]:
        return [_deterministic_vector(t, self.dim) for t in texts]


def _deterministic_vector(text: str, dim: int) -> list[float]:
    import hashlib
    import math
    import struct

    out: list[float] = []
    counter = 0
    while len(out) < dim:
        digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        for i in range(0, len(digest), 4):
            (val,) = struct.unpack("<I", digest[i : i + 4])
            out.append((val / 0xFFFFFFFF) * 2.0 - 1.0)
            if len(out) >= dim:
                break
        counter += 1
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def default_client() -> EmbeddingClient:
    """Return the real Voyage client if VOYAGE_API_KEY is set, otherwise the
    deterministic fake. Production deploys must set the key — the fake is for
    local dev and tests only."""
    if os.environ.get("VOYAGE_API_KEY"):
        return VoyageClient()
    return FakeEmbeddingClient()
