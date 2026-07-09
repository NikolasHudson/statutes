"""Query-embedding cache.

Every ``use_vector=True`` search pays a synchronous Voyage round-trip to embed
the query — the latency (and unmetered spend) that originally kept vector
search off the public browse endpoint. Query text repeats heavily (re-running
a search, paging, the eval harnesses), and embeddings are deterministic for a
given model, so a cache is pure win: same vector, no wire call.

Backed by the default Django cache — Redis in prod (``REDIS_URL``), LocMem in
dev/tests — keyed by model + normalized text so a model swap can never serve
stale vectors. The cache must never break search: any cache error falls
through to a live embed.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.cache import cache

from .voyage import INPUT_TYPE_QUERY, EmbeddingClient, default_client

logger = logging.getLogger(__name__)

QUERY_EMBED_CACHE_TTL = 14 * 86400  # seconds; queries repeat within days


def _cache_key(model: str, text: str) -> str:
    normalized = " ".join(text.split()).lower()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    return f"qemb:{model}:{digest}"


def embed_query_cached(
    text: str, *, client: EmbeddingClient | None = None
) -> list[float]:
    """Embed ``text`` as a query, via the cache when possible."""
    active = client or default_client()
    key = _cache_key(active.model, text)

    try:
        hit = cache.get(key)
    except Exception:  # cache down ≠ search down
        logger.warning("query-embedding cache read failed", exc_info=True)
        hit = None
    if hit is not None:
        return hit

    vector = active.embed_texts([text], input_type=INPUT_TYPE_QUERY)[0]

    try:
        cache.set(key, vector, timeout=QUERY_EMBED_CACHE_TTL)
    except Exception:
        logger.warning("query-embedding cache write failed", exc_info=True)
    return vector
