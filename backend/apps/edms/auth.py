"""Who may call ``/api/edms``, and how much.

Three credential shapes reach this router, because three genuinely different
clients need it:

* **OAuth Bearer** — the browser extension, signed in through
  ``chrome.identity.launchWebAuthFlow`` against our own authorization server.
  It has no cookie (it is not a page on our origin) and we are not going to ask
  attorneys to paste API keys into a Chrome extension. Scope-locked to ``edms``:
  an ``mcp`` token opens nothing here.
* **X-API-Key** — the power-user / scripting fallback, and the escape hatch if
  the OAuth flow ever misbehaves on a locked-down machine.
* **Session cookie** — the SPA settings page at ``/account/edms``. CSRF is
  enforced by Ninja's ``SessionAuth`` on unsafe methods, as everywhere else on
  the cookie surface.

Ninja tries them in that order and stops at the first that authenticates, so
``request.auth`` is one of three different objects. :func:`caller` normalizes
that into a user plus *how* they proved it — which matters exactly once, and
importantly: enabling the crowdsource opt-in is session-only, so the SPA consent
screen is the only door into sharing a client's filings.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from ninja.errors import HttpError

from apps.accounts.models import APIKey
from apps.api.auth import api_key_auth, require_feature_for_user
from apps.api.bearer_auth import OAuthBearerAuth
from apps.api.session_auth import session_auth
from apps.oauth_server.models import OAuthToken

# The OAuth scope the extension requests and this router requires.
EDMS_SCOPE = "edms"

edms_bearer_auth = OAuthBearerAuth(required_scope=EDMS_SCOPE)

# Order matters: header-bearing machine credentials first, cookie last, so a
# browser that happens to hold both never has its CSRF check skipped.
EDMS_AUTH = [edms_bearer_auth, api_key_auth, session_auth]


@dataclass(frozen=True)
class Caller:
    user: object
    kind: str  # "oauth" | "api_key" | "session"

    @property
    def is_session(self) -> bool:
        return self.kind == "session"


def caller(request) -> Caller:
    """Normalize ``request.auth`` into (user, credential kind)."""
    auth = getattr(request, "auth", None)
    if isinstance(auth, OAuthToken):
        return Caller(user=auth.user, kind="oauth")
    if isinstance(auth, APIKey):
        return Caller(user=auth.user, kind="api_key")
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return Caller(user=user, kind="session")
    # Ninja only reaches a handler after an auth class returned non-None, so
    # this is unreachable in practice — it fails closed rather than handing a
    # handler an AnonymousUser it would happily filter querysets by.
    raise HttpError(401, "authentication required")


def require_edms(request) -> Caller:
    """Authenticate, then enforce the plan gate. Every handler starts here."""
    who = caller(request)
    require_feature_for_user(who.user, "edms")
    return who


def enforce_upload_quota(user) -> None:
    """Per-user daily cap on destination requests.

    EDMSpro's cost per call is small but not zero (each ``route`` is up to a
    handful of Graph round trips), and an extension bug that retries in a loop
    would otherwise burn a user's Microsoft throttle budget as well as ours.
    Same day-bucket cache counter the REST quota uses; 0 disables it."""
    limit = getattr(settings, "EDMS_DAILY_UPLOAD_LIMIT", 0)
    if not limit:
        return
    day_key = timezone.now().strftime("%Y-%m-%d")
    cache_key = f"edms:route:{user.pk}:{day_key}"
    try:
        used = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=86_400)
        used = 1
    if used > limit:
        raise HttpError(
            429,
            f"Daily EDMSpro save limit ({limit}) reached. It resets at midnight UTC.",
        )


def rate_limit_reset_epoch() -> int:
    """Unix epoch of the next UTC midnight — the quota header's reset time."""
    now = timezone.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timezone.timedelta(days=1)
    return int(time.mktime(midnight.timetuple()))
