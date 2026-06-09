"""PR5: optional LLM query rewrite (flag-gated, off the hot path by default).

Turns a user's natural-language legal question into a tighter retrieval query —
expand abbreviations, surface terms of art and synonyms, drop conversational
filler — before hybrid search runs, to lift recall on verbose or lay-worded
questions. Reuses the :mod:`semantic_support` OpenAI-call shape (JSON mode, cheap
model default, dependency-injectable).

Safety contract: this can only ever *help* retrieval. ``rewrite_query`` is a
**passthrough** — it returns the original query unchanged — whenever the feature
is disabled, no key is configured, the model errors, or the rewrite comes back
empty or implausibly long. Retrieval never sees a worse query than the baseline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
# A rewrite longer than this (chars) is rejected as runaway / an accidental answer
# rather than a query; we fall back to the original.
_MAX_REWRITE_CHARS = 300


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_PREFIXES)


SYSTEM_PROMPT = (
    "You rewrite a user's legal-research question into a concise search query "
    "for hybrid keyword + semantic retrieval over Iowa statutes, court rules, and "
    "case law. Expand abbreviations, surface the legal terms of art and the few "
    "most useful synonyms, and drop conversational filler and instructions to the "
    "assistant. Keep the SAME legal meaning and jurisdiction — do not narrow or "
    "broaden the question, invent specifics, or answer it. Output a single query "
    "phrase of at most ~30 words. Respond with ONLY a JSON object: "
    '{"query": "..."}.'
)


class QueryRewriter(Protocol):
    def rewrite(self, query: str) -> str:
        ...


@dataclass
class OpenAIQueryRewriter:
    model: str = _DEFAULT_MODEL
    api_key: str | None = None
    max_tokens: int = 120

    def _key(self) -> str:
        return self.api_key or getattr(settings, "OPENAI_API_KEY", "")

    def rewrite(self, query: str) -> str:
        key = self._key()
        if not key or not query.strip():
            return ""
        try:
            from openai import OpenAI
        except ImportError:
            log.warning("openai SDK not installed; query rewrite unavailable")
            return ""
        kwargs: dict = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        }
        if _is_reasoning_model(self.model):
            kwargs["max_completion_tokens"] = max(self.max_tokens, 2000)
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["max_tokens"] = self.max_tokens
            kwargs["temperature"] = 0
        try:
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(**kwargs)
            return _parse_query(resp.choices[0].message.content or "")
        except Exception:  # noqa: BLE001 — a rewrite failure must never break search
            log.exception("query rewrite failed")
            return ""


def _parse_query(text: str) -> str:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("query", "")).strip()


def default_query_rewriter() -> QueryRewriter | None:
    if getattr(settings, "OPENAI_API_KEY", ""):
        return OpenAIQueryRewriter()
    return None


def rewrite_query(query: str, *, rewriter: QueryRewriter | None = None) -> str:
    """Return a retrieval-optimized rewrite of ``query``, or the original query
    unchanged on any failure / no-op. Never raises. The retrieval pipeline calls
    this only when ``settings.RAG_QUERY_REWRITE`` is on; tests inject ``rewriter``."""
    if not query or not query.strip():
        return query
    rw = rewriter or default_query_rewriter()
    if rw is None:
        return query
    try:
        out = rw.rewrite(query)
    except Exception:  # noqa: BLE001
        log.exception("query rewrite raised")
        return query
    out = (out or "").strip()
    if not out or len(out) > _MAX_REWRITE_CHARS:
        return query
    return out
