"""Tests for live chat trace capture (apps/api/trace_capture + ChatTrace).

Two concerns:

* the derivation logic that turns a raw tool trace into the search-quality
  signals we filter on — especially ``top_result_used``, the flag that
  answers "did it actually use the best retrieved hit?"; and
* the capture is wired into the endpoint, persists a row, respects the
  off switch, and can never break a chat.
"""

from __future__ import annotations

import json
from unittest import mock

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.api.models import ChatTrace
from apps.api.trace_capture import derive, record_chat_trace

from ._factories import make_user


def _search_call(query: str, hits: list[dict]) -> dict:
    return {
        "name": "search_statutes",
        "arguments": {"query": query},
        "result": {"query": query, "hits": hits},
    }


def _hit(path: str, heading: str = "", citation: str = "") -> dict:
    return {"node": {"path": path, "heading": heading, "citation": citation}}


class DeriveTests(SimpleTestCase):
    def test_no_search_leaves_top_result_used_none(self):
        trace = [{"name": "lookup_citation", "arguments": {}, "result": {}}]
        d = derive(trace, answer="See Iowa Ct. R. 32:1.10.")
        self.assertIsNone(d["top_result_used"])
        self.assertEqual(d["num_searches"], 0)
        self.assertEqual(d["num_tool_calls"], 1)

    def test_top_hit_cited_sets_true(self):
        trace = [_search_call("lawyer conflict screening", [
            _hit("32:1.10", "Imputation of conflicts"),
            _hit("32:1.7", "Conflict of interest"),
        ])]
        d = derive(trace, answer="Under Iowa Ct. R. 32:1.10, screening …")
        self.assertTrue(d["top_result_used"])
        self.assertEqual(d["search_queries"], ["lawyer conflict screening"])
        self.assertEqual(d["retrieved"][0]["hits"][0]["path"], "32:1.10")

    def test_only_lower_hit_cited_sets_false(self):
        # The reranker's #1 was 32:1.7 but the answer grounded on 32:1.10:
        # retrieval and the answer disagree — the symptom we want to catch.
        trace = [_search_call("conflict", [
            _hit("32:1.7", "Conflict of interest"),
            _hit("32:1.10", "Imputation of conflicts"),
        ])]
        d = derive(trace, answer="Iowa Ct. R. 32:1.10 controls here.")
        self.assertFalse(d["top_result_used"])

    def test_any_search_with_top_hit_used_wins(self):
        trace = [
            _search_call("first bad query", [_hit("999.1", "Unrelated")]),
            _search_call("better query", [_hit("32:1.10", "Imputation")]),
        ]
        d = derive(trace, answer="The rule is 32:1.10.")
        self.assertTrue(d["top_result_used"])
        self.assertEqual(d["num_searches"], 2)

    def test_zero_hits_search_counts_but_stays_false(self):
        d = derive([_search_call("nonsense", [])], answer="No rule found.")
        self.assertFalse(d["top_result_used"])
        self.assertEqual(d["retrieved"][0]["hits"], [])

    def test_citation_match_falls_back_when_no_path(self):
        trace = [_search_call("q", [
            {"node": {"path": "", "citation": "Iowa Ct. R. 32:1.10"}},
        ])]
        d = derive(trace, answer="Per Iowa Ct. R. 32:1.10 you must screen.")
        self.assertTrue(d["top_result_used"])


class _FakeMsg:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _FakeCompletion:
    model = "gpt-4o-mini"

    def __init__(self, content="Grounded answer."):
        self.choices = [type("C", (), {"message": _FakeMsg(content)})()]


def _fake_openai(content="Grounded answer."):
    client = mock.MagicMock()
    client.chat.completions.create.return_value = _FakeCompletion(content)
    return mock.patch("openai.OpenAI", return_value=client)


def _post(client: Client, payload: dict):
    return client.post(
        "/api/chat", data=json.dumps(payload), content_type="application/json"
    )


@override_settings(OPENAI_API_KEY="sk-test", CHAT_TRACE_CAPTURE=True)
class CaptureWiringTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(email="lawyer@example.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_successful_chat_writes_a_row(self):
        with _fake_openai("Here is the answer."):
            resp = _post(self.client, {
                "messages": [{"role": "user", "content": "what is consumer fraud?"}],
                "source_slug": "iowa-code",
            })
        self.assertEqual(resp.status_code, 200)
        row = ChatTrace.objects.get()
        self.assertEqual(row.user, self.user)
        self.assertEqual(row.question, "what is consumer fraud?")
        self.assertEqual(row.answer, "Here is the answer.")
        self.assertEqual(row.source_slug, "iowa-code")
        self.assertEqual(row.num_searches, 0)
        self.assertIsNone(row.top_result_used)
        self.assertIsNotNone(row.latency_ms)

    @override_settings(CHAT_TRACE_CAPTURE=False)
    def test_off_switch_writes_nothing(self):
        with _fake_openai():
            _post(self.client, {"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(ChatTrace.objects.count(), 0)

    def test_capture_failure_never_breaks_the_chat(self):
        with _fake_openai("still answered"), mock.patch(
            "apps.api.models.ChatTrace.objects"
        ) as objs:
            objs.create.side_effect = RuntimeError("db down")
            resp = _post(
                self.client, {"messages": [{"role": "user", "content": "hi"}]}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["content"], "still answered")

    def test_openai_failure_records_error_row(self):
        client = mock.MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("401 bad key")
        with mock.patch("openai.OpenAI", return_value=client):
            resp = _post(
                self.client, {"messages": [{"role": "user", "content": "hi"}]}
            )
        self.assertEqual(resp.status_code, 502)
        row = ChatTrace.objects.get()
        self.assertIn("OpenAI call failed", row.error)
        self.assertEqual(row.answer, "")
