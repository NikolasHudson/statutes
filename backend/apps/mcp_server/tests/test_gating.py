"""Policy tests for the MCP feature-gate + rate-limit layer.

These exercise ``gate_request`` directly with lightweight fakes so we don't need
a DB — what matters is that the MCP transport reuses the REST tier rules:
free-tier keys reach only lookup/search tools, paid tools 403, and the per-key
daily quota raises 429 once exhausted. The key-verification and quota math have
their own tests in ``apps.accounts`` / ``apps.api``; here we verify the wiring.
"""

from __future__ import annotations

import json

from django.core.cache import cache
from django.test import SimpleTestCase
from ninja.errors import HttpError

from apps.accounts.models import Tier
from apps.api import auth as rest_auth
from apps.mcp_server.gating import gate_request, tool_names


class _User:
    def __init__(self, tier: str):
        self.tier = tier


class _Key:
    """Enough of an APIKey for require_feature / enforce_rate_limit."""

    def __init__(self, pk: int, tier: str):
        self.pk = pk
        self.user = _User(tier)


def _call(tool: str, **arguments) -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
    ).encode("utf-8")


class ToolNameExtractionTests(SimpleTestCase):
    def test_tools_call_extracts_name(self):
        self.assertEqual(tool_names(json.loads(_call("search_statutes"))), ["search_statutes"])

    def test_non_tool_methods_yield_nothing(self):
        for method in ("initialize", "tools/list", "ping", "notifications/initialized"):
            payload = {"jsonrpc": "2.0", "id": 1, "method": method}
            self.assertEqual(tool_names(payload), [], method)

    def test_batch_collects_every_tool_call(self):
        payload = [
            json.loads(_call("lookup_citation")),
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            json.loads(_call("audit_brief")),
        ]
        self.assertEqual(tool_names(payload), ["lookup_citation", "audit_brief"])


class GateRequestTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_free_tier_may_call_search_and_lookup(self):
        key = _Key(pk=1, tier=Tier.FREE)
        # Neither of these should raise.
        gate_request(key, _call("search_statutes", query="theft"))
        gate_request(key, _call("lookup_citation", citation="714.16"))

    def test_free_tier_paid_tool_is_403(self):
        key = _Key(pk=2, tier=Tier.FREE)
        for tool in ("audit_brief", "validate_citations", "verify_quote", "get_version_history"):
            with self.assertRaises(HttpError) as ctx:
                gate_request(key, _call(tool, text="x"))
            self.assertEqual(ctx.exception.status_code, 403, tool)

    def test_solo_tier_may_call_paid_tools(self):
        key = _Key(pk=3, tier=Tier.SOLO)
        gate_request(key, _call("audit_brief", text="x"))
        gate_request(key, _call("validate_citations", text="x"))

    def test_unknown_tool_fails_closed_for_free_tier(self):
        # A tool not in TOOL_FEATURES defaults to the restrictive "validate"
        # gate, so a free key is blocked rather than waved through.
        key = _Key(pk=4, tier=Tier.FREE)
        with self.assertRaises(HttpError) as ctx:
            gate_request(key, _call("some_future_tool"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_non_tool_call_is_not_gated(self):
        key = _Key(pk=5, tier=Tier.FREE)
        # initialize / tools/list must pass even on the free tier so the MCP
        # handshake works, and must not consume quota.
        gate_request(key, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode())
        gate_request(key, b"")
        gate_request(key, b"not json at all")

    def test_daily_quota_raises_429_when_exhausted(self):
        key = _Key(pk=6, tier=Tier.FREE)
        original = rest_auth.TIER_DAILY_QUOTA[Tier.FREE]
        rest_auth.TIER_DAILY_QUOTA[Tier.FREE] = 2
        self.addCleanup(lambda: rest_auth.TIER_DAILY_QUOTA.__setitem__(Tier.FREE, original))

        gate_request(key, _call("search_statutes"))  # 1
        gate_request(key, _call("search_statutes"))  # 2
        with self.assertRaises(HttpError) as ctx:
            gate_request(key, _call("search_statutes"))  # 3 -> over quota
        self.assertEqual(ctx.exception.status_code, 429)

    def test_denied_feature_does_not_consume_quota(self):
        # A 403 must not charge the daily budget: the feature check runs before
        # any quota increment.
        key = _Key(pk=7, tier=Tier.FREE)
        original = rest_auth.TIER_DAILY_QUOTA[Tier.FREE]
        rest_auth.TIER_DAILY_QUOTA[Tier.FREE] = 1
        self.addCleanup(lambda: rest_auth.TIER_DAILY_QUOTA.__setitem__(Tier.FREE, original))

        with self.assertRaises(HttpError):
            gate_request(key, _call("audit_brief", text="x"))  # 403, no charge
        # The one allowed call still goes through.
        gate_request(key, _call("search_statutes"))
