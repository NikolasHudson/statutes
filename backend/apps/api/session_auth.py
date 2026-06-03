"""CSRF-aware session auth for the browser-facing Ninja routes.

The ``X-API-Key`` routes (apps/api/auth.py) are deliberately *not* covered
here: headless callers send a bearer-style header, no cookie and no Origin, so
CSRF does not apply to them. Flipping ``NinjaAPI(csrf=True)`` would wrongly
demand a CSRF token on those POSTs too — so CSRF is attached per-router on the
cookie surface instead.

Two objects cover that surface:

* :data:`session_auth` — authenticate the caller from the Django session
  cookie AND enforce the CSRF token on unsafe methods. Attach to every
  logged-in route (chat, verify, account keys, profile, change-password).
  django-ninja's ``SessionAuth`` (an ``APIKeyCookie`` subclass) already runs
  the cookie CSRF check in ``_get_key``; we re-export it under a local name so
  the intent reads clearly at the call site.

* :data:`csrf_protect` — enforce the CSRF token on *public* state-changing
  routes that cannot require a logged-in user (login / register / logout). It
  maps no user; it exists only so django-ninja runs its cookie CSRF check
  before the handler creates or destroys a session. ``authenticate`` returns a
  constant so the operation always proceeds — the handler does its own
  credential check.

Note on tests: Django's test ``Client`` sets ``_dont_enforce_csrf_checks`` on
the request unless constructed with ``enforce_csrf_checks=True``. Ninja's CSRF
check honours that flag, so the existing cookie-auth tests keep passing; the
CSRF regression tests opt in with ``Client(enforce_csrf_checks=True)``.
"""

from __future__ import annotations

from typing import Any, Optional

from django.conf import settings
from django.http import HttpRequest
from ninja.security import SessionAuth
from ninja.security.apikey import APIKeyCookie


# Authenticated browser routes: real session auth, CSRF enforced for unsafe
# methods (the APIKeyCookie base runs the check before authenticate()).
session_auth = SessionAuth()


class CsrfProtect(APIKeyCookie):
    """CSRF gate for unauthenticated, state-changing browser routes.

    Subclasses ``APIKeyCookie`` purely to inherit its CSRF check; it never
    maps the cookie to a user. ``_get_key`` (run first) raises 403 when the
    CSRF token is missing or bad on a POST/PUT/PATCH/DELETE; ``authenticate``
    then returns a non-``None`` sentinel so the request always reaches the
    handler, which validates credentials itself.
    """

    param_name: str = settings.SESSION_COOKIE_NAME

    def authenticate(self, request: HttpRequest, key: Optional[str]) -> Optional[Any]:
        return True


csrf_protect = CsrfProtect()
