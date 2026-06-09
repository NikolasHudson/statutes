"""Tests for the PR5 optional query rewrite (``apps.corpus.services.query_rewrite``)
and its flag-gated hook in ``retrieve_context``.

All tests inject a fake rewriter or patch the default so none hit the OpenAI API.
The contract under test is the safety one: rewrite is a passthrough on any
failure, and the hook only fires behind ``RAG_QUERY_REWRITE``.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.corpus.services.query_rewrite import (
    OpenAIQueryRewriter,
    _parse_query,
    rewrite_query,
)
from apps.corpus.services.retrieval import retrieve_context


class _FakeRewriter:
    def __init__(self, out: str):
        self.out = out
        self.calls: list[str] = []

    def rewrite(self, query: str) -> str:
        self.calls.append(query)
        return self.out


class RewriteQueryTests(SimpleTestCase):
    def test_uses_the_rewriter_output(self):
        self.assertEqual(
            rewrite_query("vague q", rewriter=_FakeRewriter("sharp legal query")),
            "sharp legal query",
        )

    def test_empty_rewrite_falls_back_to_original(self):
        self.assertEqual(rewrite_query("orig", rewriter=_FakeRewriter("")), "orig")
        self.assertEqual(rewrite_query("orig", rewriter=_FakeRewriter("   ")), "orig")

    def test_runaway_rewrite_falls_back(self):
        self.assertEqual(rewrite_query("orig", rewriter=_FakeRewriter("x" * 500)), "orig")

    def test_raising_rewriter_falls_back(self):
        class _Boom:
            def rewrite(self, q):
                raise RuntimeError("boom")

        self.assertEqual(rewrite_query("orig", rewriter=_Boom()), "orig")

    def test_empty_query_is_passthrough(self):
        self.assertEqual(rewrite_query("   ", rewriter=_FakeRewriter("x")), "   ")

    def test_no_rewriter_available_returns_original(self):
        with mock.patch(
            "apps.corpus.services.query_rewrite.default_query_rewriter",
            return_value=None,
        ):
            self.assertEqual(rewrite_query("orig"), "orig")


class ParseQueryTests(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(_parse_query('{"query": "abc def"}'), "abc def")

    def test_malformed_json(self):
        self.assertEqual(_parse_query("not json"), "")

    def test_missing_key(self):
        self.assertEqual(_parse_query('{"other": 1}'), "")

    def test_non_object(self):
        self.assertEqual(_parse_query('["a", "b"]'), "")


@override_settings(OPENAI_API_KEY="")
class OpenAIRewriterTests(SimpleTestCase):
    # OPENAI_API_KEY blanked so api_key="" doesn't fall back to a real env key and
    # hit the network — these assert the no-key / empty-input short-circuits.
    def test_no_key_returns_empty_without_calling_api(self):
        self.assertEqual(OpenAIQueryRewriter(api_key="").rewrite("q"), "")

    def test_empty_query_returns_empty(self):
        self.assertEqual(OpenAIQueryRewriter(api_key="sk-fake").rewrite("  "), "")


class RetrieveContextHookTests(SimpleTestCase):
    """The flag-gated hook: with RAG_QUERY_REWRITE on, retrieval sees the rewrite
    but the returned context keeps the ORIGINAL query for display."""

    def _capture_hybrid(self, captured):
        def fake(query, **kwargs):
            captured["query"] = query
            return []  # empty → retrieve_context returns early

        return fake

    @override_settings(RAG_QUERY_REWRITE=True)
    def test_hook_rewrites_before_search(self):
        captured: dict = {}
        with mock.patch(
            "apps.corpus.services.retrieval.hybrid_search",
            side_effect=self._capture_hybrid(captured),
        ), mock.patch(
            "apps.corpus.services.query_rewrite.default_query_rewriter",
            return_value=_FakeRewriter("REWRITTEN QUERY"),
        ):
            ctx = retrieve_context("the original lay question")
        self.assertEqual(captured["query"], "REWRITTEN QUERY")
        # Display/return keeps the original question.
        self.assertEqual(ctx.query, "the original lay question")

    @override_settings(RAG_QUERY_REWRITE=False)
    def test_flag_off_searches_the_original(self):
        captured: dict = {}
        with mock.patch(
            "apps.corpus.services.retrieval.hybrid_search",
            side_effect=self._capture_hybrid(captured),
        ), mock.patch(
            "apps.corpus.services.query_rewrite.default_query_rewriter",
            return_value=_FakeRewriter("SHOULD NOT BE USED"),
        ):
            retrieve_context("the original lay question")
        self.assertEqual(captured["query"], "the original lay question")
