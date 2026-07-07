"""Per-key authorization + rate limiting for the MCP HTTP transport.

The REST API gates every call with two primitives — :func:`enforce_rate_limit`
(per-key daily quota) and :func:`require_feature` (tier feature entitlement),
both in :mod:`apps.api.auth`. The MCP transport historically skipped both (see
the old ``auth.py`` docstring: "rate limiting, audit logging — both deferred"),
so a free-tier key could call paid tools at unbounded frequency — a cost-
amplification + availability DoS and a tier-entitlement bypass.

This module reuses the REST primitives so both surfaces share one policy, and
maps each MCP tool to the same feature string the REST tiers are defined in
terms of. It works on the raw JSON-RPC request body: only ``tools/call``
requests are gated, so the ``initialize`` / ``tools/list`` / ``ping`` handshake
and notifications are never quota-charged or feature-blocked.
"""

from __future__ import annotations

import json

from apps.accounts.models import APIKey
from apps.api.auth import enforce_rate_limit, require_feature

# MCP tool name -> the feature string in ``apps.api.auth.FEATURES_BY_TIER``.
# Free tier gets {"lookup", "search"} (lookup_citation + search_statutes);
# every other tool is SOLO+. Keep this in lockstep with the @mcp.tool
# registrations in server.py.
TOOL_FEATURES: dict[str, str] = {
    "lookup_citation": "lookup",
    "search_statutes": "search",
    "get_version_history": "history",
    "get_section_at_date": "at_date",
    "get_cross_references": "cross_refs",
    "get_definitions": "definitions",
    "list_recent_amendments": "amendments",
    "validate_citations": "validate",
    "verify_quote": "validate",
    "audit_brief": "validate",
}

# An unknown tool name maps to the most-restrictive gate so a newly-added tool
# is paid-by-default until it's explicitly classified above (fail closed).
_DEFAULT_FEATURE = "validate"


def tool_names(payload) -> list[str]:
    """Return the tool name(s) invoked by a parsed JSON-RPC MCP request body.

    Usually 0 or 1. Non-tool-call methods — ``initialize`` / ``tools/list`` /
    ``ping`` / notifications — yield ``[]``, so discovery and the handshake are
    never quota-charged or feature-gated. A JSON-RPC batch (list) is handled by
    collecting every ``tools/call`` member."""
    items = payload if isinstance(payload, list) else [payload]
    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("method") != "tools/call":
            continue
        params = item.get("params") or {}
        name = params.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def gate_request(api_key: APIKey, body: bytes) -> None:
    """Enforce feature entitlement + rate limit for a raw MCP request body.

    Raises ninja ``HttpError`` (403 for a feature the tier lacks, 429 when the
    daily quota is exhausted), exactly as the REST ``_gate()`` does. A body that
    is not a tool call — or is unparseable — is allowed through untouched; the
    FastMCP layer handles malformed JSON-RPC and non-tool methods itself.

    Feature checks run for every requested tool *before* any quota is charged,
    so a 403 never consumes the caller's daily budget."""
    try:
        payload = json.loads(body) if body else None
    except (ValueError, UnicodeDecodeError):
        return

    names = tool_names(payload)
    if not names:
        return

    for name in names:
        require_feature(api_key, TOOL_FEATURES.get(name, _DEFAULT_FEATURE))
    for _ in names:
        enforce_rate_limit(api_key)
