"""End-to-end tests for the /api/account/settings + onboarding endpoints.

Like test_accounts, these run through Django's test client and the real
session middleware — login sets the cookie, the settings routes read it. We
assert the User/UserProfile split (name writes to User, prefs to the profile),
enum/length validation, the onboarding/ToS flow, and the audit rows each
mutation leaves behind."""

from __future__ import annotations

import json

from django.test import Client, TestCase

from apps.accounts.audit import AuditEvent
from apps.accounts.models import User, UserProfile


def _post(client: Client, path: str, payload: dict | None = None):
    return client.post(
        path, data=json.dumps(payload or {}), content_type="application/json"
    )


def _patch(client: Client, path: str, payload: dict):
    return client.patch(
        path, data=json.dumps(payload), content_type="application/json"
    )


class SettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="settings@example.com", password="settingspass-12", full_name="Pat Lee"
        )

    def _client(self) -> Client:
        client = Client()
        _post(
            client,
            "/api/auth/login",
            {"email": "settings@example.com", "password": "settingspass-12"},
        )
        return client

    # ---- signal / defaults ------------------------------------------------

    def test_new_user_gets_profile_with_sane_defaults(self):
        # The post_save signal should have created a profile for this user.
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())
        resp = self._client().get("/api/account/settings")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["theme"], "system")
        self.assertEqual(body["default_search_scope"], "all")
        self.assertEqual(body["citation_style"], "bluebook")
        self.assertTrue(body["verify_citations"])
        self.assertFalse(body["onboarding_completed"])
        self.assertEqual(body["tos_version"], "")
        self.assertEqual(body["current_tos_version"], "v2.4")
        self.assertEqual(body["email"], "settings@example.com")

    def test_settings_requires_auth(self):
        self.assertEqual(Client().get("/api/account/settings").status_code, 401)
        self.assertEqual(
            _patch(Client(), "/api/account/settings", {"city": "x"}).status_code, 401
        )

    def test_me_exposes_structured_name_and_onboarding_flag(self):
        me = self._client().get("/api/auth/me").json()
        self.assertIn("first_name", me)
        self.assertIn("last_name", me)
        self.assertIn("onboarding_completed", me)
        self.assertFalse(me["onboarding_completed"])

    # ---- PATCH /settings --------------------------------------------------

    def test_patch_name_writes_to_user_and_syncs_full_name(self):
        client = self._client()
        resp = _patch(
            client,
            "/api/account/settings",
            {"first_name": "Dana", "last_name": "Okafor"},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["first_name"], "Dana")
        self.assertEqual(body["last_name"], "Okafor")

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Dana")
        self.assertEqual(self.user.last_name, "Okafor")
        self.assertEqual(self.user.full_name, "Dana Okafor")  # derived

    def test_patch_updates_profile_fields(self):
        client = self._client()
        resp = _patch(
            client,
            "/api/account/settings",
            {
                "phone": "(515) 555-0100",
                "city": "Des Moines",
                "region": "IA",
                "role": "attorney",
                "theme": "dark",
                "default_search_scope": "cases",
                "weekly_digest": False,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.phone, "(515) 555-0100")
        self.assertEqual(profile.city, "Des Moines")
        self.assertEqual(profile.role, "attorney")
        self.assertEqual(profile.theme, "dark")
        self.assertEqual(profile.default_search_scope, "cases")
        self.assertFalse(profile.weekly_digest)

    def test_patch_is_partial_and_can_clear_a_boolean(self):
        client = self._client()
        # First set a couple of values…
        _patch(client, "/api/account/settings", {"city": "Ames", "verify_citations": True})
        # …then a partial patch that only flips verify_citations should leave city.
        _patch(client, "/api/account/settings", {"verify_citations": False})
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.city, "Ames")
        self.assertFalse(profile.verify_citations)

    def test_patch_rejects_unknown_enum_value(self):
        resp = _patch(self._client(), "/api/account/settings", {"theme": "neon"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("theme", resp.json()["detail"])

    def test_patch_rejects_overlong_value(self):
        resp = _patch(
            self._client(), "/api/account/settings", {"country": "USA"}  # max 2
        )
        self.assertEqual(resp.status_code, 400)

    def test_patch_allows_clearing_role(self):
        client = self._client()
        _patch(client, "/api/account/settings", {"role": "attorney"})
        resp = _patch(client, "/api/account/settings", {"role": ""})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(UserProfile.objects.get(user=self.user).role, "")

    def test_patch_writes_settings_change_audit_event(self):
        _patch(self._client(), "/api/account/settings", {"theme": "dark"})
        ev = AuditEvent.objects.filter(
            event_type=AuditEvent.Event.SETTINGS_CHANGE, actor=self.user
        ).first()
        self.assertIsNotNone(ev)
        self.assertIn("theme", ev.detail["fields"])

    # ---- onboarding -------------------------------------------------------

    def test_complete_onboarding_stamps_state_and_audits(self):
        client = self._client()
        resp = _post(client, "/api/account/onboarding/complete", {"tos_version": "v2.4"})
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body["onboarding_completed"])
        self.assertEqual(body["tos_version"], "v2.4")
        self.assertIsNotNone(body["tos_accepted_at"])

        # /me now reflects the flag (so the SPA stops routing into the wizard).
        self.assertTrue(client.get("/api/auth/me").json()["onboarding_completed"])

        # Append-only legal trail: both events, with the version recorded.
        tos = AuditEvent.objects.filter(
            event_type=AuditEvent.Event.TOS_ACCEPTED, actor=self.user
        ).first()
        self.assertIsNotNone(tos)
        self.assertEqual(tos.detail["tos_version"], "v2.4")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ONBOARDING_COMPLETED, actor=self.user
            ).exists()
        )

    def test_complete_onboarding_without_version_uses_server_value(self):
        resp = _post(self._client(), "/api/account/onboarding/complete")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tos_version"], "v2.4")

    def test_complete_onboarding_rejects_stale_tos_version(self):
        resp = _post(
            self._client(), "/api/account/onboarding/complete", {"tos_version": "v1.0"}
        )
        self.assertEqual(resp.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(UserProfile.objects.get(user=self.user).onboarding_completed)

    def test_complete_onboarding_requires_auth(self):
        self.assertEqual(
            _post(Client(), "/api/account/onboarding/complete").status_code, 401
        )
