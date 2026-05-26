"""Persistent capture of chat search/grounding traces.

The chat endpoint already builds a full ``trace`` of every tool call (the
search query the model issued, the raw ranked results, and the final
answer) so a human can verify grounding *in the moment*. That trace was
ephemeral — it lived only in the HTTP response. ``ChatTrace`` writes it to
the database so we can answer the standing question "is the assistant
calling the best information?" by inspecting real traffic over time, not
just one request.

The denormalized columns (``search_queries``, ``retrieved``,
``num_searches``, ``top_result_used``) are derived from the raw trace at
write time by ``apps.api.trace_capture``. They exist so the admin can
*filter* on search behaviour ("show chats that searched 5+ times" =
the model floundering; "show chats where the top hit was never cited" =
retrieval/grounding mismatch) without re-parsing JSON per row.

This is a write-mostly audit log: never edited by hand, browsed read-only
in the admin. Capturing it must never break a chat, so the writer
(:func:`apps.api.trace_capture.record_chat_trace`) swallows its own
errors — a logging failure is not a user-facing failure.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ChatTrace(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # SET_NULL, not CASCADE: deleting a user must not shred the search-
    # quality history we use to tune retrieval.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_traces",
    )

    model = models.CharField(max_length=64, blank=True)
    # Corpus scope forced onto every search this turn (e.g.
    # "iowa-court-rules"); blank = all sources.
    source_slug = models.CharField(max_length=64, blank=True)

    # The user's actual ask — the last user message. This is what the
    # model had to turn into search queries; comparing the two is the
    # whole point of the log.
    question = models.TextField(blank=True)
    answer = models.TextField(blank=True)

    # The raw, untouched tool trace exactly as returned to the client:
    # [{"name", "arguments", "result"}, ...]. Source of truth; the columns
    # below are derived from it and exist only for filtering/triage.
    tool_calls = models.JSONField(default=list)

    # Every query string the model passed to search_statutes, in order.
    # Divergence from `question` (over-broad, wrong terms, too many tries)
    # is the most common search-quality failure.
    search_queries = models.JSONField(default=list)
    # Per search: the ranked hits it returned —
    # [{"query", "hits": [{"citation", "heading", "path"}, ...]}, ...].
    retrieved = models.JSONField(default=list)

    num_tool_calls = models.PositiveIntegerField(default=0)
    num_searches = models.PositiveIntegerField(default=0)

    # Heuristic: did the final answer cite the #1 reranked hit of at least
    # one search? Null when the turn issued no search. False here usually
    # means either retrieval put the right section below rank 0, or the
    # model grounded on a weaker hit / its own memory — exactly the
    # "not calling the best information" symptom. Heuristic, not proof:
    # triage signal, read the trace to confirm.
    top_result_used = models.BooleanField(null=True, blank=True)

    # Wall-clock for the whole tool loop, milliseconds.
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    # Populated when the turn failed (e.g. the OpenAI call 502'd). A failed
    # turn is often the most informative one to inspect.
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("-created_at",)),
            models.Index(fields=("top_result_used",)),
            models.Index(fields=("source_slug",)),
        ]

    def __str__(self) -> str:
        q = (self.question or "").strip().replace("\n", " ")
        return f"{self.created_at:%Y-%m-%d %H:%M} · {q[:60]}"
