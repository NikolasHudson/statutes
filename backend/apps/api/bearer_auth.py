"""OAuth 2.0 Bearer auth for the Ninja API.

Until now the OAuth tokens minted by :mod:`apps.oauth_server.oauth` were honoured
in exactly one place: the MCP ASGI middleware. Django ``/api/*`` accepted only
``X-API-Key`` or a session cookie, so an OAuth-authenticated client (the
EDMSpro browser extension, which signs in with
``chrome.identity.launchWebAuthFlow`` and has no cookie and no pasted key) had
no way in. This class closes that gap without duplicating the authorization
server: the same tokens, the same hashed-lookup verification, the same
``user.is_active`` kill-switch.

Scope is enforced here rather than left to handlers. A token issued for ``mcp``
must not open ``/api/edms`` just because both are Bearer surfaces — the whole
point of threading a scope through the code → token → refresh chain is that it
constrains something.
"""

from __future__ import annotations

from ninja.security import HttpBearer

from apps.oauth_server.models import OAuthToken, verify_access_token


class OAuthBearerAuth(HttpBearer):
    """Authenticate ``Authorization: Bearer <token>`` against ``OAuthToken``.

    Returns the token row (so handlers can read ``.user`` and ``.scope``), or
    ``None`` — which Ninja turns into 401 — for anything unknown, revoked,
    expired, belonging to a deactivated user, or lacking ``required_scope``.
    Never distinguishes between those cases to the caller.
    """

    def __init__(self, required_scope: str = ""):
        self.required_scope = required_scope
        super().__init__()

    def authenticate(self, request, token: str) -> OAuthToken | None:
        row = verify_access_token(token or "")
        if row is None:
            return None
        if self.required_scope and self.required_scope not in (row.scope or "").split():
            return None
        return row
