"""Origin-lock contract on the MCP ASGI transport
(``server._with_origin_lock``) — the ASGI twin of the Django middleware test
in ``apps/api/tests/test_origin_lock.py``.

Layering under test (``build_http_app``): ``/healthz`` short-circuits OUTSIDE
the lock (the App Platform probe never transits Cloudflare, so it carries no
header), and the lock sits OUTSIDE auth (bypass traffic is refused before it
can exercise credential checking). ``SimpleTestCase`` keeps these off the DB;
nothing under test touches the ORM."""

from __future__ import annotations

import asyncio

from django.test import SimpleTestCase, override_settings

from apps.mcp_server.server import _with_healthz, _with_origin_lock


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Recorder:
    """Inner ASGI app that records the scopes it receives and returns 204."""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)
        if scope.get("type") == "http":
            await send(
                {"type": "http.response.start", "status": 204, "headers": []}
            )
            await send(
                {"type": "http.response.body", "body": b"", "more_body": False}
            )


async def _drive(app, method: str, path: str, headers=None):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": list(headers or []),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    captured = {"status": None, "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    await app(scope, receive, send)
    return captured


class OriginLockAsgiTests(SimpleTestCase):
    def test_inert_when_secret_unset(self):
        rec = _Recorder()
        result = _run(_drive(_with_origin_lock(rec), "GET", "/mcp"))
        self.assertEqual(result["status"], 204)
        self.assertEqual(len(rec.calls), 1)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_missing_header_is_rejected(self):
        rec = _Recorder()
        result = _run(_drive(_with_origin_lock(rec), "POST", "/mcp"))
        self.assertEqual(result["status"], 403)
        self.assertEqual(len(rec.calls), 0)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_wrong_header_is_rejected(self):
        rec = _Recorder()
        result = _run(
            _drive(
                _with_origin_lock(rec),
                "POST",
                "/mcp",
                headers=[(b"x-origin-lock", b"nope")],
            )
        )
        self.assertEqual(result["status"], 403)
        self.assertEqual(len(rec.calls), 0)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_correct_header_passes_through(self):
        rec = _Recorder()
        result = _run(
            _drive(
                _with_origin_lock(rec),
                "POST",
                "/mcp",
                headers=[(b"x-origin-lock", b"sekrit")],
            )
        )
        self.assertEqual(result["status"], 204)
        self.assertEqual(len(rec.calls), 1)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_non_http_scopes_pass_through(self):
        # Lifespan events must not be blocked or the server never boots.
        rec = _Recorder()

        async def _lifespan():
            await _with_origin_lock(rec)(
                {"type": "lifespan"}, None, None
            )

        _run(_lifespan())
        self.assertEqual(len(rec.calls), 1)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_healthz_short_circuits_outside_the_lock(self):
        # Production layering: _with_healthz(_with_origin_lock(inner)). The
        # probe carries no header and must still get its 200.
        rec = _Recorder()
        app = _with_healthz(_with_origin_lock(rec))
        result = _run(_drive(app, "GET", "/healthz"))
        self.assertEqual(result["status"], 200)
        self.assertEqual(len(rec.calls), 0)
