"""ASGI middleware that gates the MCP HTTP transport on Bearer OR X-API-Key.

The stdio transport is local-only and assumed trusted (the README is explicit
about that). The HTTP transport is what attorneys' Claude Desktop installs
will dial into, so it has to be authenticated.

Two credentials are accepted, checked in this order:

1. ``Authorization: Bearer <token>`` — an OAuth 2.0 access token issued by
   our co-hosted authorization server (apps/mcp_server/oauth.py). This is the
   MCP-spec path and what claude.ai's connector UI uses. Tokens are opaque
   bearers verified by hashed lookup (:func:`models.verify_access_token`);
   the resolved token is wrapped in :class:`BearerPrincipal` so the existing
   per-user gating applies unchanged.
2. ``X-API-Key`` header → ``verify_key`` — the original REST-mirrored path,
   kept for backward compatibility (Claude Desktop via ``mcp-remote``).

401 responses carry ``WWW-Authenticate: Bearer resource_metadata="…"`` per
RFC 9728 §5.1 / the MCP authorization spec, so a spec-following client can
discover the authorization server and start the OAuth flow unprompted.

Successful requests get an ``mcp_api_key`` attribute on the ASGI scope so
downstream code can read the user/tier off it (for Bearer requests that is
the :class:`BearerPrincipal`, which duck-types the same surface).

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
AUTHORIZATION_HEADER = b"authorization"


class BearerPrincipal:
    """Adapt an OAuthToken to the APIKey surface the gate reads.

    ``gate_request`` (gating.py) needs exactly two attributes: ``.user`` (its
    tier drives ``require_feature``) and ``.pk`` (the rate-limit cache key).
    The pk is prefixed so an OAuth token's daily quota bucket can never
    collide with an APIKey row that happens to share the integer id."""

    def __init__(self, token):
        self.token = token
        self.user = token.user
        self.pk = f"oauth-{token.pk}"

    @property
    def user_id(self):
        return self.token.user_id


def _resource_metadata_url(scope: dict) -> str:
    """The RFC 9728 Protected Resource Metadata URL advertised on 401s.

    ``MCP_OAUTH_ISSUER`` pins the public origin in prod (the MCP service can
    sit behind path-based ingress where the request Host is an internal
    hostname); otherwise it derives from the request's Host header."""
    configured = os.environ.get("MCP_OAUTH_ISSUER", "").strip()
    if configured:
        base = configured.rstrip("/")
    else:
        host = ""
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name == b"host":
                host = raw_value.decode("latin-1").strip()
                break
        bare = host.split(":", 1)[0]
        scheme = "http" if bare in ("localhost", "127.0.0.1") else "https"
        base = f"{scheme}://{host}" if host else "https://localhost"
    return f"{base}/.well-known/oauth-protected-resource/mcp"


def _www_authenticate(scope: dict, error: str | None = None) -> bytes:
    parts = ["Bearer"]
    attrs = []
    if error:
        attrs.append(f'error="{error}"')
    attrs.append(f'resource_metadata="{_resource_metadata_url(scope)}"')
    return (parts[0] + " " + ", ".join(attrs)).encode("latin-1")


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


async def _send_json(
    send: Callable,
    body: bytes,
    status: int,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


def api_key_middleware(app: ASGIApp) -> ASGIApp:
    """Wrap an ASGI app so every HTTP request must carry a valid credential —
    an OAuth Bearer access token or an X-API-Key.

    Non-HTTP scopes (lifespan, websocket) are passed through untouched."""

    async def middleware(scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return

        # Find the credential headers. ASGI lowercases header names.
        key: str | None = None
        bearer: str | None = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name == HEADER_NAME and key is None:
                key = raw_value.decode("latin-1").strip()
            elif raw_name == AUTHORIZATION_HEADER and bearer is None:
                value = raw_value.decode("latin-1").strip()
                if value[:7].lower() == "bearer ":
                    bearer = value[7:].strip()

        if not key and not bearer:
            body, status = _unauthorized(
                "missing credentials: send an OAuth Bearer token "
                "(Authorization header) or an X-API-Key header"
            )
            await _send_json(
                send,
                body,
                status,
                extra_headers=[(b"www-authenticate", _www_authenticate(scope))],
            )
            return

        # Django ORM is sync; the MCP server runs ASGI.
        # thread_sensitive=True keeps the sync DB calls on the main thread so
        # they share the connection (and, in tests, the open transaction) with
        # the rest of the process. Each check is one indexed lookup; the
        # serialization cost is negligible.
        api_key = None
        if bearer:
            # OAuth path (the MCP-spec credential). A presented-but-invalid
            # Bearer token 401s immediately — it must NOT fall through to the
            # X-API-Key check, so a spec-following client sees the
            # WWW-Authenticate challenge and re-runs the OAuth flow.
            from .models import verify_access_token as _verify_token

            token = await sync_to_async(_verify_token, thread_sensitive=True)(
                bearer
            )
            if token is None:
                body, status = _unauthorized(
                    "invalid, expired, or revoked access token"
                )
                await _send_json(
                    send,
                    body,
                    status,
                    extra_headers=[
                        (
                            b"www-authenticate",
                            _www_authenticate(scope, error="invalid_token"),
                        )
                    ],
                )
                return
            api_key = BearerPrincipal(token)
        else:
            from apps.accounts.models import verify_key as _verify_key

            api_key = await sync_to_async(_verify_key, thread_sensitive=True)(
                key
            )
            if api_key is None:
                body, status = _unauthorized("invalid or revoked API key")
                await _send_json(
                    send,
                    body,
                    status,
                    extra_headers=[
                        (b"www-authenticate", _www_authenticate(scope))
                    ],
                )
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
