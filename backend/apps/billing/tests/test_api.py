"""``/api/billing/*`` — the frozen response shapes, the authz fence, and the
unconfigured-Stripe path.

The response keys in ``SubscriptionOut`` are a contract with already-shipped SPA
code (BILLING_PLAN §6a), so they are asserted literally, key by key. Renaming one
here is a production break, not a refactor.
"""

from __future__ import annotations

import datetime as dt
import json

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Tier, User
from apps.tenancy.models import Organization, OrgMembership, Subscription
from apps.tenancy.services import ensure_personal_org

from ._stripe import (
    PRICE_FIRM,
    PRICE_FIRM_SEAT,
    PRICE_SOLO,
    STRIPE_SETTINGS,
    FakeStripe,
    checkout_session_obj,
    event_body,
    mock_stripe,
    sign,
    subscription_obj,
)

SubStatus = Subscription.Status

# Every key the SPA reads off GET /api/billing/subscription. Frozen.
SUBSCRIPTION_KEYS = {
    "org",
    "plan",
    "status",
    "seats_used",
    "seats_purchased",
    "current_period_end",
    "cancel_at_period_end",
    "trial_end",
    "past_due_since",
    "grace_ends_at",
    "can_manage",
}


def make_user(email: str) -> User:
    return User.objects.create_user(email=email, password="x", tier=Tier.FREE)


class SubscriptionEndpointTests(TestCase):
    def setUp(self):
        self.user = make_user("owner@example.com")
        self.org = ensure_personal_org(self.user)
        self.client.force_login(self.user)

    def get(self) -> dict:
        response = self.client.get("/api/billing/subscription")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_anonymous_is_401(self):
        self.assertEqual(
            Client().get("/api/billing/subscription").status_code, 401
        )

    def test_no_subscription_reads_free_and_none(self):
        body = self.get()
        self.assertEqual(set(body), SUBSCRIPTION_KEYS)
        self.assertEqual(body["plan"], "free")
        self.assertEqual(body["status"], "none")  # legal: no subscription row
        self.assertEqual(body["seats_used"], 1)
        self.assertEqual(body["seats_purchased"], 0)
        self.assertIsNone(body["current_period_end"])
        self.assertIsNone(body["grace_ends_at"])
        self.assertFalse(body["cancel_at_period_end"])
        self.assertTrue(body["can_manage"])  # owner of their personal org
        self.assertEqual(
            set(body["org"]), {"id", "name", "is_personal", "status"}
        )
        self.assertTrue(body["org"]["is_personal"])

    def test_serves_db_state_with_no_stripe_configured(self):
        """A comped/backfilled subscription has no Stripe object behind it — the
        billing page must still render, so this route never 503s."""
        Subscription.objects.create(
            org=self.org, product=None, plan=Tier.FIRM,
            status=SubStatus.ACTIVE, seats=4,
        )
        with override_settings(STRIPE_SECRET_KEY=""):
            body = self.get()
        self.assertEqual(body["plan"], "firm")
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["seats_purchased"], 4)

    @override_settings(BILLING_PAST_DUE_GRACE_DAYS=7)
    def test_grace_ends_at_is_the_anchor_plus_the_window(self):
        anchor = timezone.now() - dt.timedelta(days=2)
        Subscription.objects.create(
            org=self.org, product=None, plan=Tier.SOLO,
            status=SubStatus.PAST_DUE, past_due_since=anchor, seats=1,
        )
        body = self.get()
        self.assertEqual(body["status"], "past_due")
        self.assertIsNotNone(body["past_due_since"])
        expected = anchor + dt.timedelta(days=7)
        # JSON serialisation rounds to milliseconds; the deadline is a date shown
        # in a banner, so sub-millisecond fidelity is not the point.
        self.assertAlmostEqual(
            dt.datetime.fromisoformat(body["grace_ends_at"]),
            expected,
            delta=dt.timedelta(milliseconds=1),
        )

    def test_periods_and_seats_round_trip(self):
        period_end = timezone.now() + dt.timedelta(days=20)
        Subscription.objects.create(
            org=self.org, product=None, plan=Tier.FIRM, status=SubStatus.ACTIVE,
            seats=5, current_period_end=period_end, cancel_at_period_end=True,
        )
        body = self.get()
        self.assertEqual(body["seats_purchased"], 5)
        self.assertEqual(body["seats_used"], 1)
        self.assertTrue(body["cancel_at_period_end"])
        self.assertAlmostEqual(
            dt.datetime.fromisoformat(body["current_period_end"]),
            period_end,
            delta=dt.timedelta(milliseconds=1),
        )


