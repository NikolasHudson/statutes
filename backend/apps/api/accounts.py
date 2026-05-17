"""Account + API key management endpoints.

The X-API-Key header authenticates *integration* traffic (REST + MCP HTTP).
This module covers the *user-facing* flows behind those keys:

    * register / login / logout / me     — Django session auth
    * list / create / revoke API keys    — must be logged in

All endpoints under here use cookie-session auth, not X-API-Key. The
frontend register/login flow runs through a browser, so the session cookie
is the right shape; the X-API-Key header is for headless callers (Claude
Desktop, scripts, the REST API).

CORS_ALLOW_CREDENTIALS must be True in settings for the cookie to round-trip
between the Vite dev server and Django.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.models import APIKey, User, generate_key


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
# Auth — register / login / logout / me
# ---------------------------------------------------------------------------


@auth_router.post("/register", response={200: UserOut, 400: dict}, auth=None)
def register(request, payload: RegisterRequest):
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HttpError(400, "valid email required")
    if len(payload.password) < 8:
        raise HttpError(400, "password must be at least 8 characters")
    if User.objects.filter(email__iexact=email).exists():
        raise HttpError(400, "an account with that email already exists")

    user = User.objects.create_user(
        email=email,
        password=payload.password,
        full_name=payload.full_name.strip(),
    )
    # Log them in immediately so the next request can see them.
    login(request, user)
    return _user_out(user)


@auth_router.post("/login", response={200: UserOut, 401: dict}, auth=None)
def login_view(request, payload: LoginRequest):
    user = authenticate(
        request, email=payload.email.strip().lower(), password=payload.password
    )
    if user is None:
        raise HttpError(401, "invalid email or password")
    login(request, user)
    return _user_out(user)


@auth_router.post("/logout", response={200: dict}, auth=None)
def logout_view(request):
    logout(request)
    return {"status": "ok"}


@auth_router.get("/me", response={200: UserOut, 401: dict}, auth=None)
def me(request):
    user = _require_login(request)
    return _user_out(user)


@auth_router.patch(
    "/me", response={200: UserOut, 400: dict, 401: dict}, auth=None
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
    return _user_out(user)


@auth_router.post(
    "/change-password", response={200: dict, 400: dict, 401: dict}, auth=None
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
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# API keys — list / create / revoke
# ---------------------------------------------------------------------------


@account_router.get("/api-keys", response=list[APIKeyOut], auth=None)
def list_keys(request):
    user = _require_login(request)
    rows = list(
        APIKey.objects.filter(user=user, revoked_at__isnull=True).order_by("-created_at")
    )
    return [_key_out(k) for k in rows]


@account_router.post(
    "/api-keys", response={200: CreateKeyResponse, 400: dict}, auth=None
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
    return CreateKeyResponse(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        raw_key=raw,
        created_at=key.created_at,
    )


@account_router.delete(
    "/api-keys/{key_id}", response={200: dict, 404: dict}, auth=None
)
def revoke_key(request, key_id: int):
    user = _require_login(request)
    try:
        key = APIKey.objects.get(pk=key_id, user=user, revoked_at__isnull=True)
    except APIKey.DoesNotExist as exc:
        raise HttpError(404, "key not found") from exc
    key.revoked_at = timezone.now()
    key.save(update_fields=["revoked_at"])
    return {"status": "revoked", "id": key_id}
