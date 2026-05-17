"""End-to-end tests for the account endpoints.

Uses Django's test client through Ninja's URL router, so we exercise the
real session middleware (login/logout sets and clears the cookie). We don't
mock the model layer here — these endpoints are thin enough that the
interesting bugs live in the integration."""

from __future__ import annotations

import json

from django.test import Client, TestCase

from apps.accounts.models import APIKey, User


def _post(client: Client, path: str, payload: dict):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def _patch(client: Client, path: str, payload: dict):
    return client.patch(path, data=json.dumps(payload), content_type="application/json")


class RegisterLoginTests(TestCase):
    def test_register_creates_user_and_logs_in(self):
        client = Client()
        resp = _post(
            client,
            "/api/auth/register",
            {"email": "a@example.com", "password": "supersecret123", "full_name": "A"},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["email"], "a@example.com")
        self.assertEqual(body["full_name"], "A")
        self.assertEqual(body["tier"], "free")

        # Session cookie should now allow /me without re-auth.
        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "a@example.com")

    def test_register_rejects_short_password(self):
        client = Client()
        resp = _post(
            client,
            "/api/auth/register",
            {"email": "b@example.com", "password": "short"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(email="dup@example.com", password="x" * 12)
        client = Client()
        resp = _post(
            client,
            "/api/auth/register",
            {"email": "dup@example.com", "password": "longenough"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_with_valid_credentials_sets_session(self):
        User.objects.create_user(email="c@example.com", password="correct-horse-battery")
        client = Client()
        resp = _post(
            client,
            "/api/auth/login",
            {"email": "c@example.com", "password": "correct-horse-battery"},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)

    def test_login_rejects_bad_password(self):
        User.objects.create_user(email="d@example.com", password="rightone-12345")
        client = Client()
        resp = _post(
            client,
            "/api/auth/login",
            {"email": "d@example.com", "password": "wrongone-12345"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_logout_clears_session(self):
        User.objects.create_user(email="e@example.com", password="logoutpass-123")
        client = Client()
        _post(client, "/api/auth/login", {"email": "e@example.com", "password": "logoutpass-123"})
        resp = client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)
        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_me_without_login_returns_401(self):
        client = Client()
        resp = client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)


class APIKeyDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="keys@example.com", password="keysarefun-12"
        )

    def _logged_in_client(self) -> Client:
        client = Client()
        _post(
            client,
            "/api/auth/login",
            {"email": "keys@example.com", "password": "keysarefun-12"},
        )
        return client

    def test_create_returns_raw_key_once(self):
        client = self._logged_in_client()
        resp = _post(client, "/api/account/api-keys", {"name": "claude desktop"})
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertIn("raw_key", body)
        self.assertEqual(body["name"], "claude desktop")
        self.assertEqual(len(body["prefix"]), 8)

        # Listing the keys must NOT include the raw value.
        listing = client.get("/api/account/api-keys").json()
        self.assertEqual(len(listing), 1)
        self.assertNotIn("raw_key", listing[0])

    def test_create_requires_name(self):
        client = self._logged_in_client()
        resp = _post(client, "/api/account/api-keys", {"name": "  "})
        self.assertEqual(resp.status_code, 400)

    def test_revoke_marks_key_inactive_and_hides_from_list(self):
        client = self._logged_in_client()
        created = _post(
            client, "/api/account/api-keys", {"name": "to revoke"}
        ).json()
        resp = client.delete(f"/api/account/api-keys/{created['id']}")
        self.assertEqual(resp.status_code, 200)

        # Hidden from the list now.
        listing = client.get("/api/account/api-keys").json()
        self.assertEqual(listing, [])

        # And the row is preserved with revoked_at set (audit trail).
        row = APIKey.objects.get(pk=created["id"])
        self.assertIsNotNone(row.revoked_at)

    def test_revoke_other_users_key_is_404(self):
        intruder = User.objects.create_user(
            email="i@example.com", password="intruderpass-12"
        )
        other_key = APIKey.objects.create(
            user=intruder, name="theirs", prefix="abc12345", hashed_key="x" * 64
        )
        client = self._logged_in_client()
        resp = client.delete(f"/api/account/api-keys/{other_key.id}")
        self.assertEqual(resp.status_code, 404)
        # And the row is still active (not revoked).
        other_key.refresh_from_db()
        self.assertIsNone(other_key.revoked_at)

    def test_endpoints_require_login(self):
        client = Client()
        self.assertEqual(client.get("/api/account/api-keys").status_code, 401)
        self.assertEqual(
            _post(client, "/api/account/api-keys", {"name": "x"}).status_code, 401
        )
        self.assertEqual(client.delete("/api/account/api-keys/1").status_code, 401)


class ProfileEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="me@example.com", password="originalpass-12", full_name="Old Name"
        )

    def _client(self) -> Client:
        client = Client()
        _post(
            client,
            "/api/auth/login",
            {"email": "me@example.com", "password": "originalpass-12"},
        )
        return client

    def test_update_name_and_email(self):
        client = self._client()
        resp = _patch(
            client,
            "/api/auth/me",
            {"full_name": "New Name", "email": "New@Example.com"},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["full_name"], "New Name")
        # Email is normalized to lower-case.
        self.assertEqual(body["email"], "new@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    def test_partial_update_leaves_other_fields(self):
        client = self._client()
        resp = _patch(client, "/api/auth/me", {"full_name": "Only Name"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["email"], "me@example.com")

    def test_email_collision_rejected(self):
        User.objects.create_user(email="taken@example.com", password="x" * 12)
        client = self._client()
        resp = _patch(client, "/api/auth/me", {"email": "taken@example.com"})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "me@example.com")

    def test_invalid_email_rejected(self):
        client = self._client()
        resp = _patch(client, "/api/auth/me", {"email": "not-an-email"})
        self.assertEqual(resp.status_code, 400)

    def test_update_requires_login(self):
        resp = _patch(Client(), "/api/auth/me", {"full_name": "x"})
        self.assertEqual(resp.status_code, 401)

    def test_change_password_and_session_survives(self):
        client = self._client()
        resp = _post(
            client,
            "/api/auth/change-password",
            {"current_password": "originalpass-12", "new_password": "brandnewpass-34"},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        # Session must still be valid right after the change.
        self.assertEqual(client.get("/api/auth/me").status_code, 200)
        # Old password no longer authenticates; the new one does.
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("originalpass-12"))
        self.assertTrue(self.user.check_password("brandnewpass-34"))

    def test_change_password_wrong_current_rejected(self):
        client = self._client()
        resp = _post(
            client,
            "/api/auth/change-password",
            {"current_password": "wrong", "new_password": "brandnewpass-34"},
        )
        self.assertEqual(resp.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("originalpass-12"))

    def test_change_password_too_short_rejected(self):
        client = self._client()
        resp = _post(
            client,
            "/api/auth/change-password",
            {"current_password": "originalpass-12", "new_password": "short"},
        )
        self.assertEqual(resp.status_code, 400)
