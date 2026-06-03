"""Account + API key management endpoints.

The X-API-Key header authenticates *integration* traffic (REST + MCP HTTP).
This module covers the *user-facing* flows behind those keys:

    * register / login / logout / me     — Django session auth
    * list / create / revoke API keys    — must be logged in

All endpoints under here use cookie-session auth, not X-API-Key. The
frontend register/login flow runs through a browser, so the session cookie
is the right shape; the X-API-Key header is for headless callers (Claude
Desktop, scripts, the REST API).

Because these routes ride on the session cookie, they are also CSRF-protected
(see apps/api/session_auth.py): the logged-in routes attach ``session_auth``
and the public login/register/logout routes attach ``csrf_protect``, both of
which enforce the CSRF token on unsafe methods. GET ``/csrf`` (and ``/me``)
hand the SPA the token it must echo back as ``X-CSRFToken``.

CORS_ALLOW_CREDENTIALS must be True in settings for the cookie to round-trip
between the frontend dev server and Django.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.core.cache import cache
from django.middleware.csrf import get_token
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.audit import AuditEvent, client_ip, record_event
from apps.accounts.models import APIKey, User, generate_key
from apps.api.session_auth import csrf_protect, session_auth


auth_router = Router()
account_router = Router()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(Schema):
    email: str
    password: str
    full_name: str = ""


class LoginRequest(Schema):
    email: str
    password: str


class UpdateProfileRequest(Schema):
    # Both optional: the client sends only the fields it wants to change.
    full_name: str | None = None
    email: str | None = None


class ChangePasswordRequest(Schema):
    current_password: str
    new_password: str


class UserOut(Schema):
    id: int
    email: str
    full_name: str
    tier: str
    date_joined: dt.datetime


class CreateKeyRequest(Schema):
    name: str


class APIKeyOut(Schema):
    """Public view of an APIKey row. The raw key is *not* in here — that
    only appears on creation, in CreateKeyResponse."""

    id: int
    name: str
    prefix: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None


class CreateKeyResponse(Schema):
    """Returned exactly once when the key is created. After this response
    the raw value is unrecoverable — only the SHA-256 hash is stored."""

    id: int
    name: str
    prefix: str
    raw_key: str
    created_at: dt.datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        tier=user.tier,
        date_joined=user.date_joined,
    )


def _key_out(api_key: APIKey) -> APIKeyOut:
    return APIKeyOut(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
    )


def _require_login(request) -> User:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, "authentication required")
    return user


# ---------------------------------------------------------------------------
# Registration throttle (#15). django-axes covers /login (it hooks the
# authenticate() call), but /register is not an auth call, so we guard it with
# the same cache-backed counter pattern used by the chat quota / API rate
# limiter (apps/api/chat.py:_bump). Keyed on source IP so a single host cannot
# spray account-creation/enumeration attempts; the per-attempt cost is one
# atomic cache incr against the shared (Redis in prod) store.
# ---------------------------------------------------------------------------
_REGISTER_MAX_PER_HOUR = 10
_REGISTER_WINDOW = 3600


def _register_throttle(request) -> None:
    """Raise 429 (generic) once an IP exceeds the hourly registration cap."""
    ip = client_ip(request) or "unknown"
    key = f"register:ip:{ip}:{timezone.now():%Y-%m-%d-%H}"
    try:
        used = cache.incr(key)
    except ValueError:
        if cache.add(key, 1, timeout=_REGISTER_WINDOW):
            used = 1
        else:
            used = cache.incr(key)
    if used > _REGISTER_MAX_PER_HOUR:
        record_event(
            event_type=AuditEvent.Event.REGISTER_BLOCKED,
            request=request,
            outcome=AuditEvent.Outcome.BLOCKED,
            detail={"reason": "rate_limited"},
        )
        raise HttpError(429, "too many requests, please try again later")


# ---------------------------------------------------------------------------
# Auth — register / login / logout / me
# ---------------------------------------------------------------------------


@auth_router.get("/csrf", response={200: dict}, auth=None)
def csrf(request):
    """Hand the SPA a CSRF token and set the ``csrftoken`` cookie on the
    response. The browser echoes the token back as the ``X-CSRFToken`` header
    on every credentialed unsafe request (login, chat, key management, …).
    Same-origin in prod, so the cookie round-trips."""
    return {"csrfToken": get_token(request)}


@auth_router.post(
    "/register", response={200: UserOut, 400: dict, 429: dict}, auth=csrf_protect
)
def register(request, payload: RegisterRequest):
    _register_throttle(request)
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HttpError(400, "valid email required")
    if len(payload.password) < 8:
        raise HttpError(400, "password must be at least 8 characters")
    if User.objects.filter(email__iexact=email).exists():
        # Generic message (finding #15): do NOT confirm the email is taken, or
        # the endpoint becomes an account-enumeration oracle. The duplicate is
        # still recorded in the audit trail for monitoring.
        record_event(
            event_type=AuditEvent.Event.REGISTER_BLOCKED,
            request=request,
            actor_email=email,
            outcome=AuditEvent.Outcome.BLOCKED,
            detail={"reason": "duplicate_email"},
        )
        raise HttpError(400, "could not create account with those details")

    user = User.objects.create_user(
        email=email,
        password=payload.password,
        full_name=payload.full_name.strip(),
    )
    # Log them in immediately so the next request can see them. login() fires
    # user_logged_in, which the audit signal records as a LOGIN_SUCCESS; emit
    # the registration event explicitly so account creation is its own line.
    record_event(
        event_type=AuditEvent.Event.REGISTER,
        request=request,
        actor=user,
        outcome=AuditEvent.Outcome.SUCCESS,
    )
    # With multiple AUTHENTICATION_BACKENDS configured (axes + ModelBackend),
    # login() can't infer which backend authenticated a user that was created
    # rather than returned by authenticate(), so name the real one explicitly.
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return _user_out(user)


@auth_router.post(
    "/login", response={200: UserOut, 401: dict, 429: dict}, auth=csrf_protect
)
def login_view(request, payload: LoginRequest):
    email = payload.email.strip().lower()
    credentials = {"email": email}

    # django-axes lockout check (findings #6/#15). When the IP+account is locked
    # out, short-circuit BEFORE touching the password so we neither burn a hash
    # nor reveal whether the account exists. The 429 body is intentionally
    # generic. (AxesStandaloneBackend would also block this inside
    # authenticate(); checking here lets us return a clear, attributed signal.)
    from axes.handlers.proxy import AxesProxyHandler

    if AxesProxyHandler.is_locked(request, credentials=credentials):
        record_event(
            event_type=AuditEvent.Event.LOGIN_LOCKED_OUT,
            request=request,
            actor_email=email,
            outcome=AuditEvent.Outcome.BLOCKED,
        )
        raise HttpError(
            429, "too many failed attempts, please try again later"
        )

    # authenticate(request, ...) lets axes observe the attempt (it hooks the
    # user_login_failed signal Django fires when every backend returns None).
    # The audit LOGIN_SUCCESS / LOGIN_FAILURE rows are written by the auth-signal
    # receivers in apps/accounts/signals.py.
    user = authenticate(request, email=email, password=payload.password)
    if user is None:
        raise HttpError(401, "invalid email or password")
    login(request, user)
    return _user_out(user)


@auth_router.post("/logout", response={200: dict}, auth=csrf_protect)
def logout_view(request):
    logout(request)
    return {"status": "ok"}


@auth_router.get("/me", response={200: UserOut, 401: dict}, auth=None)
def me(request):
    # Touch the CSRF token so Django sets the ``csrftoken`` cookie on this
    # response even when the caller is signed out. The SPA hits /me on load
    # (signed in or not), so this is the common path on which the browser
    # picks up the token it must echo back on later credentialed writes.
    get_token(request)
    user = _require_login(request)
    return _user_out(user)


@auth_router.patch(
    "/me", response={200: UserOut, 400: dict, 401: dict}, auth=session_auth
)
def update_me(request, payload: UpdateProfileRequest):
    """Edit the signed-in user's own profile (display name / login email).

    Tier is deliberately not editable here — it's a billing attribute, not
    something a user grants themselves."""
    user = _require_login(request)
    update_fields: list[str] = []

    if payload.full_name is not None:
        name = payload.full_name.strip()
        if len(name) > 200:
            raise HttpError(400, "name must be 200 characters or fewer")
        user.full_name = name
        update_fields.append("full_name")

    if payload.email is not None:
        email = payload.email.strip().lower()
        if not email or "@" not in email:
            raise HttpError(400, "valid email required")
        if (
            User.objects.filter(email__iexact=email)
            .exclude(pk=user.pk)
            .exists()
        ):
            raise HttpError(400, "an account with that email already exists")
        user.email = email
        update_fields.append("email")

    if update_fields:
        user.save(update_fields=update_fields)
        record_event(
            event_type=AuditEvent.Event.PROFILE_CHANGE,
            request=request,
            actor=user,
            outcome=AuditEvent.Outcome.SUCCESS,
            detail={"fields": update_fields},
        )
    return _user_out(user)


@auth_router.post(
    "/change-password", response={200: dict, 400: dict, 401: dict}, auth=session_auth
)
def change_password(request, payload: ChangePasswordRequest):
    user = _require_login(request)
    if not user.check_password(payload.current_password):
        raise HttpError(400, "current password is incorrect")
    if len(payload.new_password) < 8:
        raise HttpError(400, "new password must be at least 8 characters")
    user.set_password(payload.new_password)
    user.save(update_fields=["password"])
    # set_password rotates the session auth hash; without this the user's
    # own cookie would be invalidated and they'd be logged out mid-edit.
    update_session_auth_hash(request, user)
    record_event(
        event_type=AuditEvent.Event.PASSWORD_CHANGE,
        request=request,
        actor=user,
        outcome=AuditEvent.Outcome.SUCCESS,
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# API keys — list / create / revoke
# ---------------------------------------------------------------------------


@account_router.get("/api-keys", response=list[APIKeyOut], auth=session_auth)
def list_keys(request):
    user = _require_login(request)
    rows = list(
        APIKey.objects.filter(user=user, revoked_at__isnull=True).order_by("-created_at")
    )
    return [_key_out(k) for k in rows]


@account_router.post(
    "/api-keys", response={200: CreateKeyResponse, 400: dict}, auth=session_auth
)
def create_key(request, payload: CreateKeyRequest):
    user = _require_login(request)
    name = payload.name.strip()
    if not name:
        raise HttpError(400, "name is required")
    if len(name) > 100:
        raise HttpError(400, "name must be 100 characters or fewer")

    raw, prefix, hashed = generate_key()
    key = APIKey.objects.create(
        user=user, name=name, prefix=prefix, hashed_key=hashed
    )
    # Record the key prefix only — never the raw key — so the audit trail can
    # correlate a key to its lifecycle without storing a usable credential.
    record_event(
        event_type=AuditEvent.Event.API_KEY_CREATE,
        request=request,
        actor=user,
        outcome=AuditEvent.Outcome.SUCCESS,
        detail={"key_id": key.id, "prefix": prefix, "name": name},
    )
    return CreateKeyResponse(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        raw_key=raw,
        created_at=key.created_at,
    )


@account_router.delete(
    "/api-keys/{key_id}", response={200: dict, 404: dict}, auth=session_auth
)
def revoke_key(request, key_id: int):
    user = _require_login(request)
    try:
        key = APIKey.objects.get(pk=key_id, user=user, revoked_at__isnull=True)
    except APIKey.DoesNotExist as exc:
        raise HttpError(404, "key not found") from exc
    key.revoked_at = timezone.now()
    key.save(update_fields=["revoked_at"])
    record_event(
        event_type=AuditEvent.Event.API_KEY_REVOKE,
        request=request,
        actor=user,
        outcome=AuditEvent.Outcome.SUCCESS,
        detail={"key_id": key_id, "prefix": key.prefix},
    )
    return {"status": "revoked", "id": key_id}
