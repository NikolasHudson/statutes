"""Production HTTP-app wiring contracts: the stateless/JSON transport flags, the
auth-exempt ``GET /healthz`` short-circuit, and transport-security defaults.

These cover config/transport wiring — not tool logic (``test_tools.py``) and not
auth-middleware behavior (``test_auth_middleware.py``). ``SimpleTestCase`` keeps
them off the DB (see the note in ``test_auth_middleware`` about the ingestion
suite's serialized-rollback fixtures); none of the code under test touches the
ORM."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.mcp_server.server import (
    _transport_security,
    _with_healthz,
    build_server,
)


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


async def _drive(app, method: str, path: str):
    scope = {"type": "http", "method": method, "path": path, "headers": []}

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


class ServerFlagsTests(SimpleTestCase):
    def test_stateless_and_json_enabled(self):
        # These two flags are what make the server safe behind App Platform's
        # no-affinity load balancer and clear of the edge streaming timeout.
        server = build_server()
        self.assertTrue(server.settings.stateless_http)
        self.assertTrue(server.settings.json_response)
        self.assertIsNotNone(server.settings.transport_security)


class HealthzTests(SimpleTestCase):
    def test_exact_get_healthz_short_circuits_before_inner_app(self):
        rec = _Recorder()
        app = _with_healthz(rec)
        out = _run(_drive(app, "GET", "/healthz"))
        self.assertEqual(out["status"], 200)
        self.assertIn(b'"status": "ok"', out["body"])
        # Crucially, the auth'd inner app was never reached.
        self.assertEqual(rec.calls, [])

    def test_post_healthz_falls_through(self):
        rec = _Recorder()
        app = _with_healthz(rec)
        out = _run(_drive(app, "POST", "/healthz"))
        self.assertEqual(out["status"], 204)
        self.assertEqual(len(rec.calls), 1)

    def test_only_exact_path_matches_no_prefix_bypass(self):
        # A startswith("/health") bypass placed ahead of auth would be an
        # auth-bypass surface; assert these near-misses fall through to the
        # inner (authenticated) app instead of returning 200.
        rec = _Recorder()
        app = _with_healthz(rec)
        for path in ("/healthz/", "/healthz/../mcp", "/healthzx", "/mcp", "/"):
            rec.calls.clear()
            out = _run(_drive(app, "GET", path))
            self.assertEqual(out["status"], 204, path)
            self.assertEqual(len(rec.calls), 1, path)

    def test_non_http_scope_passes_through(self):
        # The Starlette lifespan must reach the inner app — that's what starts
        # StreamableHTTPSessionManager.run().
        rec = _Recorder()
        app = _with_healthz(rec)

        async def receive():
            return {"type": "lifespan.startup"}

        async def send(_message):
            pass

        _run(app({"type": "lifespan"}, receive, send))
        self.assertEqual([s["type"] for s in rec.calls], ["lifespan"])


class TransportSecurityTests(SimpleTestCase):
    @override_settings(
        ALLOWED_HOSTS=["app.hudsonlegal.tech", "x.ondigitalocean.app"],
        CORS_ALLOWED_ORIGINS=["https://app.hudsonlegal.tech"],
    )
    def test_defaults_derive_from_django_with_port_wildcards(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in (
                "MCP_ALLOWED_HOSTS",
                "MCP_ALLOWED_ORIGINS",
                "MCP_DNS_REBINDING_PROTECTION",
            ):
                os.environ.pop(k, None)
            ts = _transport_security()
        self.assertTrue(ts.enable_dns_rebinding_protection)
        # Both bare host and :* port-wildcard forms, so a Host with or without an
        # explicit port validates.
        self.assertIn("app.hudsonlegal.tech", ts.allowed_hosts)
        self.assertIn("app.hudsonlegal.tech:*", ts.allowed_hosts)
        self.assertIn("x.ondigitalocean.app", ts.allowed_hosts)
        self.assertIn("x.ondigitalocean.app:*", ts.allowed_hosts)
        self.assertEqual(ts.allowed_origins, ["https://app.hudsonlegal.tech"])

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_wildcard_host_disables_protection(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("MCP_ALLOWED_HOSTS", "MCP_DNS_REBINDING_PROTECTION"):
                os.environ.pop(k, None)
            ts = _transport_security()
        # "*" has no exact-match equivalent in the SDK, so protection is off and
        # the literal "*" is not left in the allowlist.
        self.assertFalse(ts.enable_dns_rebinding_protection)
        self.assertNotIn("*", ts.allowed_hosts)

    def test_env_override_and_escape_hatch(self):
        with patch.dict(
            os.environ,
            {
                "MCP_ALLOWED_HOSTS": "a.example.com, b.example.com:9000",
                "MCP_ALLOWED_ORIGINS": "https://a.example.com",
                "MCP_DNS_REBINDING_PROTECTION": "false",
            },
        ):
            ts = _transport_security()
        self.assertFalse(ts.enable_dns_rebinding_protection)
        self.assertIn("a.example.com", ts.allowed_hosts)
        self.assertIn("a.example.com:*", ts.allowed_hosts)
        # A host that already carries a port is not given a :* variant.
        self.assertIn("b.example.com:9000", ts.allowed_hosts)
        self.assertNotIn("b.example.com:9000:*", ts.allowed_hosts)
        self.assertEqual(ts.allowed_origins, ["https://a.example.com"])
