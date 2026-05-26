"""Read-only admin for ChatTrace — the search-quality inspection surface.

This is an audit log, never edited by hand: add/change/delete are all
disabled. The value is the per-chat detail view, which lays the trace out
the way you actually debug "it's not calling the best information":

    the user's question
      → each search query the model rewrote it into
        → the ranked hits that query returned (★ = cited in the answer)
      → the final answer

so a mismatch (right section retrieved but never cited, or a bad query
rewrite, or 6 flailing searches) is visible at a glance instead of buried
in a JSON blob.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import ChatTrace
from .trace_capture import _answer_uses


@admin.register(ChatTrace)
class ChatTraceAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "short_question",
        "num_searches",
        "num_tool_calls",
        "top_result_used",
        "source_slug",
        "has_error",
    )
    list_filter = (
        "top_result_used",
        "source_slug",
        "model",
        "created_at",
    )
    search_fields = ("question", "answer")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    readonly_fields = (
        "created_at",
        "user",
        "model",
        "source_slug",
        "latency_ms",
        "num_searches",
        "num_tool_calls",
        "top_result_used",
        "question",
        "trace_view",
        "answer",
        "error",
        "raw_tool_calls",
    )
    fields = readonly_fields

    # A log is captured, not authored: keep the admin strictly view-only.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Allow purging old rows (retention/privacy) but nothing else.
        return True

    @admin.display(description="Question")
    def short_question(self, obj: ChatTrace) -> str:
        q = (obj.question or "").strip().replace("\n", " ")
        return (q[:80] + "…") if len(q) > 80 else q

    @admin.display(boolean=True, description="Error")
    def has_error(self, obj: ChatTrace) -> bool:
        return bool(obj.error)

    @admin.display(description="Search trace (★ = hit cited in answer)")
    def trace_view(self, obj: ChatTrace):
        """Render every search call: the query, then its ranked hits with
        a ★ on any hit whose path/citation appears in the final answer.
        Rank 0 is highlighted because that is the one the reranker thought
        was best — if it's never starred, retrieval and the answer
        disagree."""
        answer = obj.answer or ""
        blocks = []
        searches = [
            c for c in (obj.tool_calls or [])
            if isinstance(c, dict) and c.get("name") == "search_statutes"
        ]
        if not searches:
            return mark_safe("<em>No search_statutes calls this turn.</em>")

        for n, call in enumerate(searches, 1):
            args = call.get("arguments") or {}
            result = call.get("result") or {}
            query = args.get("query") or result.get("query") or "(none)"
            hits = result.get("hits") or []
            rows = []
            for rank, hit in enumerate(hits):
                node = hit.get("node") if isinstance(hit, dict) else None
                node = node if isinstance(node, dict) else (hit or {})
                used = _answer_uses(answer, hit if isinstance(hit, dict) else {})
                star = "★" if used else "&nbsp;"
                top = "background:#fffbe6;font-weight:600;" if rank == 0 else ""
                rows.append(format_html(
                    '<tr style="{}"><td style="padding:2px 8px;color:#888">'
                    "{}</td><td style='padding:2px 8px;color:#c0392b'>{}</td>"
                    '<td style="padding:2px 8px">{}</td>'
                    '<td style="padding:2px 8px">{}</td></tr>',
                    mark_safe(top),
                    rank,
                    mark_safe(star),
                    node.get("citation") or node.get("path") or "?",
                    node.get("heading") or "",
                ))
            table = (
                format_html(
                    '<table style="border-collapse:collapse;margin:4px 0 '
                    '14px 16px;font-size:12px">{}</table>',
                    format_html_join("", "{}", ((r,) for r in rows)),
                )
                if rows
                else mark_safe(
                    '<div style="margin:4px 0 14px 16px;color:#c0392b">'
                    "0 hits returned</div>"
                )
            )
            blocks.append(format_html(
                '<div style="margin-bottom:6px"><strong>Search {}:</strong> '
                '<code>{}</code></div>{}',
                n, query, table,
            ))
        return format_html(
            '<div style="max-width:900px">{}</div>',
            format_html_join("", "{}", ((b,) for b in blocks)),
        )

    @admin.display(description="Raw tool_calls (source of truth)")
    def raw_tool_calls(self, obj: ChatTrace):
        import json

        return format_html(
            '<pre style="max-height:500px;overflow:auto;font-size:11px;'
            'background:#f6f8fa;padding:10px">{}</pre>',
            json.dumps(obj.tool_calls, indent=2, default=str),
        )
