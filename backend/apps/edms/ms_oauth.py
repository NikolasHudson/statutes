"""Microsoft identity platform OAuth 2.0 client — connecting a user's OneDrive.

Not to be confused with :mod:`apps.oauth_server.oauth`, where *we* are the
authorization server and the extension is the client. Here the roles invert: we
are the client, Microsoft is the authorization server, and the prize is a
refresh token that lets this server create folders and mint upload sessions in
one attorney's OneDrive.

Two deliberate choices, both departures from the prototype:

* **State lives in the Django session, not the cache.** The prototype stashed
  the CSRF state (and a hand-rolled "begin token") in ``django.core.cache``.
  Production has no Redis today, so the cache is LocMem *per gunicorn worker* —
  an authorize request served by one worker and a callback served by another
  would simply not find the state, failing the connect intermittently and
  unreproducibly. Sessions are DB-backed and shared, so they are the correct
  store for a value that must survive a round trip through Microsoft.
* **The connect flow is browser-only.** It starts and ends on
  ``/account/edms``; the extension deep-links there rather than driving OAuth
  itself. That keeps the redirect URI single and fixed (Azure app registrations
  allowlist it exactly) and means no non-browser caller can start a consent
  flow on a user's behalf.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from django.conf import settings

AUTHORIZE_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

# Session keys for the state + the post-connect return path.
STATE_SESSION_KEY = "edms_ms_oauth_state"
HTTP_TIMEOUT = 20


class MicrosoftOAuthError(Exception):
    """Anything that goes wrong exchanging a code for tokens."""


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: datetime
    account_email: str
    account_name: str


def is_configured() -> bool:
    """False when the Azure app registration hasn't been set up (dev boxes, CI).
    The connect endpoints answer 503 rather than bouncing the user to a
    Microsoft error page that says nothing useful."""
    return bool(settings.MS_OAUTH_CLIENT_ID and settings.MS_OAUTH_CLIENT_SECRET)


def redirect_uri() -> str:
    """The one registered redirect URI, derived from ``APP_URL`` so it cannot
    drift from the app's real origin. Must match the Azure registration
    byte-for-byte."""
    if settings.MS_OAUTH_REDIRECT_URI:
        return settings.MS_OAUTH_REDIRECT_URI
    return settings.APP_URL.rstrip("/") + "/api/edms/integrations/onedrive/callback"


def new_state(session) -> str:
    """Mint a state value and bind it to this browser session."""
    state = secrets.token_urlsafe(32)
    session[STATE_SESSION_KEY] = state
    return state


def consume_state(session, presented: str) -> bool:
    """Constant-time compare against the session's state, then burn it."""
    stored = session.pop(STATE_SESSION_KEY, "")
    if not stored or not presented:
        return False
    return secrets.compare_digest(str(stored), presented)


def authorize_url(state: str) -> str:
    tenant = settings.MS_OAUTH_TENANT or "common"
    params = {
        "client_id": settings.MS_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "response_mode": "query",
        "scope": " ".join(settings.MS_OAUTH_SCOPES),
        "state": state,
        # Always show the account chooser: attorneys routinely have a personal
        # and a firm Microsoft account signed in, and silently picking the
        # wrong one files client documents in the wrong place.
        "prompt": "select_account",
    }
    return f"{AUTHORIZE_URL_TEMPLATE.format(tenant=tenant)}?{urlencode(params)}"


def exchange_code(code: str) -> TokenBundle:
    """Trade an authorization code for tokens, and read back who consented."""
    tenant = settings.MS_OAUTH_TENANT or "common"
    resp = requests.post(
        TOKEN_URL_TEMPLATE.format(tenant=tenant),
        data={
            "client_id": settings.MS_OAUTH_CLIENT_ID,
            "client_secret": settings.MS_OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
            "scope": " ".join(settings.MS_OAUTH_SCOPES),
        },
        timeout=HTTP_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise MicrosoftOAuthError(
            f"token exchange failed ({resp.status_code})"
        )
    body = resp.json()
    access_token = body.get("access_token", "")
    refresh_token = body.get("refresh_token", "")
    if not access_token or not refresh_token:
        # No refresh token means ``offline_access`` was not granted, and a
        # connection that dies in an hour is worse than no connection: it would
        # look healthy right up until the first save after lunch.
        raise MicrosoftOAuthError(
            "Microsoft did not return offline access. Reconnect and accept the "
            "permission to keep working when you are not signed in."
        )
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(body.get("expires_in", 3600))
    )

    profile = requests.get(
        GRAPH_ME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=HTTP_TIMEOUT,
    )
    me = profile.json() if profile.status_code < 400 else {}
    return TokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        account_email=me.get("mail") or me.get("userPrincipalName") or "",
        account_name=me.get("displayName", ""),
    )
