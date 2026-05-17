"""Query expansion using a small LLM.

Attorneys ask in natural language ("can a tenant deduct repair costs from
rent?"); the corpus is written in statutory dialect ("withholding rent"
"set-off" "self-help"). A cheap LLM call bridges the gap by adding Iowa
legal terms-of-art the query doesn't already contain.

Tests inject ``QueryExpander`` directly so we never touch the network. The
real client is wired in via ``default_expander()`` only when ANTHROPIC_API_KEY
is set; without it we no-op the expansion (search still works, just less
recall on natural-language queries)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol


log = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You expand legal-search queries with Iowa statutory terms-of-art so a "
    "keyword search engine can find the right Iowa Code sections. Add 3-6 "
    "synonyms or formal-statutory phrasings the user did not already use. "
    "Keep the original query verbatim. Return ONLY the expanded query as a "
    "single line of space-separated terms — no preamble, no quotes, no "
    "punctuation other than what is in the terms themselves."
)


class QueryExpander(Protocol):
    def expand(self, query: str) -> str:
        ...


@dataclass
class NoopExpander:
    """Returns the query unchanged. The default in test/dev environments."""

    def expand(self, query: str) -> str:
        return query


@dataclass
class AnthropicExpander:
    """Expands queries with a Haiku call. Cheap and fast — Haiku 4.5 is
    appropriate; Sonnet is overkill for this. We use a hard 80-token cap so
    a runaway model doesn't blow the budget."""

    model: str = "claude-haiku-4-5-20251001"
    api_key: str | None = None
    max_tokens: int = 80

    def expand(self, query: str) -> str:
        try:
            import anthropic  # type: ignore
        except ImportError:
            log.warning("anthropic SDK not installed; falling back to noop expansion")
            return query
        try:
            client = anthropic.Anthropic(
                api_key=self.api_key or os.environ.get("ANTHROPIC_API_KEY")
            )
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": query}],
            )
            text = "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            ).strip()
            return text or query
        except Exception:  # noqa: BLE001 — never let expansion failure block search
            log.exception("query expansion failed; falling back to original query")
            return query


def default_expander() -> QueryExpander:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicExpander()
    return NoopExpander()
