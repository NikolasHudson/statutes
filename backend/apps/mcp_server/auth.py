"""ASGI middleware that gates the MCP HTTP transport on X-API-Key.

The stdio transport is local-only and assumed trusted (the README is explicit
about that). The HTTP transport is what attorneys' Claude Desktop installs
will dial into, so it has to be authenticated.

We mirror the REST API's auth model: ``X-API-Key`` header → ``verify_key`` →
401 if invalid. Successful requests get an ``mcp_api_key`` attribute on the
ASGI scope so downstream code can read the user/tier off it.

Beyond authentication we also apply the REST API's *authorization* and
*rate-limiting* on this transport (see :mod:`apps.mcp_server.gating`): the
JSON-RPC body is buffered so we can see which tool a ``tools/call`` targets,
then the same ``require_feature`` / ``enforce_rate_limit`` primitives the REST
API uses gate it (403 / 429) before the request reaches FastMCP. The buffered
body is replayed to the inner app unchanged.
"""

from __future__ import annotations

import json
import os
from typing import Awaitable, Callable

from asgiref.sync import sync_to_async


ASGIApp = Callable[[dict, Callable, Callable], Awaitable[None]]


HEADER_NAME = b"x-api-key"


# Cap the buffered request body. We must buffer to inspect the JSON-RPC method,
# and an unbounded buffer would itself be a memory-DoS vector, so we bound it.
# The largest legitimate payload is a full brief passed to audit_brief; 1 MB is
# comfortably above the corpus tools' 250k-char text ceiling while still capping
# memory. Override per-environment with ``MCP_MAX_BODY_BYTES``.
def _max_body_bytes() -> int:
    raw = os.environ.get("MCP_MAX_BODY_BYTES", "").strip()
    if raw.isdigit():
        return int(raw)
    return 1_000_000


def _error(detail: str, status: int, code: str = "error") -> tuple[bytes, int]:
    body = json.dumps({"error": code, "detail": detail}).encode("utf-8")
    return body, status


def _unauthorized(detail: str) -> tuple[bytes, int]:
    return _error(detail, 401, code="unauthorized")


async def _send_json(send: Callable, body: bytes, status: int) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


def api_key_middleware(app: ASGIApp) -> ASGIApp:
    """Wrap an ASGI app so every HTTP request must carry a valid X-API-Key.

    Non-HTTP scopes (lifespan, websocket) are passed through untouched."""

    async def middleware(scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return

        # Find the X-API-Key header. ASGI lowercases header names.
        key: str | None = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name == HEADER_NAME:
                key = raw_value.decode("latin-1").strip()
                break

        if not key:
            body, status = _unauthorized("missing X-API-Key header")
            await _send_json(send, body, status)
            return

        # Django ORM is sync; the MCP server runs ASGI.
        from apps.accounts.models import verify_key as _verify_key

        # thread_sensitive=True keeps the sync DB call on the main thread so
        # it shares the connection (and, in tests, the open transaction) with
        # the rest of the process. The auth check is one indexed lookup; the
        # serialization cost is negligible.
        api_key = await sync_to_async(_verify_key, thread_sensitive=True)(key)
        if api_key is None:
            body, status = _unauthorized("invalid or revoked API key")
            await _send_json(send, body, status)
            return

        # Buffer the request body so we can inspect the JSON-RPC method for the
        # feature/quota gate, then replay it downstream unchanged.
        limit = _max_body_bytes()
        buffered = b""
        more = True
        while more:
            message = await receive()
            msg_type = message.get("type")
            if msg_type == "http.request":
                buffered += message.get("body", b"")
                more = message.get("more_body", False)
                if len(buffered) > limit:
                    body, status = _error("request body too large", 413)
                    await _send_json(send, body, status)
                    return
            elif msg_type == "http.disconnect":
                return
            else:
                more = False

        # Authorization + rate limiting, sharing the REST API's primitives.
        # gate_request raises ninja HttpError (403 tier-gate / 429 quota); we're
        # outside ninja's exception handler here, so translate it to JSON.
        from ninja.errors import HttpError

        from .gating import gate_request

        try:
            await sync_to_async(gate_request, thread_sensitive=True)(
                api_key, buffered
            )
        except HttpError as exc:
            body, status = _error(str(exc), exc.status_code, code="forbidden")
            await _send_json(send, body, status)
            return

        # Replay the buffered body to the inner app: hand back the whole body in
        # one message, then defer to the original receive for anything after.
        replayed = False

        async def replay_receive() -> dict:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {
                    "type": "http.request",
                    "body": buffered,
                    "more_body": False,
                }
            return await receive()

        scope["mcp_api_key"] = api_key
        await app(scope, replay_receive, send)

    return middleware
