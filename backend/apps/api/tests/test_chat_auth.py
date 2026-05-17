"""Auth + spend-gate tests for /api/chat.

The endpoint no longer takes a BYO key — it spends our server
``OPENAI_API_KEY``. These guard the three things that stand between a
logged-in user and an unbounded OpenAI bill: login is required, the model
is allowlisted, and both the per-user daily cap and the global monthly
ceiling actually reject once tripped.
"""

from __future__ import annotations

import json
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from ._factories import make_user


def _post(client: Client, payload: dict):
    return client.post(
        "/api/chat", data=json.dumps(payload), content_type="application/json"
    )


class _FakeMessage:
    content = "Grounded answer."
    tool_calls = None


class _FakeCompletion:
    model = "gpt-4o-mini"
    choices = [type("C", (), {"message": _FakeMessage()})()]


def _fake_openai():
    """A stand-in OpenAI client whose first completion has no tool calls,
    so the chat loop returns immediately without any network I/O."""
    client = mock.MagicMock()
    client.chat.completions.create.return_value = _FakeCompletion()
    return mock.patch("openai.OpenAI", return_value=client)


@override_settings(OPENAI_API_KEY="sk-test")
class ChatAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(email="lawyer@example.com")
        self.client = Client()

    def test_anonymous_is_rejected(self):
        resp = _post(self.client, {"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status_code, 401)

    def test_logged_in_happy_path(self):
        self.client.force_login(self.user)
        with _fake_openai():
            resp = _post(
                self.client, {"messages": [{"role": "user", "content": "hi"}]}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["content"], "Grounded answer.")

    def test_unknown_model_rejected_before_spend(self):
        self.client.force_login(self.user)
        resp = _post(
            self.client,
            {"messages": [{"role": "user", "content": "hi"}], "model": "gpt-5-ultra"},
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(OPENAI_API_KEY="")
    def test_unconfigured_key_is_503_not_500(self):
        self.client.force_login(self.user)
        resp = _post(self.client, {"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status_code, 503)

    @override_settings(CHAT_DAILY_USER_LIMIT=2)
    def test_per_user_daily_cap_trips(self):
        self.client.force_login(self.user)
        with _fake_openai():
            for _ in range(2):
                self.assertEqual(
                    _post(
                        self.client,
                        {"messages": [{"role": "user", "content": "q"}]},
                    ).status_code,
                    200,
                )
            blocked = _post(
                self.client, {"messages": [{"role": "user", "content": "q"}]}
            )
        self.assertEqual(blocked.status_code, 429)

    @override_settings(CHAT_MONTHLY_GLOBAL_LIMIT=1)
    def test_global_monthly_ceiling_trips_for_everyone(self):
        self.client.force_login(self.user)
        with _fake_openai():
            self.assertEqual(
                _post(
                    self.client, {"messages": [{"role": "user", "content": "q"}]}
                ).status_code,
                200,
            )
            # A different user is still blocked — the ceiling is global.
            other = make_user(email="other@example.com")
            self.client.force_login(other)
            blocked = _post(
                self.client, {"messages": [{"role": "user", "content": "q"}]}
            )
        self.assertEqual(blocked.status_code, 503)
