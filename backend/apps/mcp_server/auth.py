"""ASGI middleware that gates the MCP HTTP transport on X-API-Key.

The stdio transport is local-only and assumed trusted (the README is explicit
about that). The HTTP transport is what attorneys' Claude Desktop installs
will dial into, so it has to be authenticated.

We mirror the REST API's auth model: ``X-API-Key`` header → ``verify_key`` →
401 if invalid. Successful requests get an ``mcp_api_key`` attribute on the
ASGI scope so downstream code can read the user/tier off it later (rate
limiting, audit logging — both deferred for now).
"""

from __future__ import annotations

import json
from typing import Awaitable, Callable

from asgiref.sync import sync_to_async


ASGIApp = Callable[[dict, Callable, Callable], Awaitable[None]]


HEADER_NAME = b"x-api-key"


def _unauthorized(detail: str) -> tuple[bytes, int]:
    body = json.dumps({"error": "unauthorized", "detail": detail}).encode("utf-8")
    return body, 401


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

        scope["mcp_api_key"] = api_key
        await app(scope, receive, send)

    return middleware
