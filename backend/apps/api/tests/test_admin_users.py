"""Staff-only user management surface (apps.api.admin_users).

Three concerns: the gate (anon / non-staff never get in), the guardrails on
writes (superuser fence, no self-lockout, budget validation, audit rows), and
the deactivation kill-switch (sessions AND API keys stop working).
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.test import Client, TestCase

from apps.accounts.audit import AuditEvent
from apps.accounts.models import APIKey, Tier, User, verify_key

from ._factories import make_api_key, make_user


def _staff(email="staff@example.com", *, superuser=False) -> User:
    user = make_user(email)
    user.is_staff = True
    user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    return user


def _patch(client: Client, user_id: int, data: dict):
    return client.patch(
        f"/api/admin/users/{user_id}",
        data=json.dumps(data),
        content_type="application/json",
    )


class AdminUsersGateTests(TestCase):
    def test_anonymous_gets_401(self):
        for path in ("/api/admin/users", "/api/admin/users/1"):
            self.assertEqual(Client().get(path).status_code, 401, path)

    def test_non_staff_gets_401(self):
        make_user("plain@example.com")
        client = Client()
        client.force_login(User.objects.get(email="plain@example.com"))
        self.assertEqual(client.get("/api/admin/users").status_code, 401)

    def test_non_staff_cannot_patch(self):
        target = make_user("t@example.com")
        make_user("plain@example.com")
        client = Client()
        client.force_login(User.objects.get(email="plain@example.com"))
        self.assertEqual(
            _patch(client, target.id, {"tier": "firm"}).status_code, 401
        )
        target.refresh_from_db()
        self.assertEqual(target.tier, Tier.SOLO)


class AdminUsersListDetailTests(TestCase):
    def setUp(self):
        _staff()
        self.client = Client()
        self.client.force_login(User.objects.get(email="staff@example.com"))

    def test_list_returns_all_accounts_with_filters(self):
        make_user("alice@example.com")
        inactive = make_user("bob@example.com")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        body = self.client.get("/api/admin/users").json()
        self.assertEqual(body["total"], 3)
        emails = {u["email"] for u in body["users"]}
        self.assertIn("bob@example.com", emails)  # unlike the usage list

        body = self.client.get("/api/admin/users?status=deactivated").json()
        self.assertEqual([u["email"] for u in body["users"]], ["bob@example.com"])

        body = self.client.get("/api/admin/users?q=alice").json()
        self.assertEqual([u["email"] for u in body["users"]], ["alice@example.com"])

    def test_list_rejects_bad_filters(self):
        self.assertEqual(
            self.client.get("/api/admin/users?tier=platinum").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/admin/users?status=weird").status_code, 400
        )

    def test_detail_includes_keys_and_events(self):
        target = make_user("t@example.com")
        make_api_key(target, "leaky")
        body = self.client.get(f"/api/admin/users/{target.id}").json()
        self.assertEqual(body["user"]["email"], "t@example.com")
        self.assertEqual([k["name"] for k in body["api_keys"]], ["leaky"])
        self.assertFalse(body["can_edit_staff_flag"])  # not a superuser
        self.assertTrue(body["can_edit"])

    def test_detail_events_include_admin_actions_on_target(self):
        # Admin actions record the STAFF member as actor; the target's page
        # must still surface them (via detail.target_user_id).
        target = make_user("t@example.com")
        r = _patch(self.client, target.id, {"tier": "firm"})
        self.assertEqual(r.status_code, 200)
        body = self.client.get(f"/api/admin/users/{target.id}").json()
        self.assertIn(
            "admin_user_change", [e["event_type"] for e in body["events"]]
        )

    def test_detail_404(self):
        self.assertEqual(self.client.get("/api/admin/users/99999").status_code, 404)


class AdminUsersPatchTests(TestCase):
    def setUp(self):
        self.staff = _staff()
        self.client = Client()
        self.client.force_login(User.objects.get(email="staff@example.com"))
        self.target = make_user("t@example.com")

    def _audit_rows(self):
        return AuditEvent.objects.filter(
            event_type=AuditEvent.Event.ADMIN_USER_CHANGE
        )

    def test_patch_tier_budget_and_active_with_audit(self):
        r = _patch(
            self.client,
            self.target.id,
            {"tier": "firm", "monthly_budget_usd": 42.5, "is_active": False},
        )
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, "firm")
        self.assertEqual(self.target.monthly_budget_usd, Decimal("42.50"))
        self.assertFalse(self.target.is_active)

        row = self._audit_rows().get()
        self.assertEqual(row.actor, self.staff)
        self.assertEqual(row.detail["target_email"], "t@example.com")
        self.assertEqual(
            set(row.detail["changes"]), {"tier", "monthly_budget_usd", "is_active"}
        )

    def test_null_budget_clears_override(self):
        self.target.monthly_budget_usd = Decimal("5.00")
        self.target.save(update_fields=["monthly_budget_usd"])
        r = _patch(self.client, self.target.id, {"monthly_budget_usd": None})
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.monthly_budget_usd)

    def test_noop_patch_writes_no_audit_row(self):
        r = _patch(self.client, self.target.id, {"tier": self.target.tier})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._audit_rows().count(), 0)

    def test_validation_errors(self):
        self.assertEqual(
            _patch(self.client, self.target.id, {"tier": "platinum"}).status_code,
            400,
        )
        self.assertEqual(
            _patch(
                self.client, self.target.id, {"monthly_budget_usd": -1}
            ).status_code,
            400,
        )

    def test_staff_cannot_change_staff_flag(self):
        r = _patch(self.client, self.target.id, {"is_staff": True})
        self.assertEqual(r.status_code, 403)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)

    def test_staff_cannot_edit_staff_account(self):
        other = _staff("staff2@example.com")
        self.assertEqual(
            _patch(self.client, other.id, {"tier": "firm"}).status_code, 403
        )

    def test_no_self_lockout(self):
        supe = _staff("root@example.com", superuser=True)
        client = Client()
        client.force_login(User.objects.get(email="root@example.com"))
        for field in ({"is_active": False}, {"is_staff": False}):
            self.assertEqual(_patch(client, supe.id, field).status_code, 400)

    def test_superuser_grants_and_revokes_staff(self):
        _staff("root@example.com", superuser=True)
        client = Client()
        client.force_login(User.objects.get(email="root@example.com"))
        r = _patch(client, self.target.id, {"is_staff": True})
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)
        # And may edit (demote) another staff account.
        r = _patch(client, self.target.id, {"is_staff": False})
        self.assertEqual(r.status_code, 200)

    def test_superuser_cannot_be_deactivated_via_api(self):
        supe = _staff("root@example.com", superuser=True)
        other = _staff("root2@example.com", superuser=True)
        client = Client()
        client.force_login(User.objects.get(email="root2@example.com"))
        del other
        self.assertEqual(
            _patch(client, supe.id, {"is_active": False}).status_code, 400
        )

    def test_is_superuser_not_patchable(self):
        # Unknown fields are ignored by the schema — is_superuser stays put.
        _patch(self.client, self.target.id, {"is_superuser": True})
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_superuser)


class DeactivationKillSwitchTests(TestCase):
    def test_deactivated_user_api_key_stops_verifying(self):
        user = make_user("t@example.com")
        _, raw = make_api_key(user)
        self.assertIsNotNone(verify_key(raw))
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertIsNone(verify_key(raw))

    def test_deactivated_user_session_dies(self):
        user = make_user("t@example.com")
        client = Client()
        client.force_login(User.objects.get(email="t@example.com"))
        self.assertEqual(client.get("/api/auth/me").status_code, 200)
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertEqual(client.get("/api/auth/me").status_code, 401)


class AdminKeyRevokeTests(TestCase):
    def setUp(self):
        _staff()
        self.client = Client()
        self.client.force_login(User.objects.get(email="staff@example.com"))
        self.target = make_user("t@example.com")
        self.key, self.raw = make_api_key(self.target, "leaky")

    def test_revoke_and_audit(self):
        r = self.client.post(
            f"/api/admin/users/{self.target.id}/api-keys/{self.key.id}/revoke"
        )
        self.assertEqual(r.status_code, 200)
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.revoked_at)
        self.assertIsNone(verify_key(self.raw))
        row = AuditEvent.objects.filter(
            event_type=AuditEvent.Event.API_KEY_REVOKE
        ).get()
        self.assertTrue(row.detail["by_admin"])
        self.assertEqual(row.detail["target_email"], "t@example.com")

    def test_wrong_user_404(self):
        other = make_user("other@example.com")
        r = self.client.post(
            f"/api/admin/users/{other.id}/api-keys/{self.key.id}/revoke"
        )
        self.assertEqual(r.status_code, 404)

    def test_staff_target_requires_superuser(self):
        staffer = _staff("staff2@example.com")
        key, _ = make_api_key(staffer)
        r = self.client.post(
            f"/api/admin/users/{staffer.id}/api-keys/{key.id}/revoke"
        )
        self.assertEqual(r.status_code, 403)


class CsrfOnWritesTests(TestCase):
    def test_patch_without_csrf_token_is_rejected(self):
        _staff()
        target = make_user("t@example.com")
        client = Client(enforce_csrf_checks=True)
        client.force_login(User.objects.get(email="staff@example.com"))
        r = _patch(client, target.id, {"tier": "firm"})
        self.assertEqual(r.status_code, 403)
        target.refresh_from_db()
        self.assertEqual(target.tier, Tier.SOLO)
