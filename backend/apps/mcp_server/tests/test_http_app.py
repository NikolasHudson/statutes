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

from django.test import SimpleTestCase, TransactionTestCase, override_settings

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


# ---------------------------------------------------------------------------
# DB connection hygiene (``_with_db_hygiene``) — the 2026-08-18 incident:
# a raw ASGI stack never fires Django's request signals, so a persistent
# connection the DB side dropped stayed dead in one gunicorn worker for hours.
# ---------------------------------------------------------------------------


class DbHygieneWrapperTests(SimpleTestCase):
    """Contract of the wrapper itself, with the Django hook mocked out."""

    def _events_app(self, events, raise_after=False):
        async def inner(scope, receive, send):
            events.append("inner")
            if raise_after:
                raise RuntimeError("tool blew up")
            await send(
                {"type": "http.response.start", "status": 204, "headers": []}
            )
            await send(
                {"type": "http.response.body", "body": b"", "more_body": False}
            )

        return inner

    def test_recycles_before_and_after_each_http_request(self):
        from apps.mcp_server.server import _with_db_hygiene

        events: list[str] = []
        with patch(
            "apps.mcp_server.server._close_old_connections",
            side_effect=lambda: events.append("recycle"),
        ):
            app = _with_db_hygiene(self._events_app(events))
            out = _run(_drive(app, "POST", "/mcp"))
        self.assertEqual(out["status"], 204)
        # Before the inner app (so its first ORM call gets a live connection)
        # and after it (so a connection that errored mid-request is reset).
        self.assertEqual(events, ["recycle", "inner", "recycle"])

    def test_recycles_in_finally_when_inner_app_raises(self):
        from apps.mcp_server.server import _with_db_hygiene

        events: list[str] = []
        with patch(
            "apps.mcp_server.server._close_old_connections",
            side_effect=lambda: events.append("recycle"),
        ):
            app = _with_db_hygiene(self._events_app(events, raise_after=True))
            with self.assertRaises(RuntimeError):
                _run(_drive(app, "POST", "/mcp"))
        self.assertEqual(events, ["recycle", "inner", "recycle"])

    def test_non_http_scope_passes_through_without_touching_db(self):
        from apps.mcp_server.server import _with_db_hygiene

        rec = _Recorder()
        with patch("apps.mcp_server.server._close_old_connections") as hook:
            app = _with_db_hygiene(rec)

            async def receive():
                return {"type": "lifespan.startup"}

            async def send(_message):
                pass

            _run(app({"type": "lifespan"}, receive, send))
        self.assertEqual([s["type"] for s in rec.calls], ["lifespan"])
        hook.assert_not_called()

    def test_hook_runs_on_the_same_thread_as_the_orm_work(self):
        # Django connections are thread-local: recycling on any thread other
        # than the thread_sensitive executor the tools use would be a no-op
        # for the connection that actually goes stale.
        import threading

        from asgiref.sync import sync_to_async

        from apps.mcp_server.server import _with_db_hygiene

        threads: list[tuple[str, int]] = []

        async def inner(scope, receive, send):
            await sync_to_async(
                lambda: threads.append(("orm", threading.get_ident())),
                thread_sensitive=True,
            )()
            await send(
                {"type": "http.response.start", "status": 204, "headers": []}
            )
            await send(
                {"type": "http.response.body", "body": b"", "more_body": False}
            )

        with patch(
            "apps.mcp_server.server._close_old_connections",
            side_effect=lambda: threads.append(
                ("recycle", threading.get_ident())
            ),
        ):
            _run(_drive(_with_db_hygiene(inner), "POST", "/mcp"))

        self.assertEqual([t[0] for t in threads], ["recycle", "orm", "recycle"])
        self.assertEqual(len({t[1] for t in threads}), 1, threads)

    def test_close_old_connections_skips_connections_inside_atomic(self):
        # TestCase wraps every test in atomic(); Django's own test client
        # avoids closing that connection by disconnecting the signal hook. We
        # call the hook directly, so the guard is ours.
        from unittest.mock import MagicMock

        from apps.mcp_server.server import _close_old_connections

        in_txn = MagicMock(in_atomic_block=True)
        free = MagicMock(in_atomic_block=False)
        fake_handler = MagicMock()
        fake_handler.all.return_value = [in_txn, free]
        with patch("apps.mcp_server.server.connections", fake_handler):
            _close_old_connections()
        fake_handler.all.assert_called_once_with(initialized_only=True)
        in_txn.close_if_unusable_or_obsolete.assert_not_called()
        free.close_if_unusable_or_obsolete.assert_called_once_with()

    def test_build_http_app_layers_hygiene_between_origin_lock_and_auth(self):
        # /healthz and the origin lock must never cost a DB round trip; auth is
        # the first ORM call of a request. So: origin_lock(hygiene(auth(mcp))).
        from apps.mcp_server import server as srv

        auth_app = object()
        hygiene_app = object()
        with (
            patch.object(
                srv, "_with_db_hygiene", return_value=hygiene_app
            ) as hygiene,
            patch.object(srv, "_with_origin_lock", return_value=object()) as lock,
            patch(
                "apps.mcp_server.auth.api_key_middleware",
                return_value=auth_app,
            ),
        ):
            srv.build_http_app()
        hygiene.assert_called_once_with(auth_app)
        lock.assert_called_once_with(hygiene_app)


