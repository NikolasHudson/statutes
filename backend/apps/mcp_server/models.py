"""OAuth 2.0 authorization models for the MCP server.

The MCP spec models a remote MCP server as an OAuth 2.1 *resource server* and
requires an authorization server for hosted clients (claude.ai Custom
Connectors do point-and-click OAuth; they cannot send a static ``X-API-Key``
header). We co-host a minimal authorization server with the resource server:
the Django service already owns users, sessions, and login, so it issues the
tokens and the MCP ASGI app validates them against the same tables.

Three tables mirror the shape of the flow:

* :class:`OAuthClient` — a dynamically-registered client (RFC 7591). Claude
  registers itself; no admin action needed. Public clients (PKCE-only,
  ``token_endpoint_auth_method="none"``) carry no secret.
* :class:`OAuthAuthorizationCode` — the short-lived, single-use authorization
  code binding a user's consent to a client + PKCE challenge.
* :class:`OAuthToken` — the issued access/refresh token pair. Tokens are
  opaque random bearers (NOT JWTs) stored as SHA-256 hashes, exactly like
  :class:`apps.accounts.models.APIKey` — a DB compromise leaks no usable
  credentials, and revocation is a row update, not a key-rotation event.

Every raw credential is generated with ``secrets.token_urlsafe`` and shown to
the client exactly once; only hashes persist.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

# Lifetimes. Access tokens are short so a leaked bearer ages out quickly;
# refresh tokens are long enough that a weekly-use connector never re-consents,
# and they ROTATE on every use (OAuth 2.1 MUST for public clients), so a stolen
# refresh token dies the moment either party uses it.
ACCESS_TOKEN_TTL_SECONDS = 60 * 60            # 1 hour
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
AUTH_CODE_TTL_SECONDS = 10 * 60                # 10 minutes


def hash_token(raw: str) -> str:
    """SHA-256 hex digest — same storage scheme as APIKey.hashed_key."""
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token() -> tuple[str, str]:
    """Return (raw, hashed). The raw value is returned to the client once and
    never persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


class OAuthClient(models.Model):
    """A dynamically-registered OAuth client (RFC 7591).

    Registration is open (the RFC's model — Claude registers itself without
    user interaction), so a client row grants nothing by itself: every token
    still requires a logged-in user's explicit consent on the authorize page,
    and entitlement comes from that user's tier, never from the client."""

    class AuthMethod(models.TextChoices):
        NONE = "none", "None (public client, PKCE only)"
        CLIENT_SECRET_POST = "client_secret_post", "Client secret (POST body)"
        CLIENT_SECRET_BASIC = "client_secret_basic", "Client secret (HTTP Basic)"

    client_id = models.CharField(max_length=64, unique=True, db_index=True)
    # Empty for public clients; SHA-256 of the secret for confidential ones.
    client_secret_hash = models.CharField(max_length=64, blank=True, default="")
    client_name = models.CharField(max_length=200, blank=True, default="")
    # Exact-match allowlist (OAuth 2.1 MUST): every authorize/token redirect_uri
    # is compared verbatim against this list — no prefix or wildcard matching.
    redirect_uris = models.JSONField(default=list)
    token_endpoint_auth_method = models.CharField(
        max_length=32,
        choices=AuthMethod.choices,
        default=AuthMethod.CLIENT_SECRET_BASIC,  # RFC 7591 default when omitted
    )
    grant_types = models.JSONField(
        default=list, help_text="Subset of {authorization_code, refresh_token}."
    )
    scope = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.client_name or '(unnamed)'} ({self.client_id[:8]}…)"

    @property
    def is_public(self) -> bool:
        return self.token_endpoint_auth_method == self.AuthMethod.NONE

    def verify_secret(self, raw_secret: str) -> bool:
        """Constant-time check of a presented client secret."""
        if not self.client_secret_hash or not raw_secret:
            return False
        return secrets.compare_digest(
            self.client_secret_hash, hash_token(raw_secret)
        )

    def redirect_uri_allowed(self, uri: str) -> bool:
        return bool(uri) and uri in self.redirect_uris


