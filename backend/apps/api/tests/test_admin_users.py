"""Staff-only user management surface (apps.api.admin_users).

Four concerns: the gate (anon / non-staff never get in), the guardrails on
writes (superuser fence, no self-lockout, budget validation, audit rows), the
deactivation kill-switch (sessions AND API keys stop working), and **comping** —
staff granting a paid plan by hand now that ``User.tier`` is a derived cache of
the billing state (it writes a comped Subscription on the user's personal org;
a Stripe-billed plan is refused).
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.management import call_command
from django.test import Client, TestCase

from apps.accounts.audit import AuditEvent
from apps.accounts.models import APIKey, Tier, User, verify_key
from apps.tenancy import services
from apps.tenancy.models import Organization, Subscription

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
        """A non-staff caller cannot comp anyone — not even themselves."""
        target = make_user("t@example.com", tier=Tier.FREE)
        make_user("plain@example.com")
        client = Client()
        client.force_login(User.objects.get(email="plain@example.com"))
        self.assertEqual(
            _patch(client, target.id, {"comped_plan": "firm"}).status_code, 401
        )
        target.refresh_from_db()
        self.assertEqual(target.tier, Tier.FREE)
        self.assertFalse(Subscription.objects.exists())


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
        r = _patch(self.client, target.id, {"comped_plan": "firm"})
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

    def test_patch_plan_budget_and_active_with_audit(self):
        r = _patch(
            self.client,
            self.target.id,
            {"comped_plan": "firm", "monthly_budget_usd": 42.5, "is_active": False},
        )
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, "firm")
        self.assertEqual(self.target.monthly_budget_usd, Decimal("42.50"))
        self.assertFalse(self.target.is_active)

        row = self._audit_rows().get()
        self.assertEqual(row.actor, self.staff)
        self.assertEqual(row.detail["target_email"], "t@example.com")
        # The comp, the tier it derived, and the two plain columns.
        self.assertEqual(
            set(row.detail["changes"]),
            {"comped_plan", "tier", "monthly_budget_usd", "is_active"},
        )
        self.assertEqual(row.detail["changes"]["comped_plan"]["new"], "firm")
        self.assertTrue(row.detail["changes"]["tier"]["derived"])

    def test_tier_is_no_longer_writable(self):
        """A stale client sending ``tier`` gets a loud 400, not a silent no-op:
        the column is derived, so writing it would grant nothing and be reverted
        by ``reconcile_tiers``."""
        r = _patch(self.client, self.target.id, {"tier": "firm"})
        self.assertEqual(r.status_code, 400)
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.SOLO)  # untouched
        self.assertFalse(Subscription.objects.exists())
        self.assertEqual(self._audit_rows().count(), 0)

    def test_null_budget_clears_override(self):
        self.target.monthly_budget_usd = Decimal("5.00")
        self.target.save(update_fields=["monthly_budget_usd"])
        r = _patch(self.client, self.target.id, {"monthly_budget_usd": None})
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.monthly_budget_usd)

    def test_noop_patch_writes_no_audit_row(self):
        # The target is not comped, so re-sending "free" changes nothing.
        r = _patch(self.client, self.target.id, {"comped_plan": "free"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._audit_rows().count(), 0)

    def test_validation_errors(self):
        self.assertEqual(
            _patch(
                self.client, self.target.id, {"comped_plan": "platinum"}
            ).status_code,
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
            _patch(self.client, other.id, {"comped_plan": "firm"}).status_code, 403
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


class CompingTests(TestCase):
    """Comping is the ONE way staff grant a plan by hand now.

    ``User.tier`` is a derived cache of ``tenancy.services.effective_plan``, so a
    comp has to write what the tier derives FROM: a flagship (``product IS NULL``)
    Subscription on the user's personal org, ``status=active``, ``seats=1``, no
    Stripe ids — the same row the 0002_billing backfill wrote for paid users.
    """

    def setUp(self):
        self.staff = _staff()
        self.client = Client()
        self.client.force_login(User.objects.get(email="staff@example.com"))
        # A genuinely free user: no org, no subscription, tier=free.
        self.target = make_user("t@example.com", tier=Tier.FREE)

    def _comp(self, plan: str):
        return _patch(self.client, self.target.id, {"comped_plan": plan})

    def test_comping_a_free_user_grants_the_tier_and_survives_reconcile(self):
        r = self._comp("firm")
        self.assertEqual(r.status_code, 200)

        # 1. The tier moved…
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.FIRM)

        # 2. …because a comped subscription now backs it — the backfill's shape.
        org = services.billing_org(self.target)
        self.assertIsNotNone(org)
        self.assertTrue(org.is_personal)
        sub = Subscription.objects.get(org=org)
        self.assertIsNone(sub.product_id)  # flagship
        self.assertEqual(sub.plan, Tier.FIRM)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.seats, 1)
        self.assertIsNone(sub.stripe_subscription_id)
        self.assertEqual(sub.stripe_price_id, "")
        self.assertEqual(services.effective_plan(self.target), Tier.FIRM)

        # 3. …so the reconciler agrees with it instead of reverting it (the
        # regression: a hand-set tier was clobbered on the next cron run).
        call_command("reconcile_tiers", "--fix", "--quiet")
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.FIRM)

        # And the API reports it as staff-granted, not paid.
        body = self.client.get(f"/api/admin/users/{self.target.id}").json()
        self.assertEqual(body["plan"]["comped_plan"], "firm")
        self.assertEqual(body["plan"]["source"], "comped")
        self.assertTrue(body["plan"]["editable"])
        self.assertEqual(body["user"]["tier"], "firm")

    def test_comping_an_already_comped_user_changes_the_plan(self):
        self.assertEqual(self._comp("solo").status_code, 200)
        self.assertEqual(self._comp("custom").status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.CUSTOM)
        sub = Subscription.objects.get()  # upserted, not duplicated
        self.assertEqual(sub.plan, Tier.CUSTOM)

    def test_uncomping_revokes_the_tier(self):
        self.assertEqual(self._comp("solo").status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.SOLO)

        r = self._comp("free")
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.FREE)
        # Back to the shape of an account that never paid.
        self.assertFalse(Subscription.objects.exists())
        call_command("reconcile_tiers", "--fix", "--quiet")
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.FREE)

        body = self.client.get(f"/api/admin/users/{self.target.id}").json()
        self.assertEqual(body["plan"]["source"], "none")
        self.assertEqual(body["plan"]["comped_plan"], "free")

    def test_stripe_paying_customer_cannot_be_comped(self):
        org = services.ensure_personal_org(self.target)
        Subscription.objects.create(
            org=org,
            product=None,
            plan=Tier.SOLO,
            status=Subscription.Status.ACTIVE,
            seats=1,
            stripe_subscription_id="sub_live_123",
            stripe_price_id="price_solo",
        )
        services.sync_user_tier(self.target)

        r = self._comp("firm")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Stripe", r.json()["detail"])

        # Untouched: the plan, the tier, and the audit trail.
        sub = Subscription.objects.get()
        self.assertEqual(sub.plan, Tier.SOLO)
        self.assertEqual(sub.stripe_subscription_id, "sub_live_123")
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.SOLO)
        self.assertFalse(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ADMIN_USER_CHANGE
            ).exists()
        )

        # The detail page renders it as paid + read-only.
        body = self.client.get(f"/api/admin/users/{self.target.id}").json()
        self.assertEqual(body["plan"]["source"], "stripe")
        self.assertFalse(body["plan"]["editable"])

    def test_budget_still_editable_for_a_stripe_customer(self):
        """The 409 fence is on the PLAN, not the whole account: an unchanged
        plan riding along with a budget edit must not block it."""
        org = services.ensure_personal_org(self.target)
        Subscription.objects.create(
            org=org,
            product=None,
            plan=Tier.SOLO,
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id="sub_live_123",
        )
        r = _patch(
            self.client,
            self.target.id,
            {"comped_plan": "solo", "monthly_budget_usd": 10},
        )
        self.assertEqual(r.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.monthly_budget_usd, Decimal("10.00"))

    def test_comp_refused_when_the_org_is_suspended(self):
        """A suspended org grants nothing (services.org_granted_plan), so a comp
        there would be a silent no-op — refuse instead of lying."""
        org = services.ensure_personal_org(self.target)
        org.status = Organization.Status.SUSPENDED
        org.save(update_fields=["status"])

        r = self._comp("firm")
        self.assertEqual(r.status_code, 409)
        self.assertFalse(Subscription.objects.exists())
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.FREE)

    def test_firm_membership_is_reported_but_not_mistaken_for_a_comp(self):
        """A user can be ``firm`` with no comp at all (a seat in someone's firm).
        The plan panel must say so — un-comping cannot revoke that."""
        firm = Organization.objects.create(
            slug="acme-law", name="Acme Law", status=Organization.Status.ACTIVE
        )
        Subscription.objects.create(
            org=firm,
            product=None,
            plan=Tier.FIRM,
            status=Subscription.Status.ACTIVE,
            seats=5,
            stripe_subscription_id="sub_firm_1",
        )
        services.add_member(firm, self.target)
        self.target.refresh_from_db()
        self.assertEqual(self.target.tier, Tier.FIRM)

        body = self.client.get(f"/api/admin/users/{self.target.id}").json()
        self.assertEqual(body["user"]["tier"], "firm")
        # Their PERSONAL org holds nothing — the plan is the firm's.
        self.assertEqual(body["plan"]["comped_plan"], "free")
        self.assertEqual(body["plan"]["source"], "none")
        self.assertTrue(body["plan"]["editable"])
        self.assertEqual(
            body["plan"]["other_grants"],
            [{"org_id": firm.id, "org_name": "Acme Law", "plan": "firm"}],
        )


class CsrfOnWritesTests(TestCase):
    def test_patch_without_csrf_token_is_rejected(self):
        _staff()
        target = make_user("t@example.com", tier=Tier.FREE)
        client = Client(enforce_csrf_checks=True)
        client.force_login(User.objects.get(email="staff@example.com"))
        r = _patch(client, target.id, {"comped_plan": "firm"})
        self.assertEqual(r.status_code, 403)
        target.refresh_from_db()
        self.assertEqual(target.tier, Tier.FREE)
        self.assertFalse(Subscription.objects.exists())
