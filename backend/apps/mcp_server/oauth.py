"""OAuth 2.0 authorization server endpoints for the MCP server.

The MCP spec (2025-06-18 authorization) models a remote MCP server as an
OAuth 2.1 resource server discovered via RFC 9728 Protected Resource Metadata,
with an authorization server discovered via RFC 8414. We co-host both roles:
these Django views ARE the authorization server (they own users, sessions, and
the login page), and the MCP ASGI app (apps/mcp_server/auth.py) is the
resource server that validates the issued Bearer tokens.

Endpoints (all rooted at the public domain — see apps/mcp_server/urls.py):

* ``GET /.well-known/oauth-authorization-server``  — RFC 8414 AS metadata
* ``GET /.well-known/oauth-protected-resource``    — RFC 9728 PRM (+ the
  ``/mcp`` path-inserted variants clients derive from the resource URL)
* ``POST /oauth/register``   — RFC 7591 Dynamic Client Registration
* ``GET/POST /oauth/authorize`` — authorization-code + PKCE (S256) consent
* ``POST /oauth/token``      — code exchange + refresh (with rotation)
* ``POST /oauth/revoke``     — RFC 7009 revocation

CSRF: ``register`` / ``token`` / ``revoke`` are machine-to-machine (no cookie,
no Origin) and are ``csrf_exempt`` — exactly the reasoning the REST API applies
to its ``X-API-Key`` routes (apps/api/session_auth.py). The ``authorize``
consent POST is a real browser form riding the Django session cookie, so it
keeps full CsrfViewMiddleware protection (the template embeds the token).

Tokens are opaque random bearers stored hashed (see models.py) — never JWTs —
so validation is one indexed lookup and revocation is immediate.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from urllib.parse import urlencode, urlsplit

from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import (
    AUTH_CODE_TTL_SECONDS,
    ACCESS_TOKEN_TTL_SECONDS,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthToken,
    generate_token,
    hash_token,
    verify_refresh_token,
)

SUPPORTED_AUTH_METHODS = {m.value for m in OAuthClient.AuthMethod}
SUPPORTED_GRANT_TYPES = {"authorization_code", "refresh_token"}
SUPPORTED_RESPONSE_TYPES = {"code"}
# One coarse scope: access to the MCP tool surface. Fine-grained entitlement
# stays where it already lives — the user's tier (apps/mcp_server/gating.py) —
# so the OAuth layer never becomes a second, conflicting permission system.
SUPPORTED_SCOPES = ["mcp"]

# RFC 7636 §4.1: code_verifier is 43–128 chars of [A-Za-z0-9-._~].
_VERIFIER_RE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


# ---------------------------------------------------------------------------
# Issuer / resource identity
# ---------------------------------------------------------------------------

def issuer(request: HttpRequest | None = None) -> str:
    """The authorization server's issuer identifier (RFC 8414).

    ``MCP_OAUTH_ISSUER`` pins it explicitly in prod (e.g.
    ``https://corpus.nick.law``); otherwise it derives from the request so dev
    servers and tests self-describe correctly. No trailing slash, ever — the
    metadata URLs and the canonical resource are built by concatenation."""
    configured = os.environ.get("MCP_OAUTH_ISSUER", "").strip()
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return request.build_absolute_uri("/").rstrip("/")
    return "http://localhost"


def canonical_resource(request: HttpRequest | None = None) -> str:
    """The MCP server's canonical resource URI (RFC 8707 / RFC 9728): the
    issuer origin plus the ``/mcp`` mount path."""
    return issuer(request) + "/mcp"


def _resource_matches(presented: str, request: HttpRequest) -> bool:
    """Audience check for the RFC 8707 ``resource`` parameter.

    Exact match against the canonical URI, tolerating only a trailing slash
    and case-insensitive scheme/host (both blessed by the MCP spec's
    robustness note)."""
    canonical = canonical_resource(request)

    def _norm(uri: str) -> str:
        parts = urlsplit(uri.rstrip("/"))
        return (
            f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path}"
        )

    try:
        return _norm(presented) == _norm(canonical)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Discovery metadata (RFC 8414 + RFC 9728)
# ---------------------------------------------------------------------------

@require_GET
def authorization_server_metadata(request: HttpRequest) -> JsonResponse:
    base = issuer(request)
    return JsonResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "registration_endpoint": f"{base}/oauth/register",
            "revocation_endpoint": f"{base}/oauth/revoke",
            "response_types_supported": sorted(SUPPORTED_RESPONSE_TYPES),
            "grant_types_supported": sorted(SUPPORTED_GRANT_TYPES),
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": sorted(
                SUPPORTED_AUTH_METHODS
            ),
            "revocation_endpoint_auth_methods_supported": sorted(
                SUPPORTED_AUTH_METHODS
            ),
            "scopes_supported": SUPPORTED_SCOPES,
        }
    )


@require_GET
def protected_resource_metadata(request: HttpRequest) -> JsonResponse:
    base = issuer(request)
    return JsonResponse(
        {
            "resource": canonical_resource(request),
            "authorization_servers": [base],
            "scopes_supported": SUPPORTED_SCOPES,
            "bearer_methods_supported": ["header"],
            "resource_name": "Iowa Legal Corpus MCP Server",
        }
    )


# ---------------------------------------------------------------------------
# Dynamic Client Registration (RFC 7591)
# ---------------------------------------------------------------------------

def _valid_redirect_uri(uri: str) -> bool:
    """OAuth 2.1 MUST: redirect URIs are HTTPS or loopback. No fragments."""
    if not isinstance(uri, str) or "#" in uri:
        return False
    try:
        parts = urlsplit(uri)
    except ValueError:
        return False
    if not parts.netloc:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and parts.hostname in (
        "localhost",
        "127.0.0.1",
        "::1",
    )


def _registration_error(description: str, code: str = "invalid_client_metadata"):
    return JsonResponse(
        {"error": code, "error_description": description}, status=400
    )


@csrf_exempt
@require_http_methods(["POST"])
def register(request: HttpRequest) -> JsonResponse:
    """RFC 7591 dynamic registration. Open by design — a client row is only a
    name + redirect-URI allowlist; a user must still consent before any token
    exists, so open registration grants nothing by itself."""
    try:
        meta = json.loads(request.body or b"{}")
        if not isinstance(meta, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return _registration_error("request body must be a JSON object")

    redirect_uris = meta.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        return _registration_error(
            "redirect_uris is required and must be a non-empty array",
            code="invalid_redirect_uri",
        )
    for uri in redirect_uris:
        if not _valid_redirect_uri(uri):
            return _registration_error(
                f"redirect_uri must be HTTPS or loopback: {uri!r}",
                code="invalid_redirect_uri",
            )

    auth_method = meta.get(
        "token_endpoint_auth_method",
        OAuthClient.AuthMethod.CLIENT_SECRET_BASIC,
    )
    if auth_method not in SUPPORTED_AUTH_METHODS:
        return _registration_error(
            f"unsupported token_endpoint_auth_method: {auth_method!r}"
        )

    grant_types = meta.get("grant_types") or ["authorization_code"]
    if not set(grant_types) <= SUPPORTED_GRANT_TYPES:
        return _registration_error(
            f"unsupported grant_types: {sorted(set(grant_types) - SUPPORTED_GRANT_TYPES)}"
        )

    response_types = meta.get("response_types") or ["code"]
    if not set(response_types) <= SUPPORTED_RESPONSE_TYPES:
        return _registration_error(
            f"unsupported response_types: {response_types!r}"
        )

    client_name = meta.get("client_name") or ""
    if not isinstance(client_name, str):
        return _registration_error("client_name must be a string")

    scope = meta.get("scope") or ""

    raw_secret = ""
    secret_hash = ""
    if auth_method != OAuthClient.AuthMethod.NONE:
        raw_secret, secret_hash = generate_token()

    client = OAuthClient.objects.create(
        client_id=secrets.token_urlsafe(24),
        client_secret_hash=secret_hash,
        client_name=client_name[:200],
        redirect_uris=redirect_uris,
        token_endpoint_auth_method=auth_method,
        grant_types=sorted(set(grant_types) | {"refresh_token"}),
        scope=scope[:200] if isinstance(scope, str) else "",
    )

    body = {
        "client_id": client.client_id,
        "client_id_issued_at": int(client.created_at.timestamp()),
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
        "grant_types": client.grant_types,
        "response_types": ["code"],
        "scope": client.scope,
    }
    if raw_secret:
        body["client_secret"] = raw_secret
        body["client_secret_expires_at"] = 0  # never expires
    return JsonResponse(body, status=201)


# ---------------------------------------------------------------------------
# Authorization endpoint (code + PKCE, session-login consent)
# ---------------------------------------------------------------------------

_AUTHORIZE_PARAMS = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "code_challenge",
    "code_challenge_method",
    "resource",
)


def _error_page(request, description: str, status: int = 400) -> HttpResponse:
    """Render (never redirect) when client_id / redirect_uri can't be trusted —
    redirecting to an unvalidated URI would be an open redirect."""
    return render(
        request,
        "mcp_server/oauth_error.html",
        {"description": description},
        status=status,
    )


def _redirect_error(
    redirect_uri: str, error: str, description: str, state: str
) -> HttpResponse:
    params = {"error": error, "error_description": description}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    resp = HttpResponse(status=302)
    resp["Location"] = f"{redirect_uri}{sep}{urlencode(params)}"
    return resp


def _validate_authorize_params(request, params: dict):
    """Shared GET/POST validation. Returns (client, error_response) — exactly
    one is non-None. Anything wrong before redirect_uri is proven registered
    renders an error page; after that, errors redirect back to the client."""
    client = OAuthClient.objects.filter(
        client_id=params.get("client_id", "")
    ).first()
    if client is None:
        return None, _error_page(request, "Unknown client_id.")

    redirect_uri = params.get("redirect_uri", "")
    if not redirect_uri:
        # RFC 6749 §3.1.2.3: may be omitted only when exactly one is registered.
        if len(client.redirect_uris) == 1:
            params["redirect_uri"] = redirect_uri = client.redirect_uris[0]
        else:
            return None, _error_page(request, "redirect_uri is required.")
    if not client.redirect_uri_allowed(redirect_uri):
        return None, _error_page(
            request, "redirect_uri is not registered for this client."
        )

    state = params.get("state", "")
    if params.get("response_type") != "code":
        return None, _redirect_error(
            redirect_uri,
            "unsupported_response_type",
            "only response_type=code is supported",
            state,
        )
    if not params.get("code_challenge"):
        return None, _redirect_error(
            redirect_uri,
            "invalid_request",
            "code_challenge is required (PKCE)",
            state,
        )
    if params.get("code_challenge_method", "S256") != "S256":
        return None, _redirect_error(
            redirect_uri,
            "invalid_request",
            "only code_challenge_method=S256 is supported",
            state,
        )
    resource = params.get("resource", "")
    if resource and not _resource_matches(resource, request):
        return None, _redirect_error(
            redirect_uri,
            "invalid_target",
            "resource does not identify this MCP server",
            state,
        )
    requested = (params.get("scope") or "").split()
    if any(s not in SUPPORTED_SCOPES for s in requested):
        return None, _redirect_error(
            redirect_uri, "invalid_scope", "unsupported scope requested", state
        )
    return client, None


@require_http_methods(["GET", "POST"])
def authorize(request: HttpRequest) -> HttpResponse:
    """The user-facing half of the flow.

    GET: validate the request, then show the logged-in user a consent page
    (or bounce through the existing sign-in with ``?next=`` back here — the
    session login the whole app already uses; no second credential system).

    POST: the consent form. CSRF-protected (session-cookie surface), user must
    be logged in, and every parameter is re-validated from the form — a
    tampered hidden field must not bypass the GET-side checks."""
    source = request.GET if request.method == "GET" else request.POST
    params = {name: source.get(name, "").strip() for name in _AUTHORIZE_PARAMS}

    client, error = _validate_authorize_params(request, params)
    if error is not None:
        return error

    if not request.user.is_authenticated:
        # Reuse the app's own sign-in. redirect_to_login carries the full
        # authorize URL (with all OAuth params) in ?next= so the login page
        # can land the user back here to consent.
        return redirect_to_login(request.get_full_path())

    if request.method == "GET":
        return render(
            request,
            "mcp_server/oauth_authorize.html",
            {
                "client": client,
                "params": params,
                "scope_display": params["scope"] or "mcp",
                "user": request.user,
            },
        )

    state = params["state"]
    if request.POST.get("action") != "approve":
        return _redirect_error(
            params["redirect_uri"],
            "access_denied",
            "the user denied the request",
            state,
        )

    raw_code, code_hash = generate_token()
    OAuthAuthorizationCode.objects.create(
        client=client,
        user=request.user,
        code_hash=code_hash,
        redirect_uri=params["redirect_uri"],
        code_challenge=params["code_challenge"],
        code_challenge_method="S256",
        scope=params["scope"] or "mcp",
        resource=params["resource"],
        expires_at=timezone.now()
        + timezone.timedelta(seconds=AUTH_CODE_TTL_SECONDS),
    )
    out = {"code": raw_code}
    if state:
        out["state"] = state
    sep = "&" if "?" in params["redirect_uri"] else "?"
    resp = HttpResponse(status=302)
    resp["Location"] = f"{params['redirect_uri']}{sep}{urlencode(out)}"
    return resp


# ---------------------------------------------------------------------------
# Token endpoint (code exchange + refresh rotation)
# ---------------------------------------------------------------------------

def _token_error(
    error: str, description: str, status: int = 400
) -> JsonResponse:
    resp = JsonResponse(
        {"error": error, "error_description": description}, status=status
    )
    resp["Cache-Control"] = "no-store"
    return resp


def _authenticate_client(request: HttpRequest):
    """Resolve + authenticate the client for the token/revocation endpoints.

    Supports HTTP Basic (client_secret_basic), POST-body secret
    (client_secret_post), and bare client_id for public (``none``) clients.
    Returns (client, error_response) — exactly one is non-None."""
    client_id = request.POST.get("client_id", "")
    secret = request.POST.get("client_secret", "")

    header = request.headers.get("Authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            basic_id, _, basic_secret = decoded.partition(":")
        except (ValueError, UnicodeDecodeError):
            return None, _token_error(
                "invalid_client", "malformed Basic authorization header", 401
            )
        client_id, secret = basic_id, basic_secret

    client = OAuthClient.objects.filter(client_id=client_id).first()
    if client is None:
        return None, _token_error("invalid_client", "unknown client", 401)
    if client.is_public:
        return client, None
    if not client.verify_secret(secret):
        return None, _token_error(
            "invalid_client", "client authentication failed", 401
        )
    return client, None


def _verify_pkce(verifier: str, challenge: str) -> bool:
    if not _VERIFIER_RE.match(verifier or ""):
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, challenge)


@csrf_exempt
@require_http_methods(["POST"])
def token(request: HttpRequest) -> JsonResponse:
    client, error = _authenticate_client(request)
    if error is not None:
        return error

    grant_type = request.POST.get("grant_type", "")

    if grant_type == "authorization_code":
        return _token_authorization_code(request, client)
    if grant_type == "refresh_token":
        return _token_refresh(request, client)
    return _token_error(
        "unsupported_grant_type",
        "grant_type must be authorization_code or refresh_token",
    )


def _token_success(token_row, raw_access, raw_refresh) -> JsonResponse:
    resp = JsonResponse(
        {
            "access_token": raw_access,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "refresh_token": raw_refresh,
            "scope": token_row.scope,
        }
    )
    # RFC 6749 §5.1: token responses carry credentials; never cache them.
    resp["Cache-Control"] = "no-store"
    resp["Pragma"] = "no-cache"
    return resp


def _token_authorization_code(request, client) -> JsonResponse:
    raw_code = request.POST.get("code", "")
    if not raw_code:
        return _token_error("invalid_request", "code is required")

    code = (
        OAuthAuthorizationCode.objects.filter(code_hash=hash_token(raw_code))
        .select_related("client", "user")
        .first()
    )
    if code is None or code.client_id != client.pk:
        return _token_error("invalid_grant", "unknown authorization code")

    if code.used_at is not None:
        # Replay of a consumed code — the OAuth 2.1 stolen-code signal. Revoke
        # every token descended from it so the attacker AND the legitimate
        # holder both lose access (the user just re-consents).
        now = timezone.now()
        code.tokens.filter(revoked_at__isnull=True).update(revoked_at=now)
        return _token_error("invalid_grant", "authorization code already used")

    # Single attempt: burn the code BEFORE the PKCE check so a stolen code
    # cannot be retried against a dictionary of verifiers.
    code.used_at = timezone.now()
    code.save(update_fields=["used_at"])

    if code.is_expired:
        return _token_error("invalid_grant", "authorization code expired")

    redirect_uri = request.POST.get("redirect_uri", "")
    if redirect_uri != code.redirect_uri:
        return _token_error("invalid_grant", "redirect_uri mismatch")

    if not _verify_pkce(request.POST.get("code_verifier", ""), code.code_challenge):
        return _token_error("invalid_grant", "PKCE verification failed")

    resource = request.POST.get("resource", "")
    if resource and not _resource_matches(resource, request):
        return _token_error(
            "invalid_target", "resource does not identify this MCP server"
        )

    row, raw_access, raw_refresh = OAuthToken.issue(
        client=client,
        user=code.user,
        scope=code.scope,
        resource=code.resource or resource,
        authorization_code=code,
    )
    return _token_success(row, raw_access, raw_refresh)


def _token_refresh(request, client) -> JsonResponse:
    old = verify_refresh_token(request.POST.get("refresh_token", ""))
    if old is None or old.client_id != client.pk:
        return _token_error(
            "invalid_grant", "invalid, expired, or rotated refresh token"
        )

    # Rotation (OAuth 2.1 MUST for public clients): the presented refresh token
    # dies now; a fresh pair replaces it. New row rather than in-place update
    # keeps the grant chain auditable.
    old.revoke()
    row, raw_access, raw_refresh = OAuthToken.issue(
        client=client,
        user=old.user,
        scope=old.scope,
        resource=old.resource,
        authorization_code=old.authorization_code,
    )
    return _token_success(row, raw_access, raw_refresh)


# ---------------------------------------------------------------------------
# Revocation (RFC 7009)
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
def revoke(request: HttpRequest) -> HttpResponse:
    client, error = _authenticate_client(request)
    if error is not None:
        return error

    raw = request.POST.get("token", "")
    if raw:
        hashed = hash_token(raw)
        # token_type_hint is only a hint (RFC 7009 §2.1) — check both columns.
        row = OAuthToken.objects.filter(
            Q(access_hashed=hashed) | Q(refresh_hashed=hashed), client=client
        ).first()
        if row is not None:
            row.revoke()
    # RFC 7009 §2.2: 200 even for unknown/foreign tokens — never an oracle.
    return HttpResponse(status=200)