class OAuthAuthorizationCode(models.Model):
    """A single-use authorization code (OAuth 2.1 § 4.1) with its PKCE binding.

    The code itself is stored hashed. ``used_at`` is stamped on the FIRST
    exchange attempt — success or failure — so a stolen code cannot be
    brute-forced against the PKCE check by replaying it."""

    client = models.ForeignKey(
        OAuthClient, on_delete=models.CASCADE, related_name="authorization_codes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_oauth_codes",
    )
    code_hash = models.CharField(max_length=64, unique=True, db_index=True)
    redirect_uri = models.TextField()
    code_challenge = models.CharField(max_length=128)
    code_challenge_method = models.CharField(max_length=8, default="S256")
    scope = models.CharField(max_length=200, blank=True, default="")
    # RFC 8707 resource indicator from the authorize request; copied onto the
    # token so the audience the user consented to is the audience granted.
    resource = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"code for {self.user} via {self.client}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at


class OAuthToken(models.Model):
    """An issued access + refresh token pair, both stored hashed.

    Refresh rotation creates a NEW row and revokes the old one (rather than
    mutating in place) so the chain of grants stays auditable and "old refresh
    token no longer works" is a simple ``revoked_at`` check."""

    client = models.ForeignKey(
        OAuthClient, on_delete=models.CASCADE, related_name="tokens"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_oauth_tokens",
    )
    access_hashed = models.CharField(max_length=64, unique=True, db_index=True)
    refresh_hashed = models.CharField(max_length=64, unique=True, db_index=True)
    scope = models.CharField(max_length=200, blank=True, default="")
    resource = models.TextField(blank=True, default="")
    # The code this grant chain originated from. If that code is ever replayed
    # (used_at already set), every token descended from it is revoked — the
    # OAuth 2.1 stolen-code mitigation.
    authorization_code = models.ForeignKey(
        OAuthAuthorizationCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tokens",
    )
    access_expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"token for {self.user} via client {self.client_id}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    @classmethod
    def issue(
        cls,
        *,
        client: OAuthClient,
        user,
        scope: str = "",
        resource: str = "",
        authorization_code: OAuthAuthorizationCode | None = None,
    ) -> tuple["OAuthToken", str, str]:
        """Mint a new access/refresh pair. Returns (row, raw_access, raw_refresh);
        the raws go to the client, only hashes persist."""
        raw_access, access_hashed = generate_token()
        raw_refresh, refresh_hashed = generate_token()
        now = timezone.now()
        token = cls.objects.create(
            client=client,
            user=user,
            scope=scope,
            resource=resource,
            authorization_code=authorization_code,
            access_hashed=access_hashed,
            refresh_hashed=refresh_hashed,
            access_expires_at=now
            + timezone.timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS),
            refresh_expires_at=now
            + timezone.timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        )
        return token, raw_access, raw_refresh


def verify_access_token(raw: str) -> OAuthToken | None:
    """Resolve a presented Bearer token to its OAuthToken row.

    Returns None for unknown, revoked, or expired tokens — mirroring
    ``accounts.verify_key``'s contract (never reveal which failed). Refreshes
    ``last_used_at`` lazily (once per minute), same as the REST API-key path."""
    if not raw:
        return None
    token = (
        OAuthToken.objects.filter(
            access_hashed=hash_token(raw),
            revoked_at__isnull=True,
            user__is_active=True,
        )
        .select_related("user")
        .first()
    )
    if token is None:
        return None
    now = timezone.now()
    if now >= token.access_expires_at:
        return None
    if (
        token.last_used_at is None
        or (now - token.last_used_at).total_seconds() > 60
    ):
        OAuthToken.objects.filter(pk=token.pk).update(last_used_at=now)
    return token


def verify_refresh_token(raw: str) -> OAuthToken | None:
    """Resolve a presented refresh token to its (active, unexpired) row."""
    if not raw:
        return None
    token = (
        OAuthToken.objects.filter(
            refresh_hashed=hash_token(raw),
            revoked_at__isnull=True,
            user__is_active=True,
        )
        .select_related("user")
        .first()
    )
    if token is None or timezone.now() >= token.refresh_expires_at:
        return None
    return token
