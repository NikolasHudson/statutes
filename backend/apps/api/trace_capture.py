"""Turn the chat tool trace into a persisted, searchable ChatTrace row.

Two jobs:

* :func:`derive` — pull the search-quality signals out of the raw tool
  trace (what the model searched, what came back, did it use the best
  hit). Pure and side-effect free so it can be unit-tested against
  synthetic traces.
* :func:`record_chat_trace` — persist a row. **It must never raise.** The
  chat endpoint calls this on its way to ``return``; a logging failure is
  not a user-facing failure, so every error is caught and logged, not
  propagated.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _hit_node(hit: dict) -> dict:
    """A search hit is ``{"node": {...}, ...}``; tolerate a flat shape too
    so a future tool change can't silently break derivation."""
    if not isinstance(hit, dict):
        return {}
    node = hit.get("node")
    return node if isinstance(node, dict) else hit


def _hit_ref(hit: dict) -> dict:
    """The minimal, stable identity of a hit for the denormalized column —
    enough to read the admin without expanding the raw trace."""
    n = _hit_node(hit)
    return {
        "citation": n.get("citation") or "",
        "heading": n.get("heading") or "",
        "path": n.get("path") or "",
    }


def _answer_uses(answer: str, hit: dict) -> bool:
    """Heuristic: did the answer cite this hit? The node ``path`` (e.g.
    ``32:1.10``, ``714.16``) is the load-bearing token a grounded answer
    repeats, so match on that, then fall back to the rendered citation.
    Substring match — good enough for a triage flag, not proof."""
    if not answer:
        return False
    ref = _hit_ref(hit)
    path = ref["path"].strip()
    if path and path in answer:
        return True
    cite = ref["citation"].strip()
    return bool(cite) and cite in answer


def derive(trace: list[dict], answer: str) -> dict[str, Any]:
    """Compute the denormalized search-quality columns from the raw trace.

    ``top_result_used`` is ``None`` when the turn issued no search at all
    (the question may have been a pure citation lookup), ``True`` if the
    answer cited the rank-0 hit of *any* search, else ``False``.
    """
    search_queries: list[str] = []
    retrieved: list[dict] = []
    top_used: bool | None = None

    for call in trace:
        if not isinstance(call, dict):
            continue
        if call.get("name") != "search_statutes":
            continue
        args = call.get("arguments") or {}
        result = call.get("result") or {}
        query = args.get("query") or result.get("query") or ""
        hits = result.get("hits") or []
        search_queries.append(query)
        retrieved.append(
            {"query": query, "hits": [_hit_ref(h) for h in hits]}
        )
        if hits:
            # First search to produce hits flips the flag from "no search"
            # (None) to a concrete answer; any later top-hit hit wins.
            if top_used is None:
                top_used = False
            if _answer_uses(answer, hits[0]):
                top_used = True

    return {
        "search_queries": search_queries,
        "retrieved": retrieved,
        "num_tool_calls": len(trace),
        "num_searches": len(search_queries),
        "top_result_used": top_used,
    }


def _trace_to_dicts(trace) -> list[dict]:
    """The endpoint holds a list of ninja ``ToolCallTrace`` schema objects;
    normalize to plain JSON-able dicts without assuming a pydantic
    version."""
    out: list[dict] = []
    for tc in trace or []:
        if isinstance(tc, dict):
            out.append(tc)
            continue
        out.append(
            {
                "name": getattr(tc, "name", ""),
                "arguments": getattr(tc, "arguments", {}) or {},
                "result": getattr(tc, "result", {}) or {},
            }
        )
    return out


def record_chat_trace(
    *,
    user,
    payload,
    content: str,
    trace,
    model: str,
    latency_ms: int | None = None,
    error: str = "",
) -> None:
    """Persist one chat turn. Never raises.

    Gated by ``settings.CHAT_TRACE_CAPTURE`` so it can be switched off
    (e.g. if storage/privacy ever becomes a concern) without a code
    change.
    """
    if not getattr(settings, "CHAT_TRACE_CAPTURE", True):
        return
    try:
        from apps.api.models import ChatTrace

        raw = _trace_to_dicts(trace)
        derived = derive(raw, content or "")

        # The user's actual ask is the last user-role message.
        question = ""
        for m in reversed(payload.messages):
            if m.role == "user":
                question = m.content
                break

        ChatTrace.objects.create(
            user=user if getattr(user, "pk", None) else None,
            model=model or "",
            source_slug=payload.source_slug or "",
            question=question,
            answer=content or "",
            tool_calls=raw,
            search_queries=derived["search_queries"],
            retrieved=derived["retrieved"],
            num_tool_calls=derived["num_tool_calls"],
            num_searches=derived["num_searches"],
            top_result_used=derived["top_result_used"],
            latency_ms=latency_ms,
            error=error or "",
        )
    except Exception:  # noqa: BLE001 — capture must not break chat
        logger.exception("chat trace capture failed")
