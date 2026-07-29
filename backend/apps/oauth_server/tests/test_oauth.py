"""OAuth 2.0 authorization server + Bearer resource-server tests.

Covers the whole MCP-spec authorization surface end to end:

* discovery metadata shapes (RFC 8414 + RFC 9728, incl. the /mcp variants)
* dynamic client registration (RFC 7591)
* the full PKCE happy path: register → consent (session login) → code →
  token → an authenticated MCP call with the Bearer token
* the failure modes that carry the security weight: bad PKCE verifier,
  code replay (revokes descendants), refresh rotation (old refresh dies),
  revocation (RFC 7009), expired access tokens, CSRF on the consent POST,
  unregistered redirect_uri (rendered, never redirected)
* backward compatibility: X-API-Key still authenticates the MCP transport

These hit the DB (real ``TestCase``), unlike the middleware contract tests in
``test_auth_middleware`` which patch ``verify_key``. The ASGI middleware is
driven through ``async_to_sync`` so its ``sync_to_async(thread_sensitive=True)``
DB calls run on the test's main thread and see the open test transaction —
the same mechanics the tool tests rely on.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlsplit

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import APIKey, generate_key
from apps.mcp_server.auth import BearerPrincipal, api_key_middleware
from apps.oauth_server.models import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthToken,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# ASGI plumbing (mirrors test_auth_middleware, plus response-header capture)
# ---------------------------------------------------------------------------

class _RecorderApp:
    """Minimal inner ASGI app: records scopes, returns 204."""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)
        await send(
            {"type": "http.response.start", "status": 204, "headers": []}
        )
        await send(
            {"type": "http.response.body", "body": b"", "more_body": False}
        )


def _drive(app, headers, body: bytes = b"{}"):
    """Run one request through the ASGI app; return (status, body, headers).

    ``async_to_sync`` (not a bare event loop) so thread_sensitive DB work in
    the middleware executes on this thread, inside the test transaction."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "headers": headers,
    }
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    captured = {"status": None, "body": b"", "headers": {}}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = {
                name.decode("latin-1"): value.decode("latin-1")
                for name, value in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    async def go():
        await app(scope, receive, send)

    async_to_sync(go)()
    return captured["status"], captured["body"], captured["headers"]


# ---------------------------------------------------------------------------
# Shared OAuth-flow helpers
# ---------------------------------------------------------------------------

REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)  # 64 chars, RFC 7636 charset
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OAuthFlowMixin:
    """Register a client + run the authorize/token legs; used by most cases."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="attorney@example.com", password="correct-horse-battery"
        )

    def register_client(self, auth_method="none", **extra):
        payload = {
            "client_name": "Claude",
            "redirect_uris": [REDIRECT_URI],
            "token_endpoint_auth_method": auth_method,
            "grant_types": ["authorization_code", "refresh_token"],
            **extra,
        }
        resp = self.client.post(
            "/oauth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()

    def authorize_params(self, client_id, challenge, **overrides):
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": "mcp",
            "state": "xyz123",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": "http://testserver/mcp",
        }
        params.update(overrides)
        return params

    def obtain_code(self, client_id, challenge, **overrides):
        """Login + consent; returns the authorization code from the redirect."""
        self.client.force_login(self.user)
        params = self.authorize_params(client_id, challenge, **overrides)
        resp = self.client.post(
            "/oauth/authorize", data={**params, "action": "approve"}
        )
        self.assertEqual(resp.status_code, 302, getattr(resp, "content", b""))
        location = resp["Location"]
        self.assertTrue(location.startswith(REDIRECT_URI), location)
        query = parse_qs(urlsplit(location).query)
        self.assertEqual(query.get("state"), ["xyz123"])
        return query["code"][0]

    def exchange_code(self, client_id, code, verifier, **overrides):
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "resource": "http://testserver/mcp",
        }
        data.update(overrides)
        return self.client.post("/oauth/token", data=data)

    def issue_tokens(self):
        """Full register→authorize→token run; returns the token response dict."""
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        code = self.obtain_code(reg["client_id"], challenge)
        resp = self.exchange_code(reg["client_id"], code, verifier)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        body["client_id"] = reg["client_id"]
        return body

    def _entitle(self):
        """Give the flow's user a plan that includes ``edms``.

        Since the paywall moved to token issuance, minting an edms token needs
        an entitled user. These tests are about scope boundaries, not billing,
        so they say so explicitly rather than depending on the default tier."""
        self.user.tier = "solo"
        self.user.save(update_fields=["tier"])

    def _seed_first_party_client(self, scope="edms"):
        """The row ``manage.py seed_edms_oauth_client`` writes: created
        directly, deliberately never through the open /oauth/register.

        Upserts, like the command it stands in for, so a test may drive the
        authorize flow more than once."""
        client, _ = OAuthClient.objects.update_or_create(
            client_id="hudson-edmspro-extension",
            defaults={
                "client_secret_hash": "",
                "client_name": "Hudson EDMSpro",
                "redirect_uris": [REDIRECT_URI],
                "token_endpoint_auth_method": OAuthClient.AuthMethod.NONE,
                "grant_types": ["authorization_code", "refresh_token"],
                "scope": scope,
            },
        )
        return client


# ---------------------------------------------------------------------------
# Discovery metadata
# ---------------------------------------------------------------------------

class MetadataTests(TestCase):
    def test_authorization_server_metadata_shape(self):
        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-authorization-server/mcp",
        ):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200)
                meta = resp.json()
                issuer = meta["issuer"]
                self.assertFalse(issuer.endswith("/"))
                self.assertEqual(
                    meta["authorization_endpoint"], f"{issuer}/oauth/authorize"
                )
                self.assertEqual(meta["token_endpoint"], f"{issuer}/oauth/token")
                self.assertEqual(
                    meta["registration_endpoint"], f"{issuer}/oauth/register"
                )
                self.assertEqual(
                    meta["revocation_endpoint"], f"{issuer}/oauth/revoke"
                )
                self.assertEqual(meta["response_types_supported"], ["code"])
                self.assertEqual(
                    meta["grant_types_supported"],
                    ["authorization_code", "refresh_token"],
                )
                self.assertEqual(
                    meta["code_challenge_methods_supported"], ["S256"]
                )
                self.assertIn(
                    "none", meta["token_endpoint_auth_methods_supported"]
                )

    def test_protected_resource_metadata_points_at_authorization_server(self):
        for path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200)
                meta = resp.json()
                self.assertTrue(meta["resource"].endswith("/mcp"))
                self.assertEqual(len(meta["authorization_servers"]), 1)
                # The advertised AS must be the issuer whose RFC 8414 document
                # we serve — that's the discovery chain Claude walks.
                self.assertEqual(
                    meta["resource"], meta["authorization_servers"][0] + "/mcp"
                )
                self.assertEqual(meta["bearer_methods_supported"], ["header"])

    def test_issuer_env_override(self):
        import os
        from unittest.mock import patch as env_patch

        with env_patch.dict(
            os.environ, {"MCP_OAUTH_ISSUER": "https://app.hudsonlegal.tech/"}
        ):
            meta = self.client.get(
                "/.well-known/oauth-authorization-server"
            ).json()
        self.assertEqual(meta["issuer"], "https://app.hudsonlegal.tech")
        self.assertEqual(
            meta["token_endpoint"], "https://app.hudsonlegal.tech/oauth/token"
        )


# ---------------------------------------------------------------------------
# Dynamic Client Registration (RFC 7591)
# ---------------------------------------------------------------------------

class RegistrationTests(TestCase):
    def _register(self, payload):
        return self.client.post(
            "/oauth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_public_client_registration(self):
        resp = self._register(
            {
                "client_name": "Claude",
                "redirect_uris": [REDIRECT_URI],
                "token_endpoint_auth_method": "none",
            }
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("client_id", body)
        self.assertNotIn("client_secret", body)  # public: PKCE only
        row = OAuthClient.objects.get(client_id=body["client_id"])
        self.assertTrue(row.is_public)
        self.assertEqual(row.redirect_uris, [REDIRECT_URI])
        # refresh_token is always granted alongside authorization_code.
        self.assertIn("refresh_token", body["grant_types"])

    def test_confidential_client_gets_secret_stored_hashed(self):
        resp = self._register(
            {
                "redirect_uris": [REDIRECT_URI],
                "token_endpoint_auth_method": "client_secret_post",
            }
        )
        body = resp.json()
        self.assertIn("client_secret", body)
        self.assertEqual(body["client_secret_expires_at"], 0)
        row = OAuthClient.objects.get(client_id=body["client_id"])
        # Never the raw secret in the DB.
        self.assertNotEqual(row.client_secret_hash, body["client_secret"])
        self.assertTrue(row.verify_secret(body["client_secret"]))

    def test_missing_redirect_uris_rejected(self):
        resp = self._register({"client_name": "no uris"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_redirect_uri")

    def test_non_https_redirect_uri_rejected_but_loopback_allowed(self):
        bad = self._register({"redirect_uris": ["http://evil.example.com/cb"]})
        self.assertEqual(bad.status_code, 400)
        ok = self._register({"redirect_uris": ["http://localhost:33418/cb"]})
        self.assertEqual(ok.status_code, 201)

    def test_unsupported_grant_type_rejected(self):
        resp = self._register(
            {
                "redirect_uris": [REDIRECT_URI],
                "grant_types": ["client_credentials"],
            }
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_client_metadata")


# ---------------------------------------------------------------------------
# Authorization endpoint
# ---------------------------------------------------------------------------

class AuthorizeTests(OAuthFlowMixin, TestCase):
    def test_logged_out_redirects_through_login_with_next(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params(reg["client_id"], challenge),
        )
        self.assertEqual(resp.status_code, 302)
        # settings.LOGIN_URL is the SPA sign-in at "/"; ?next= carries the
        # full authorize URL so login lands the user back on consent.
        self.assertTrue(resp["Location"].startswith("/?next=/oauth/authorize"))
        # The OAuth params ride inside next= so consent resumes losslessly.
        self.assertIn("code_challenge%3D", resp["Location"])

    def test_logged_in_get_renders_consent_page(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        self.client.force_login(self.user)
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params(reg["client_id"], challenge),
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Claude", content)
        self.assertIn("csrfmiddlewaretoken", content)
        self.assertIn(challenge, content)  # carried through as hidden field

    def test_unknown_client_renders_error_never_redirects(self):
        verifier, challenge = _pkce_pair()
        self.client.force_login(self.user)
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params("nope-not-registered", challenge),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("Location", resp)

    def test_unregistered_redirect_uri_renders_error_never_redirects(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        self.client.force_login(self.user)
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params(
                reg["client_id"],
                challenge,
                redirect_uri="https://attacker.example.com/cb",
            ),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("Location", resp)

    def test_missing_code_challenge_redirects_invalid_request(self):
        reg = self.register_client()
        self.client.force_login(self.user)
        params = self.authorize_params(reg["client_id"], "", code_challenge="")
        resp = self.client.get("/oauth/authorize", data=params)
        self.assertEqual(resp.status_code, 302)
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["invalid_request"])
        self.assertEqual(query["state"], ["xyz123"])

    def test_plain_challenge_method_rejected(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        self.client.force_login(self.user)
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params(
                reg["client_id"], challenge, code_challenge_method="plain"
            ),
        )
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["invalid_request"])

    def test_foreign_resource_redirects_invalid_target(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        self.client.force_login(self.user)
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params(
                reg["client_id"],
                challenge,
                resource="https://some-other-server.example.com/mcp",
            ),
        )
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["invalid_target"])

    def test_deny_redirects_access_denied_and_mints_nothing(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        self.client.force_login(self.user)
        params = self.authorize_params(reg["client_id"], challenge)
        resp = self.client.post(
            "/oauth/authorize", data={**params, "action": "deny"}
        )
        self.assertEqual(resp.status_code, 302)
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["access_denied"])
        self.assertEqual(OAuthAuthorizationCode.objects.count(), 0)

    def test_consent_post_requires_csrf_token(self):
        """The consent POST is the one browser-facing state change in the flow;
        it must keep CsrfViewMiddleware protection (unlike the machine
        endpoints, which are csrf_exempt)."""
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        params = self.authorize_params(reg["client_id"], challenge)
        resp = strict.post(
            "/oauth/authorize", data={**params, "action": "approve"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(OAuthAuthorizationCode.objects.count(), 0)

    def test_consent_post_requires_login(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        params = self.authorize_params(reg["client_id"], challenge)
        resp = self.client.post(
            "/oauth/authorize", data={**params, "action": "approve"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/?next="))
        self.assertEqual(OAuthAuthorizationCode.objects.count(), 0)


# ---------------------------------------------------------------------------
# Token endpoint + the full PKCE happy path through the MCP transport
# ---------------------------------------------------------------------------

class TokenFlowTests(OAuthFlowMixin, TestCase):
    def test_full_pkce_flow_and_bearer_mcp_call(self):
        """register → authorize (logged-in consent) → code → token → MCP call."""
        tokens = self.issue_tokens()
        self.assertEqual(tokens["token_type"], "Bearer")
        self.assertEqual(tokens["expires_in"], 3600)
        self.assertIn("refresh_token", tokens)
        self.assertEqual(tokens["scope"], "mcp")

        # Only hashes in the DB.
        row = OAuthToken.objects.get()
        self.assertNotEqual(row.access_hashed, tokens["access_token"])
        self.assertEqual(row.user, self.user)

        # The Bearer token authenticates the MCP ASGI transport.
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, _, _ = _drive(
            app,
            headers=[
                (
                    b"authorization",
                    f"Bearer {tokens['access_token']}".encode(),
                ),
                (b"host", b"testserver"),
            ],
        )
        self.assertEqual(status, 204)
        principal = recorder.calls[0]["mcp_api_key"]
        self.assertIsInstance(principal, BearerPrincipal)
        # Scoped to the consenting user — the existing per-user entitlement
        # (tier features + quota) reads .user off this, same as an APIKey.
        self.assertEqual(principal.user, self.user)

    def test_bearer_token_flows_through_tier_gating(self):
        """Requirement: reuse the per-user entitlement the API-key path applies.
        A FREE-tier user's token may search but NOT call the paid validate
        tools — same 403 the REST tiers produce."""
        tokens = self.issue_tokens()
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        headers = [
            (b"authorization", f"Bearer {tokens['access_token']}".encode()),
            (b"host", b"testserver"),
        ]

        def call(tool):
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": {}},
                }
            ).encode()
            return _drive(app, headers=headers, body=body)

        status, _, _ = call("search_statutes")  # free tier includes search
        self.assertEqual(status, 204)
        status, body, _ = call("validate_citations")  # SOLO+ feature
        self.assertEqual(status, 403)
        self.assertIn(b"free", body)

    def test_bad_pkce_verifier_rejected_and_code_burned(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        code = self.obtain_code(reg["client_id"], challenge)

        wrong = self.exchange_code(
            reg["client_id"], code, secrets.token_urlsafe(48)
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json()["error"], "invalid_grant")
        self.assertEqual(OAuthToken.objects.count(), 0)

        # Single attempt: the failed exchange consumed the code, so even the
        # CORRECT verifier is refused now (anti-brute-force).
        retry = self.exchange_code(reg["client_id"], code, verifier)
        self.assertEqual(retry.status_code, 400)
        self.assertEqual(retry.json()["error"], "invalid_grant")

    def test_code_replay_revokes_issued_tokens(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        code = self.obtain_code(reg["client_id"], challenge)
        first = self.exchange_code(reg["client_id"], code, verifier)
        self.assertEqual(first.status_code, 200)

        replay = self.exchange_code(reg["client_id"], code, verifier)
        self.assertEqual(replay.status_code, 400)
        # OAuth 2.1 stolen-code mitigation: the tokens minted from the replayed
        # code are revoked, cutting off whoever exchanged it first.
        row = OAuthToken.objects.get()
        self.assertIsNotNone(row.revoked_at)

    def test_expired_code_rejected(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        code = self.obtain_code(reg["client_id"], challenge)
        OAuthAuthorizationCode.objects.update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        resp = self.exchange_code(reg["client_id"], code, verifier)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_grant")

    def test_redirect_uri_mismatch_at_token_rejected(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        code = self.obtain_code(reg["client_id"], challenge)
        resp = self.exchange_code(
            reg["client_id"],
            code,
            verifier,
            redirect_uri="https://claude.ai/other_callback",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_grant")

    def test_confidential_client_must_authenticate(self):
        verifier, challenge = _pkce_pair()
        reg = self.register_client(auth_method="client_secret_post")
        code = self.obtain_code(reg["client_id"], challenge)

        no_secret = self.exchange_code(reg["client_id"], code, verifier)
        self.assertEqual(no_secret.status_code, 401)
        self.assertEqual(no_secret.json()["error"], "invalid_client")

        # The failed attempt never touched the code (client auth precedes
        # grant processing), so the authenticated retry succeeds.
        ok = self.exchange_code(
            reg["client_id"],
            code,
            verifier,
            client_secret=reg["client_secret"],
        )
        self.assertEqual(ok.status_code, 200, ok.content)

    def test_refresh_rotation_old_refresh_token_dies(self):
        tokens = self.issue_tokens()

        refreshed = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": tokens["client_id"],
                "refresh_token": tokens["refresh_token"],
            },
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        new = refreshed.json()
        self.assertNotEqual(new["access_token"], tokens["access_token"])
        self.assertNotEqual(new["refresh_token"], tokens["refresh_token"])
        self.assertEqual(new["scope"], "mcp")

        # Immediately after a clean rotation (no reuse yet): the NEW access token
        # works and the OLD one — whose row the rotation revoked — does not.
        self.assertEqual(self._bearer_status(new["access_token"]), 204)
        self.assertEqual(self._bearer_status(tokens["access_token"]), 401)

    def _bearer_status(self, access_token):
        status, _, _ = _drive(
            api_key_middleware(_RecorderApp()),
            headers=[
                (b"authorization", f"Bearer {access_token}".encode()),
                (b"host", b"testserver"),
            ],
        )
        return status

    def test_refresh_reuse_revokes_the_whole_token_family(self):
        # OAuth 2.1 §6.1 reuse detection: presenting an already-rotated refresh
        # token is the stolen-token signal, so it must fail AND revoke every token
        # descended from the same authorization — including the live tokens the
        # legitimate client just received — forcing re-consent. (The auth-code
        # replay path already did this; the refresh path now matches it.)
        tokens = self.issue_tokens()
        refreshed = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": tokens["client_id"],
                "refresh_token": tokens["refresh_token"],
            },
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        new = refreshed.json()

        # The freshly-minted access token is live until the reuse is detected.
        self.assertEqual(self._bearer_status(new["access_token"]), 204)

        # Replay the OLD (already-rotated) refresh token — the reuse signal.
        again = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": tokens["client_id"],
                "refresh_token": tokens["refresh_token"],
            },
        )
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["error"], "invalid_grant")

        # Reuse detection has now revoked the whole family: the NEW access token
        # AND the NEW refresh token are both dead.
        self.assertEqual(self._bearer_status(new["access_token"]), 401)
        replay_new = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": tokens["client_id"],
                "refresh_token": new["refresh_token"],
            },
        )
        self.assertEqual(replay_new.status_code, 400)
        self.assertEqual(replay_new.json()["error"], "invalid_grant")

    def test_unsupported_grant_type(self):
        reg = self.register_client()
        resp = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": reg["client_id"],
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "unsupported_grant_type")

    def test_token_response_is_uncacheable(self):
        tokens_resp = None
        verifier, challenge = _pkce_pair()
        reg = self.register_client()
        code = self.obtain_code(reg["client_id"], challenge)
        tokens_resp = self.exchange_code(reg["client_id"], code, verifier)
        self.assertEqual(tokens_resp["Cache-Control"], "no-store")


# ---------------------------------------------------------------------------
# Revocation (RFC 7009)
# ---------------------------------------------------------------------------

class RevocationTests(OAuthFlowMixin, TestCase):
    def test_revoked_access_token_stops_authenticating(self):
        tokens = self.issue_tokens()
        resp = self.client.post(
            "/oauth/revoke",
            data={
                "client_id": tokens["client_id"],
                "token": tokens["access_token"],
                "token_type_hint": "access_token",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(OAuthToken.objects.get().revoked_at)

        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, _, _ = _drive(
            app,
            headers=[
                (b"authorization", f"Bearer {tokens['access_token']}".encode()),
                (b"host", b"testserver"),
            ],
        )
        self.assertEqual(status, 401)

    def test_revoke_by_refresh_token_and_unknown_token_returns_200(self):
        tokens = self.issue_tokens()
        # Unknown token: still 200 (RFC 7009 §2.2 — no oracle), nothing revoked.
        resp = self.client.post(
            "/oauth/revoke",
            data={"client_id": tokens["client_id"], "token": "not-a-token"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(OAuthToken.objects.get().revoked_at)
        # Refresh token revokes the pair.
        resp = self.client.post(
            "/oauth/revoke",
            data={
                "client_id": tokens["client_id"],
                "token": tokens["refresh_token"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(OAuthToken.objects.get().revoked_at)

    def test_foreign_clients_token_not_revocable(self):
        tokens = self.issue_tokens()
        other = self.register_client(client_name="Other client")
        resp = self.client.post(
            "/oauth/revoke",
            data={
                "client_id": other["client_id"],
                "token": tokens["access_token"],
            },
        )
        # 200 per the RFC, but the token (owned by another client) survives.
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(OAuthToken.objects.get().revoked_at)


# ---------------------------------------------------------------------------
# Resource-server behavior on the MCP transport
# ---------------------------------------------------------------------------

class BearerTransportTests(OAuthFlowMixin, TestCase):
    def test_expired_access_token_401s_with_www_authenticate(self):
        tokens = self.issue_tokens()
        OAuthToken.objects.update(
            access_expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, body, headers = _drive(
            app,
            headers=[
                (b"authorization", f"Bearer {tokens['access_token']}".encode()),
                (b"host", b"testserver"),
            ],
        )
        self.assertEqual(status, 401)
        self.assertIn(b"invalid, expired, or revoked", body)
        self.assertIn('error="invalid_token"', headers["www-authenticate"])
        self.assertIn(
            "/.well-known/oauth-protected-resource/mcp",
            headers["www-authenticate"],
        )
        self.assertEqual(recorder.calls, [])

    def test_missing_credentials_401_advertises_resource_metadata(self):
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, _, headers = _drive(
            app, headers=[(b"host", b"app.hudsonlegal.tech")]
        )
        self.assertEqual(status, 401)
        self.assertEqual(
            headers["www-authenticate"],
            'Bearer resource_metadata='
            '"https://app.hudsonlegal.tech/.well-known/oauth-protected-resource/mcp"',
        )

    def test_garbage_bearer_does_not_fall_through_to_api_key(self):
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, _, headers = _drive(
            app,
            headers=[
                (b"authorization", b"Bearer nonsense-token"),
                (b"host", b"testserver"),
            ],
        )
        self.assertEqual(status, 401)
        self.assertIn('error="invalid_token"', headers["www-authenticate"])
        self.assertEqual(recorder.calls, [])

    def test_x_api_key_still_works(self):
        """Backward compatibility: the pre-OAuth credential keeps working."""
        raw, prefix, hashed = generate_key()
        APIKey.objects.create(
            user=self.user, name="legacy", prefix=prefix, hashed_key=hashed
        )
        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, _, _ = _drive(
            app,
            headers=[
                (b"x-api-key", raw.encode()),
                (b"host", b"testserver"),
            ],
        )
        self.assertEqual(status, 204)
        self.assertEqual(recorder.calls[0]["mcp_api_key"].user_id, self.user.pk)


# ---------------------------------------------------------------------------
# Scope boundaries (both halves + backward compatibility)
# ---------------------------------------------------------------------------

class ScopeBoundaryTests(OAuthFlowMixin, TestCase):
    """``edms`` is a privilege boundary, so it has to hold in three places.

    Who may *ask* for it (only first-party client rows, not open DCR), what an
    ``edms`` token may *reach* (not the MCP tool surface), and — the part that
    breaks live users if it is wrong — that clients and tokens predating scopes
    keep working.
    """

    def test_open_registration_clamps_away_edms(self):
        """A self-registered client asking for edms is granted mcp instead.
        RFC 7591 lets us narrow, and the response says what was granted."""
        reg = self.register_client(scope="edms")
        self.assertEqual(reg["scope"], "")
        client = OAuthClient.objects.get(client_id=reg["client_id"])
        self.assertNotIn("edms", (client.scope or "").split())

    def test_self_registered_client_cannot_authorize_edms(self):
        """The phishing path: register a lookalike client, then walk a
        signed-in attorney through a consent screen for their filings."""
        _verifier, challenge = _pkce_pair()
        reg = self.register_client(client_name="Hudson EDMSpro", scope="edms")
        self.client.force_login(self.user)
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params(
                reg["client_id"], challenge, scope="edms"
            ),
        )
        self.assertEqual(resp.status_code, 302)
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["invalid_scope"])
        self.assertEqual(query["state"], ["xyz123"])
        self.assertNotIn("code", query)
        self.assertFalse(OAuthAuthorizationCode.objects.exists())

    def test_consent_post_cannot_smuggle_edms_past_the_get_check(self):
        """The POST re-validates, so a tampered hidden field buys nothing."""
        _verifier, challenge = _pkce_pair()
        reg = self.register_client()
        self.client.force_login(self.user)
        params = self.authorize_params(
            reg["client_id"], challenge, scope="edms"
        )
        resp = self.client.post(
            "/oauth/authorize", data={**params, "action": "approve"}
        )
        self.assertEqual(resp.status_code, 302)
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["invalid_scope"])
        self.assertFalse(OAuthToken.objects.exists())

    def test_first_party_client_may_obtain_edms(self):
        """The clamp must not break the product it was added for."""
        self._entitle()
        verifier, challenge = _pkce_pair()
        client = self._seed_first_party_client()
        code = self.obtain_code(client.client_id, challenge, scope="edms")
        resp = self.exchange_code(client.client_id, code, verifier)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["scope"], "edms")

    def test_first_party_edms_client_cannot_cross_into_mcp(self):
        """Registered for edms means edms — not a superset."""
        _verifier, challenge = _pkce_pair()
        client = self._seed_first_party_client()
        self.client.force_login(self.user)
        resp = self.client.get(
            "/oauth/authorize",
            data=self.authorize_params(
                client.client_id, challenge, scope="mcp"
            ),
        )
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["invalid_scope"])

    def test_client_registered_without_a_scope_still_gets_mcp(self):
        """Every connector registered before scopes existed stored scope="".
        Treating that as "no scopes" would lock all of them out."""
        client = self._seed_first_party_client(scope="")
        client.client_id = "legacy-connector"
        client.save()
        verifier, challenge = _pkce_pair()
        code = self.obtain_code(client.client_id, challenge, scope="mcp")
        resp = self.exchange_code(client.client_id, code, verifier)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["scope"], "mcp")

    def test_edms_token_is_refused_on_the_mcp_transport(self):
        """The other half of apps/api/bearer_auth.py's mcp→edms refusal.

        Without this, an extension token — whose consent screen listed only
        the three filing grants — drives the entire paid research surface.
        """
        self._entitle()
        verifier, challenge = _pkce_pair()
        client = self._seed_first_party_client()
        code = self.obtain_code(client.client_id, challenge, scope="edms")
        tokens = self.exchange_code(client.client_id, code, verifier).json()

        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, _, headers = _drive(
            app,
            headers=[
                (b"authorization", f"Bearer {tokens['access_token']}".encode()),
                (b"host", b"testserver"),
            ],
        )
        self.assertEqual(status, 401)
        self.assertIn('error="insufficient_scope"', headers["www-authenticate"])
        self.assertEqual(recorder.calls, [])

    def test_legacy_empty_scope_token_still_reaches_mcp(self):
        """Access tokens minted before SUPPORTED_SCOPES grew past ``mcp``
        carry scope="". They must keep working, or the fix logs out every
        live connector on deploy."""
        tokens = self.issue_tokens()
        OAuthToken.objects.update(scope="")

        recorder = _RecorderApp()
        app = api_key_middleware(recorder)
        status, _, _ = _drive(
            app,
            headers=[
                (b"authorization", f"Bearer {tokens['access_token']}".encode()),
                (b"host", b"testserver"),
            ],
        )
        self.assertEqual(status, 204)
        self.assertEqual(recorder.calls[0]["mcp_api_key"].user, self.user)


# ---------------------------------------------------------------------------
# Entitlement at token issuance
# ---------------------------------------------------------------------------

class EdmsEntitlementTests(OAuthFlowMixin, TestCase):
    """EDMSpro v1 is a paid feature, and issuance is the only place that can
    enforce it.

    The product is preview-and-download, performed by the extension in the
    browser against the court's own site; after sign-in it never asks Hudson
    for permission again. So a 403 on ``/api/edms/*`` gates nothing that
    matters — holding a token IS the entitlement, and the check has to happen
    before one exists.
    """

    def _authorize(self, scope="edms"):
        _verifier, challenge = _pkce_pair()
        client = self._seed_first_party_client(scope=scope)
        self.client.force_login(self.user)
        resp = self.client.post(
            "/oauth/authorize",
            data={
                **self.authorize_params(client.client_id, challenge, scope=scope),
                "action": "approve",
            },
        )
        self.assertEqual(resp.status_code, 302, getattr(resp, "content", b""))
        return parse_qs(urlsplit(resp["Location"]).query)

    def test_free_tier_is_refused_the_edms_scope(self):
        query = self._authorize()
        self.assertEqual(query["error"], ["access_denied"])
        self.assertIn("not included in your plan", query["error_description"][0])
        self.assertNotIn("code", query)
        self.assertFalse(OAuthAuthorizationCode.objects.exists())

    def test_refusal_names_the_product_not_the_scope_token(self):
        """The description is shown to an attorney by the extension verbatim."""
        query = self._authorize()
        self.assertIn("EDMSpro", query["error_description"][0])

    def test_paid_tier_is_granted(self):
        self.user.tier = "solo"
        self.user.save(update_fields=["tier"])
        self.assertIn("code", self._authorize())

    def test_staff_are_granted_without_any_plan(self):
        """Staff operate the product; they must never need a comped
        subscription to reproduce a customer's problem."""
        self.user.tier = "free"
        self.user.is_staff = True
        self.user.save(update_fields=["tier", "is_staff"])
        self.assertIn("code", self._authorize())

    def test_mcp_scope_is_not_gated_at_issuance(self):
        """Deliberate asymmetry: every MCP tool call re-checks the feature at
        call time, so an unentitled mcp token is harmless. Gating it here would
        break connectors that legitimately hold one."""
        self.user.tier = "free"
        self.user.save(update_fields=["tier"])
        self.assertIn("code", self._authorize(scope="mcp"))

    def test_the_gate_reads_the_plan_at_authorize_time(self):
        """Downgrade then retry: no cached decision survives the plan change."""
        self.user.tier = "solo"
        self.user.save(update_fields=["tier"])
        self.assertIn("code", self._authorize())
        OAuthAuthorizationCode.objects.all().delete()
        self.user.tier = "free"
        self.user.save(update_fields=["tier"])
        self.assertEqual(self._authorize()["error"], ["access_denied"])