class DbHygieneRecoveryTests(TransactionTestCase):
    """The incident, end to end, against a real connection on the
    thread_sensitive executor: sever the socket underneath Django, show that
    plain ORM calls now fail (and keep failing — that was the "until restart"
    part), then show one request through ``_with_db_hygiene`` recovers.

    ``TransactionTestCase`` (autocommit, no wrapping ``atomic()``) so the
    executor thread's connection behaves exactly as in production.
    ``serialized_rollback`` is the suite-wide convention for these (see the
    ingestion and tenancy migration tests): without it, this class's teardown
    flush would let ``post_migrate`` re-create content types under new pks,
    and the next serialized-rollback sibling to share the DB would then
    collide restoring the originals."""

    serialized_rollback = True

    def setUp(self):
        from asgiref.sync import sync_to_async
        from django.db import connections as dj_connections

        # The executor thread's connection is separate from this thread's;
        # close it on the way out or the test DB can't be dropped.
        self.addCleanup(
            lambda: _run(
                sync_to_async(dj_connections.close_all, thread_sensitive=True)()
            )
        )

    def test_dropped_connection_is_recycled_before_the_next_request(self):
        from asgiref.sync import sync_to_async
        from django.db import OperationalError, connection

        from apps.mcp_server.server import _with_db_hygiene

        def on_executor(fn):
            return sync_to_async(fn, thread_sensitive=True)()

        def query():
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone()[0]

        def sever():
            # What the DB side did at 19:28 UTC: hang up. Django's wrapper
            # still believes it holds a live connection.
            connection.connection.close()

        results: list[int] = []

        async def inner(scope, receive, send):
            results.append(await on_executor(query))
            await send(
                {"type": "http.response.start", "status": 204, "headers": []}
            )
            await send(
                {"type": "http.response.body", "body": b"", "more_body": False}
            )

        async def scenario():
            self.assertEqual(await on_executor(query), 1)
            await on_executor(sever)
            # Without hygiene: the incident, and it does not self-heal.
            for _ in range(2):
                with self.assertRaisesMessage(
                    OperationalError, "the connection is closed"
                ):
                    await on_executor(query)
            # With hygiene: recycled before the inner app's first query.
            out = await _drive(_with_db_hygiene(inner), "POST", "/mcp")
            self.assertEqual(out["status"], 204)
            self.assertEqual(results, [1])
            # And the connection stays good for a plain follow-up call.
            self.assertEqual(await on_executor(query), 1)

        _run(scenario())