class ManageAuthzTests(TestCase):
    """owner/admin may spend money; a member may only look."""

    def setUp(self):
        # The firm org (a renamed personal org — BILLING_PLAN §6a) plus a plain
        # member invited into it. The member's billing org IS this org.
        self.owner = make_user("owner@example.com")
        self.org = ensure_personal_org(self.owner)
        self.org.name = "Acme Law"
        self.org.stripe_customer_id = "cus_test_1"
        self.org.save()

        self.member = make_user("member@example.com")
        OrgMembership.objects.create(
            user=self.member, org=self.org, role=OrgMembership.Role.MEMBER
        )

    @override_settings(**STRIPE_SETTINGS)
    def test_member_cannot_checkout(self):
        self.client.force_login(self.member)
        with mock_stripe():
            response = self.client.post(
                "/api/billing/checkout",
                data=json.dumps({"plan": "solo"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 403)

    @override_settings(**STRIPE_SETTINGS)
    def test_member_cannot_open_the_portal(self):
        self.client.force_login(self.member)
        with mock_stripe():
            response = self.client.post("/api/billing/portal")
        self.assertEqual(response.status_code, 403)

    def test_member_sees_can_manage_false(self):
        self.client.force_login(self.member)
        body = self.client.get("/api/billing/subscription").json()
        self.assertFalse(body["can_manage"])
        self.assertEqual(body["org"]["name"], "Acme Law")

    @override_settings(**STRIPE_SETTINGS)
    def test_admin_may_checkout(self):
        admin = make_user("admin@example.com")
        OrgMembership.objects.create(
            user=admin, org=self.org, role=OrgMembership.Role.ADMIN
        )
        self.client.force_login(admin)
        with mock_stripe():
            response = self.client.post(
                "/api/billing/checkout",
                data=json.dumps({"plan": "solo"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)


@override_settings(**STRIPE_SETTINGS)
class CheckoutTests(TestCase):
    def setUp(self):
        self.user = make_user("owner@example.com")
        self.org = ensure_personal_org(self.user)
        self.client.force_login(self.user)

    def post(self, body: dict, fake: FakeStripe | None = None):
        with mock_stripe(fake) as stripe:
            response = self.client.post(
                "/api/billing/checkout",
                data=json.dumps(body),
                content_type="application/json",
            )
        return response, stripe

    def test_returns_a_checkout_url(self):
        response, _ = self.post({"plan": "solo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"url": "https://checkout.stripe.com/c/pay/cs_test_1"}
        )

    def test_creates_a_customer_on_first_checkout_and_stores_it(self):
        response, stripe = self.post({"plan": "solo"})
        self.assertEqual(response.status_code, 200)
        customer_args = stripe.call_args("Customer.create")
        self.assertEqual(customer_args["email"], "owner@example.com")
        self.assertEqual(customer_args["metadata"], {"org_id": str(self.org.pk)})
        self.assertEqual(
            Organization.objects.get(pk=self.org.pk).stripe_customer_id, "cus_new_test"
        )

    def test_reuses_an_existing_customer(self):
        Organization.objects.filter(pk=self.org.pk).update(
            stripe_customer_id="cus_existing"
        )
        _, stripe = self.post({"plan": "solo"})
        self.assertNotIn("Customer.create", stripe.call_names())
        self.assertEqual(
            stripe.call_args("checkout.Session.create")["customer"], "cus_existing"
        )

    def test_session_carries_the_org_on_the_session_AND_the_subscription(self):
        """Without ``subscription_data.metadata`` the ``customer.subscription.*``
        events arrive with no way home but the customer id."""
        _, stripe = self.post({"plan": "firm", "seats": 4})
        args = stripe.call_args("checkout.Session.create")
        self.assertEqual(args["mode"], "subscription")
        self.assertEqual(args["client_reference_id"], str(self.org.pk))
        self.assertEqual(args["metadata"], {"org_id": str(self.org.pk), "plan": "firm"})
        self.assertEqual(
            args["subscription_data"]["metadata"],
            {"org_id": str(self.org.pk), "plan": "firm"},
        )
        self.assertIn("/account/billing", args["success_url"])
        self.assertIn("/account/billing", args["cancel_url"])

    def test_quantity_is_the_requested_seats(self):
        _, stripe = self.post({"plan": "firm", "seats": 6})
        line_items = stripe.call_args("checkout.Session.create")["line_items"]
        self.assertEqual(line_items, [{"price": PRICE_FIRM, "quantity": 6}])

    def test_quantity_is_floored_by_the_orgs_actual_headcount(self):
        """Never sell fewer seats than the org already has members."""
        for i in range(3):
            OrgMembership.objects.create(
                user=make_user(f"m{i}@example.com"),
                org=self.org,
                role=OrgMembership.Role.MEMBER,
            )
        _, stripe = self.post({"plan": "firm", "seats": 1})
        line_items = stripe.call_args("checkout.Session.create")["line_items"]
        self.assertEqual(line_items, [{"price": PRICE_FIRM, "quantity": 4}])

    @override_settings(**{**STRIPE_SETTINGS, "STRIPE_PRICE_FIRM_SEAT": PRICE_FIRM_SEAT})
    def test_base_plus_seat_pricing_emits_two_line_items(self):
        _, stripe = self.post({"plan": "firm", "seats": 5})
        line_items = stripe.call_args("checkout.Session.create")["line_items"]
        self.assertEqual(
            line_items,
            [
                {"price": PRICE_FIRM, "quantity": 1},
                {"price": PRICE_FIRM_SEAT, "quantity": 5},
            ],
        )

    def test_solo_always_bills_one_seat(self):
        _, stripe = self.post({"plan": "solo", "seats": 9})
        line_items = stripe.call_args("checkout.Session.create")["line_items"]
        self.assertEqual(line_items, [{"price": PRICE_SOLO, "quantity": 1}])

    def test_unpurchasable_plan_is_400(self):
        for plan in ("free", "custom", "enterprise", ""):
            response, _ = self.post({"plan": plan})
            self.assertEqual(response.status_code, 400, plan)

    @override_settings(**{**STRIPE_SETTINGS, "STRIPE_PRICE_FIRM": ""})
    def test_missing_price_id_is_503_not_a_crash(self):
        response, _ = self.post({"plan": "firm"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["detail"])

    def test_anonymous_is_401(self):
        self.assertEqual(
            Client().post(
                "/api/billing/checkout",
                data=json.dumps({"plan": "solo"}),
                content_type="application/json",
            ).status_code,
            401,
        )


@override_settings(**{**STRIPE_SETTINGS, "STRIPE_TRIAL_DAYS": 7})
class CheckoutTrialTests(TestCase):
    """The card-up-front trial (PRICING_STRATEGY §2): first Stripe subscription
    per org only — cancel-and-resubscribe must not mint a fresh trial."""

    def setUp(self):
        self.user = make_user("owner@example.com")
        self.org = ensure_personal_org(self.user)
        self.client.force_login(self.user)

    def post(self):
        with mock_stripe() as stripe:
            response = self.client.post(
                "/api/billing/checkout",
                data=json.dumps({"plan": "solo"}),
                content_type="application/json",
            )
        return response, stripe

    def session_args(self) -> dict:
        response, stripe = self.post()
        self.assertEqual(response.status_code, 200)
        return stripe.call_args("checkout.Session.create")

    def test_first_checkout_carries_the_trial_and_collects_the_card(self):
        args = self.session_args()
        self.assertEqual(args["subscription_data"]["trial_period_days"], 7)
        self.assertEqual(args["payment_method_collection"], "always")
        # trial rides alongside the metadata, never instead of it
        self.assertEqual(args["subscription_data"]["metadata"]["plan"], "solo")

    def test_an_org_that_ever_billed_through_stripe_gets_no_second_trial(self):
        Subscription.objects.create(
            org=self.org, product=None, plan=Tier.SOLO,
            status=SubStatus.CANCELED, stripe_subscription_id="sub_old_1",
        )
        args = self.session_args()
        self.assertNotIn("trial_period_days", args["subscription_data"])

    def test_a_comped_subscription_does_not_burn_the_trial(self):
        """Backfilled/comped rows have no Stripe id — that org has never been
        through Checkout and still gets its trial when it converts."""
        Subscription.objects.create(
            org=self.org, product=None, plan=Tier.SOLO, status=SubStatus.ACTIVE,
        )
        args = self.session_args()
        self.assertEqual(args["subscription_data"]["trial_period_days"], 7)

    @override_settings(**{**STRIPE_SETTINGS, "STRIPE_TRIAL_DAYS": 0})
    def test_zero_disables_the_trial(self):
        args = self.session_args()
        self.assertNotIn("trial_period_days", args["subscription_data"])


@override_settings(**STRIPE_SETTINGS)
class PortalTests(TestCase):
    def setUp(self):
        self.user = make_user("owner@example.com")
        self.org = ensure_personal_org(self.user)
        self.client.force_login(self.user)

    def test_returns_a_portal_url(self):
        Organization.objects.filter(pk=self.org.pk).update(
            stripe_customer_id="cus_test_1"
        )
        with mock_stripe() as stripe:
            response = self.client.post("/api/billing/portal")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"url": "https://billing.stripe.com/p/session/test"}
        )
        args = stripe.call_args("billing_portal.Session.create")
        self.assertEqual(args["customer"], "cus_test_1")
        self.assertTrue(args["return_url"].endswith("/account/billing"))

    def test_no_customer_yet_is_400(self):
        with mock_stripe():
            response = self.client.post("/api/billing/portal")
        self.assertEqual(response.status_code, 400)


class UnconfiguredStripeTests(TestCase):
    """No STRIPE_SECRET_KEY: the app boots, the suite passes, the Stripe-calling
    endpoints answer a clean 503 rather than exploding inside the SDK."""

    def setUp(self):
        self.user = make_user("owner@example.com")
        ensure_personal_org(self.user)
        self.client.force_login(self.user)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="")
    def test_checkout_portal_and_webhook_are_503(self):
        checkout = self.client.post(
            "/api/billing/checkout",
            data=json.dumps({"plan": "solo"}),
            content_type="application/json",
        )
        self.assertEqual(checkout.status_code, 503)
        self.assertEqual(checkout.json()["detail"], "billing not configured")

        portal = self.client.post("/api/billing/portal")
        self.assertEqual(portal.status_code, 503)
        self.assertEqual(portal.json()["detail"], "billing not configured")

        webhook = self.client.post(
            "/api/billing/webhook", data=b"{}", content_type="application/json"
        )
        self.assertEqual(webhook.status_code, 503)

    @override_settings(STRIPE_SECRET_KEY="")
    def test_subscription_still_reads(self):
        self.assertEqual(
            self.client.get("/api/billing/subscription").status_code, 200
        )


@override_settings(**STRIPE_SETTINGS)
class WebhookEndpointTests(TestCase):
    """The webhook is authenticated by SIGNATURE, not by session — auth=None and
    CSRF-exempt, so the signature check is the entire fence."""

    def setUp(self):
        self.user = make_user("owner@example.com")
        self.org = ensure_personal_org(self.user)
        Organization.objects.filter(pk=self.org.pk).update(
            stripe_customer_id="cus_test_1"
        )
        self.org.refresh_from_db()

    def post(self, body: bytes, signature: str | None = None):
        return self.client.post(
            "/api/billing/webhook",
            data=body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature if signature is not None else sign(body),
        )

    def test_valid_signature_is_processed(self):
        body = event_body(
            "customer.subscription.created",
            subscription_obj(org_id=self.org.pk),
        )
        with mock_stripe():
            response = self.post(body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "processed")
        self.assertEqual(
            Subscription.objects.get(org=self.org).plan, Tier.SOLO
        )
        self.assertEqual(User.objects.get(pk=self.user.pk).tier, Tier.SOLO)

    def test_bad_signature_is_400_and_changes_nothing(self):
        body = event_body(
            "customer.subscription.created", subscription_obj(org_id=self.org.pk)
        )
        with mock_stripe():
            response = self.post(body, signature=sign(body, secret="whsec_wrong"))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Subscription.objects.filter(org=self.org).exists())

    def test_tampered_body_is_400(self):
        body = event_body(
            "customer.subscription.created", subscription_obj(org_id=self.org.pk)
        )
        signature = sign(body)
        tampered = body.replace(b'"active"', b'"trialing"')
        with mock_stripe():
            response = self.post(tampered, signature=signature)
        self.assertEqual(response.status_code, 400)

    def test_missing_signature_header_is_400(self):
        with mock_stripe():
            response = self.client.post(
                "/api/billing/webhook",
                data=event_body("invoice.paid", {}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)

    def test_no_session_or_csrf_token_required(self):
        """Stripe has no cookie and no CSRF token. The route must not demand one."""
        body = event_body(
            "checkout.session.completed",
            checkout_session_obj(org_id=self.org.pk, plan="firm"),
        )
        client = Client(enforce_csrf_checks=True)
        with mock_stripe(FakeStripe(subscription=subscription_obj(org_id=self.org.pk))):
            response = client.post(
                "/api/billing/webhook",
                data=body,
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE=sign(body),
            )
        self.assertEqual(response.status_code, 200)

    def test_replay_over_http_is_a_no_op(self):
        body = event_body(
            "customer.subscription.created", subscription_obj(org_id=self.org.pk)
        )
        with mock_stripe():
            first = self.post(body)
            second = self.post(body)
        self.assertEqual(first.json()["result"], "processed")
        self.assertEqual(second.json()["result"], "duplicate")
