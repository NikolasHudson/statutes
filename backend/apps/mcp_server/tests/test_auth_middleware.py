"""ASGI auth middleware contract tests.

We monkey-patch ``apps.accounts.models.verify_key`` so the test never touches
the DB — what we're verifying is the middleware behavior (header parsing,
401 on missing/invalid, scope passthrough on valid), not the key-verification
logic itself, which has its own tests in ``apps.accounts``.

Keeping this off the DB also means we can use the lighter ``SimpleTestCase``,
which avoids tripping on the ingestion suite's serialized-rollback fixtures
when both suites run together (see memory: feedback_test_class_choice)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.mcp_server.auth import api_key_middleware


def _run(coro):
    """Drive a coroutine to completion. Each call gets a fresh event loop so
    we don't get bitten by ``asyncio.get_event_loop()`` raising once another
    test has consumed the implicit one."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _RecorderApp:
    """Minimal ASGI app that records invocations and returns 204."""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)
        await send(
            {"type": "http.response.start", "status": 204, "headers": []}
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _drive(app, headers: list[tuple[bytes, bytes]]) -> tuple[int, bytes]:
    """Run one ASGI request and capture status + body."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "headers": headers,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    captured: dict = {"status": None, "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    await app(scope, receive, send)
    return captured["status"], captured["body"]


class _FakeAPIKey:
    """Mimics enough of the APIKey row for assertions in the passthrough
    test — the middleware itself is opaque to its shape."""

    def __init__(self, user_id: int):
        self.user_id = user_id


class ApiKeyMiddlewareTests(SimpleTestCase):
    def test_missing_header_returns_401(self):
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        with patch("apps.accounts.models.verify_key", return_value=None) as v:
            status, body = _run(_drive(app, headers=[]))
        self.assertEqual(status, 401)
        self.assertIn(b"missing", body)
        self.assertEqual(recorder.calls, [])
        v.assert_not_called()  # short-circuit before verify_key

    def test_invalid_key_returns_401(self):
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        with patch("apps.accounts.models.verify_key", return_value=None):
            status, body = _run(
                _drive(app, headers=[(b"x-api-key", b"definitely-not-real")])
            )
        self.assertEqual(status, 401)
        self.assertIn(b"invalid", body)
        self.assertEqual(recorder.calls, [])

    def test_valid_key_passes_through_and_attaches_scope(self):
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        fake = _FakeAPIKey(user_id=42)
        with patch("apps.accounts.models.verify_key", return_value=fake):
            status, _ = _run(
                _drive(app, headers=[(b"x-api-key", b"valid-looking-key")])
            )
        self.assertEqual(status, 204)
        self.assertEqual(len(recorder.calls), 1)
        self.assertIs(recorder.calls[0]["mcp_api_key"], fake)

    def test_lifespan_passthrough(self):
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)

        async def go():
            scope = {"type": "lifespan"}

            async def receive():
                return {"type": "lifespan.startup"}

            async def send(_):
                pass

            await app(scope, receive, send)
            return recorder.calls

        with patch("apps.accounts.models.verify_key", return_value=None) as v:
            calls = _run(go())
        # The recorder was reached (it's the inner app), proving the
        # middleware did not short-circuit non-HTTP scopes — and it never
        # consulted verify_key for them.
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["type"], "lifespan")
        v.assert_not_called()
