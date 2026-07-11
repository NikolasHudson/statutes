"""Relevance reranking for retrieved candidates.

Hybrid search (FTS + trigram + vector, RRF-fused) is good at recall but its
fused score is only an ordering signal — it does not measure how well a
section actually answers the *question*. That's why a natural-language query
can come back with a grab-bag (mediator conflicts, criminal procedure) ranked
alongside the rule that matters.

A reranker is the right-sized fix: one cross-encoder pass that scores each
candidate against the query and keeps the top-k. Cheaper and far more
deterministic than an agent loop.

Mirrors the embeddings / query-expansion pattern: a ``Reranker`` protocol, a
real Voyage-backed implementation, and a deterministic no-op fallback so dev
and tests never hit the network. ``default_reranker()`` picks the real one
only when ``VOYAGE_API_KEY`` is set.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)

VOYAGE_RERANK_2 = "rerank-2"
VOYAGE_RERANK_2_5 = "rerank-2.5"


# Unlike the embedding model, the reranker holds no stored state — it scores
# (query, document) text live at request time — so switching it is safe to flip
# in any environment with no re-embed. Default is rerank-2.5 (the current Voyage
# rerank model; benchmarks/embeddings/ shows it is the single biggest retrieval
# lever); still overridable via VOYAGE_RERANK_MODEL. Prod picks this up on the
# next deploy_on_push — no app-spec/secret change needed.
def _configured_rerank_model() -> str:
    return os.environ.get("VOYAGE_RERANK_MODEL", VOYAGE_RERANK_2_5)


class Reranker(Protocol):
    """Anything that can reorder ``(id, text)`` candidates by relevance to a
    query and return the ids of the best ``top_k``, most relevant first."""

    def rerank(
        self, query: str, candidates: list[tuple[int, str]], *, top_k: int
    ) -> list[int]:
        ...

    def rerank_scored(
        self, query: str, candidates: list[tuple[int, str]], *, top_k: int
    ) -> list[tuple[int, float]]:
        ...


def _fallback_scored(
    candidates: list[tuple[int, str]], top_k: int
) -> list[tuple[int, float]]:
    """Order-preserving scored fallback: keeps the incoming (RRF) order and
    assigns a linearly decaying pseudo-score in (0, 1]. Linear — not 1/rank —
    so a downstream blend against these scores degrades gracefully instead of
    letting any additive signal swamp everything past the first few ranks."""
    kept = candidates[:top_k]
    n = len(kept)
    return [(cid, 1.0 - i / max(n, 1)) for i, (cid, _) in enumerate(kept)]


class NoopReranker:
    """Keeps the incoming order (already RRF-ranked) and just truncates to
    ``top_k``. The default in test/dev — deterministic, no network."""

    def rerank(
        self, query: str, candidates: list[tuple[int, str]], *, top_k: int
    ) -> list[int]:
        return [cid for cid, _ in candidates[:top_k]]

    def rerank_scored(
        self, query: str, candidates: list[tuple[int, str]], *, top_k: int
    ) -> list[tuple[int, float]]:
        return _fallback_scored(candidates, top_k)


@dataclass
class VoyageReranker:
    """Real Voyage cross-encoder rerank. Imports ``voyageai`` lazily so the
    package is not required in environments that don't rerank.

    Never lets a rerank failure block search — on any error we fall back to
    the original RRF order (truncated), exactly like NoopReranker."""

    model: str = field(default_factory=_configured_rerank_model)
    api_key: str | None = None
    max_retries: int = 3

    def rerank(
        self, query: str, candidates: list[tuple[int, str]], *, top_k: int
    ) -> list[int]:
        return [cid for cid, _ in self.rerank_scored(query, candidates, top_k=top_k)]

    def rerank_scored(
        self, query: str, candidates: list[tuple[int, str]], *, top_k: int
    ) -> list[tuple[int, float]]:
        """Like :meth:`rerank` but keeps Voyage's ``relevance_score`` per id
        (roughly [0, 1], higher = more relevant) so callers can blend other
        signals against real relevance instead of bare rank."""
        if not candidates:
            return []
        try:
            import voyageai  # type: ignore

            client = voyageai.Client(
                api_key=self.api_key or os.environ.get("VOYAGE_API_KEY"),
                max_retries=self.max_retries,
            )
            docs = [text for _, text in candidates]
            result = client.rerank(
                query=query,
                documents=docs,
                model=self.model,
                top_k=top_k,
            )
            # Token accounting (lazy import — see semantic_support for why).
            from apps.api.usage import FEATURE_RERANK, emit_usage

            emit_usage(
                FEATURE_RERANK,
                self.model,
                getattr(result, "total_tokens", 0) or 0,
                0,
            )
            # result.results: objects with .index into the docs list, already
            # sorted by descending relevance.
            return [
                (candidates[r.index][0], float(r.relevance_score))
                for r in result.results
            ]
        except Exception:  # noqa: BLE001 — rerank must never break search
            log.exception("rerank failed; falling back to RRF order")
            return _fallback_scored(candidates, top_k)


def default_reranker() -> Reranker:
    if os.environ.get("VOYAGE_API_KEY"):
        return VoyageReranker()
    return NoopReranker()
