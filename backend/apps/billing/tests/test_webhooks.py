"""Webhook handlers — the source of truth for billing state.

The three things that break paying customers if they are wrong, tested hardest:

1. ``past_due`` must arrive WITH a ``past_due_since`` anchor, or the grace window
   cannot be proved and the customer is downgraded on the spot.
2. ``invoice.paid`` must clear the anchor *and* lift the status — clearing one
   without the other recreates the same instant-downgrade from the other side.
3. Every handler must end in ``sync_org_tiers``, or ``User.tier`` (what every gate
   in the codebase actually reads) never moves and the webhook changed nothing.

Stripe is mocked throughout (``_stripe.mock_stripe``); no test makes a network call.
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Tier, User
from apps.billing.models import StripeEvent
from apps.billing.webhooks import handle_event
from apps.tenancy.models import Organization, OrgMembership, Subscription
from apps.tenancy.services import effective_plan

from ._stripe import (
    PRICE_FIRM,
    PRICE_FIRM_SEAT,
    PRICE_SOLO,
    STRIPE_SETTINGS,
    FakeStripe,
    checkout_session_obj,
    event,
    invoice_obj,
    item,
    mock_stripe,
    subscription_obj,
)

SubStatus = Subscription.Status


def make_user(email: str, tier: str = Tier.FREE) -> User:
    return User.objects.create_user(email=email, password="x", tier=tier)


def make_org(slug="acme", *, customer: str | None = "cus_test_1") -> Organization:
    return Organization.objects.create(
        slug=slug,
        name=slug.title(),
        status=Organization.Status.ACTIVE,
        is_personal=True,
        stripe_customer_id=customer,
    )


def make_sub(org, **kwargs) -> Subscription:
    defaults = {
        "product": None,
        "plan": Tier.SOLO,
        "status": SubStatus.ACTIVE,
        "seats": 1,
        "stripe_subscription_id": "sub_test_1",
    }
    defaults.update(kwargs)
    return Subscription.objects.create(org=org, **defaults)


@override_settings(**STRIPE_SETTINGS)
class WebhookBaseTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.org = make_org()
        OrgMembership.objects.create(
            user=self.owner, org=self.org, role=OrgMembership.Role.OWNER
        )

    def tier(self) -> str:
        return User.objects.get(pk=self.owner.pk).tier

    def sub(self) -> Subscription | None:
        return Subscription.objects.filter(org=self.org, product__isnull=True).first()


class IdempotencyTests(WebhookBaseTests):
    def test_replaying_the_same_event_id_is_a_no_op(self):
        evt = event(
            "customer.subscription.created",
            subscription_obj(org_id=self.org.pk, items=[item(PRICE_SOLO, 1)]),
            event_id="evt_dupe",
        )
        with mock_stripe():
            self.assertEqual(handle_event(evt), "processed")
            self.assertEqual(handle_event(evt), "duplicate")

        self.assertEqual(StripeEvent.objects.filter(event_id="evt_dupe").count(), 1)
        ledger = StripeEvent.objects.get(event_id="evt_dupe")
        self.assertIsNotNone(ledger.processed_at)
        self.assertEqual(ledger.type, "customer.subscription.created")
        self.assertEqual(ledger.payload["id"], "evt_dupe")

    def test_a_replay_cannot_undo_a_later_state(self):
        """The real hazard: Stripe redelivers an OLD event after a newer one landed.

        The ledger must make the stale replay a no-op — otherwise a redelivered
        ``created`` (active) would resurrect a subscription the customer has since
        canceled.
        """
        created = event(
            "customer.subscription.created",
            subscription_obj(org_id=self.org.pk),
            event_id="evt_created",
        )
        deleted = event(
            "customer.subscription.deleted",
            subscription_obj(org_id=self.org.pk, status="canceled"),
            event_id="evt_deleted",
        )
        with mock_stripe():
            handle_event(created)
            handle_event(deleted)
            self.assertEqual(handle_event(created), "duplicate")

        self.assertEqual(self.sub().status, SubStatus.CANCELED)
        self.assertEqual(self.tier(), Tier.FREE)

    def test_unhandled_event_type_is_recorded_and_ignored(self):
        evt = event("customer.updated", {"id": "cus_test_1", "object": "customer"})
        with mock_stripe():
            self.assertEqual(handle_event(evt), "unhandled")
        self.assertIsNotNone(StripeEvent.objects.get(event_id="evt_test_1").processed_at)

    def test_event_that_maps_to_no_org_is_recorded_not_retried(self):
        evt = event(
            "customer.subscription.updated",
            subscription_obj(customer="cus_unknown", sub_id="sub_unknown"),
        )
        with mock_stripe():
            self.assertEqual(handle_event(evt), "no_org")
        self.assertIsNotNone(StripeEvent.objects.get(event_id="evt_test_1").processed_at)


class OrgResolutionTests(WebhookBaseTests):
    def test_resolves_by_metadata_org_id(self):
        Organization.objects.filter(pk=self.org.pk).update(stripe_customer_id=None)
        evt = event(
            "customer.subscription.created", subscription_obj(org_id=self.org.pk)
        )
        with mock_stripe():
            self.assertEqual(handle_event(evt), "processed")
        self.assertIsNotNone(self.sub())

    def test_falls_back_to_stripe_customer_id_when_metadata_is_absent(self):
        """Invoices carry none of our metadata — the customer fallback is load-bearing."""
        evt = event("invoice.payment_failed", invoice_obj(customer="cus_test_1"))
        with mock_stripe():
            self.assertEqual(handle_event(evt), "processed")
        self.assertEqual(self.sub().status, SubStatus.PAST_DUE)

    def test_falls_back_to_a_known_subscription_id(self):
        make_sub(self.org, stripe_subscription_id="sub_known")
        Organization.objects.filter(pk=self.org.pk).update(stripe_customer_id=None)
        evt = event(
            "invoice.paid",
            invoice_obj(customer="cus_unknown", subscription="sub_known"),
        )
        with mock_stripe():
            self.assertEqual(handle_event(evt), "processed")

    def test_reads_the_2025_api_nested_invoice_subscription(self):
        """Stripe moved ``subscription`` under ``parent.subscription_details``."""
        make_sub(self.org, stripe_subscription_id="sub_nested")
        Organization.objects.filter(pk=self.org.pk).update(stripe_customer_id=None)
        invoice = invoice_obj(customer="cus_unknown", subscription=None)
        invoice["parent"] = {
            "type": "subscription_details",
            "subscription_details": {"subscription": "sub_nested"},
        }
        with mock_stripe():
            self.assertEqual(handle_event(event("invoice.paid", invoice)), "processed")


class CheckoutCompletedTests(WebhookBaseTests):
    def test_attaches_subscription_and_grants_the_plan(self):
        fake = FakeStripe(
            subscription=subscription_obj(
                org_id=self.org.pk, status="active", items=[item(PRICE_FIRM, 3)]
            )
        )
        evt = event(
            "checkout.session.completed",
            checkout_session_obj(org_id=self.org.pk, plan="firm", customer="cus_new"),
        )
        with mock_stripe(fake):
            self.assertEqual(handle_event(evt), "processed")

        sub = self.sub()
        self.assertEqual(sub.stripe_subscription_id, "sub_test_1")
        self.assertEqual(sub.plan, Tier.FIRM)
        self.assertEqual(sub.status, SubStatus.ACTIVE)
        self.assertEqual(sub.seats, 3)
        # The customer id from the session is persisted onto the org, so later
        # invoice events (which carry no metadata) can be attributed.
        self.assertEqual(
            Organization.objects.get(pk=self.org.pk).stripe_customer_id, "cus_new"
        )
        # sync_org_tiers ran: the member's cached tier moved.
        self.assertEqual(self.tier(), Tier.FIRM)

    def test_falls_back_to_session_metadata_when_stripe_read_fails(self):
        """A Stripe read failure after a successful payment must not leave the
        customer on ``free`` — the plan we stamped at checkout is the fallback."""
        fake = FakeStripe()

        def boom(*args, **kwargs):
            raise RuntimeError("stripe is down")

        fake.Subscription.retrieve = boom
        evt = event(
            "checkout.session.completed",
            checkout_session_obj(org_id=self.org.pk, plan="firm"),
        )
        with mock_stripe(fake):
            self.assertEqual(handle_event(evt), "processed")

        sub = self.sub()
        self.assertEqual(sub.plan, Tier.FIRM)
        self.assertEqual(sub.status, SubStatus.ACTIVE)
        self.assertEqual(sub.stripe_subscription_id, "sub_test_1")
        self.assertEqual(self.tier(), Tier.FIRM)


class SubscriptionUpsertTests(WebhookBaseTests):
    def test_created_writes_every_column(self):
        evt = event(
            "customer.subscription.created",
            subscription_obj(
                org_id=self.org.pk,
                status="trialing",
                items=[item(PRICE_FIRM, 5)],
                current_period_end=1_800_000_000,
                cancel_at_period_end=True,
                trial_end=1_700_500_000,
            ),
        )
        with mock_stripe():
            handle_event(evt)

        sub = self.sub()
        self.assertEqual(sub.plan, Tier.FIRM)
        self.assertEqual(sub.status, SubStatus.TRIAL)
        self.assertEqual(sub.seats, 5)
        self.assertEqual(sub.stripe_price_id, PRICE_FIRM)
        self.assertEqual(
            sub.current_period_end,
            dt.datetime.fromtimestamp(1_800_000_000, tz=dt.timezone.utc),
        )
        self.assertTrue(sub.cancel_at_period_end)
        self.assertEqual(
            sub.trial_end, dt.datetime.fromtimestamp(1_700_500_000, tz=dt.timezone.utc)
        )
        self.assertEqual(self.tier(), Tier.FIRM)

    @override_settings(**{**STRIPE_SETTINGS, "STRIPE_PRICE_FIRM_SEAT": PRICE_FIRM_SEAT})
    def test_base_plus_seat_subscription_reads_seats_from_the_seat_item(self):
        evt = event(
            "customer.subscription.created",
            subscription_obj(
                org_id=self.org.pk,
                items=[
                    item(PRICE_FIRM, 1, item_id="si_base"),
                    item(PRICE_FIRM_SEAT, 7, item_id="si_seats"),
                ],
            ),
        )
        with mock_stripe():
            handle_event(evt)

        sub = self.sub()
        self.assertEqual(sub.plan, Tier.FIRM)
        self.assertEqual(sub.seats, 7)  # NOT the base item's quantity of 1
        self.assertEqual(sub.stripe_price_id, PRICE_FIRM_SEAT)

    def test_reads_period_end_from_items_on_the_2025_api(self):
        """Stripe moved ``current_period_end`` off the subscription onto its items."""
        line = item(PRICE_SOLO, 1)
        line["current_period_end"] = 1_900_000_000
        obj = subscription_obj(org_id=self.org.pk, items=[line], current_period_end=None)
        with mock_stripe():
            handle_event(event("customer.subscription.updated", obj))

        self.assertEqual(
            self.sub().current_period_end,
            dt.datetime.fromtimestamp(1_900_000_000, tz=dt.timezone.utc),
        )

    def test_unknown_price_falls_back_to_metadata_plan(self):
        evt = event(
            "customer.subscription.created",
            subscription_obj(
                org_id=self.org.pk, plan="firm", items=[item("price_legacy_unknown", 2)]
            ),
        )
        with mock_stripe():
            handle_event(evt)
        self.assertEqual(self.sub().plan, Tier.FIRM)

    def test_unknown_price_and_no_metadata_keeps_the_existing_plan(self):
        """Never silently downgrade a paying customer because of a price we can't map."""
        make_sub(self.org, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        evt = event(
            "customer.subscription.updated",
            subscription_obj(org_id=self.org.pk, items=[item("price_legacy_unknown", 2)]),
        )
        with mock_stripe():
            handle_event(evt)
        self.assertEqual(self.sub().plan, Tier.FIRM)

    def test_unknown_stripe_status_keeps_the_existing_status(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        evt = event(
            "customer.subscription.updated",
            subscription_obj(org_id=self.org.pk, status="some_new_stripe_status"),
        )
        with mock_stripe():
            handle_event(evt)
        self.assertEqual(self.sub().status, SubStatus.ACTIVE)
        self.assertEqual(self.tier(), Tier.SOLO)

    def test_incomplete_grants_nothing(self):
        evt = event(
            "customer.subscription.created",
            subscription_obj(org_id=self.org.pk, status="incomplete"),
        )
        with mock_stripe():
            handle_event(evt)
        self.assertEqual(self.sub().status, SubStatus.UNPAID)
        self.assertEqual(self.tier(), Tier.FREE)

    def test_canceled_drops_every_member_to_free(self):
        member = make_user("member@example.com")
        OrgMembership.objects.create(
            user=member, org=self.org, role=OrgMembership.Role.MEMBER
        )
        make_sub(self.org, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        with mock_stripe():
            handle_event(
                event(
                    "customer.subscription.updated",
                    subscription_obj(org_id=self.org.pk, status="canceled"),
                )
            )

        self.assertEqual(self.sub().status, SubStatus.CANCELED)
        self.assertEqual(self.tier(), Tier.FREE)
        self.assertEqual(User.objects.get(pk=member.pk).tier, Tier.FREE)
        self.assertEqual(effective_plan(member), Tier.FREE)

    def test_deleted_cancels(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        with mock_stripe():
            handle_event(
                event(
                    "customer.subscription.deleted",
                    subscription_obj(org_id=self.org.pk, status="canceled"),
                )
            )
        self.assertEqual(self.sub().status, SubStatus.CANCELED)
        self.assertEqual(self.tier(), Tier.FREE)


class PastDueGraceTests(WebhookBaseTests):
    """THE landmine: ``past_due`` with a NULL anchor grants nothing at all."""

    def test_subscription_updated_to_past_due_stamps_the_anchor(self):
        make_sub(self.org, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        before = timezone.now()
        with mock_stripe():
            handle_event(
                event(
                    "customer.subscription.updated",
                    subscription_obj(
                        org_id=self.org.pk,
                        status="past_due",
                        items=[item(PRICE_FIRM, 1)],
                    ),
                )
            )

        sub = self.sub()
        self.assertEqual(sub.status, SubStatus.PAST_DUE)
        self.assertIsNotNone(sub.past_due_since)  # <- without this, instant downgrade
        self.assertGreaterEqual(sub.past_due_since, before)
        # Still inside the grace window: the customer keeps their plan.
        self.assertEqual(self.tier(), Tier.FIRM)

    def test_payment_failed_stamps_the_anchor_and_keeps_the_plan_in_grace(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        with mock_stripe():
            handle_event(event("invoice.payment_failed", invoice_obj()))

        sub = self.sub()
        self.assertEqual(sub.status, SubStatus.PAST_DUE)
        self.assertIsNotNone(sub.past_due_since)
        self.assertEqual(self.tier(), Tier.SOLO)

    def test_a_second_failure_does_not_push_the_deadline_out(self):
        anchor = timezone.now() - dt.timedelta(days=3)
        make_sub(
            self.org,
            plan=Tier.SOLO,
            status=SubStatus.PAST_DUE,
            past_due_since=anchor,
        )
        with mock_stripe():
            handle_event(
                event("invoice.payment_failed", invoice_obj(), event_id="evt_second")
            )
        self.assertEqual(self.sub().past_due_since, anchor)

    @override_settings(BILLING_PAST_DUE_GRACE_DAYS=7)
    def test_expired_grace_collapses_to_free(self):
        make_sub(
            self.org,
            plan=Tier.FIRM,
            status=SubStatus.PAST_DUE,
            past_due_since=timezone.now() - dt.timedelta(days=8),
        )
        # Any webhook re-syncs tiers; here the grace window has simply run out.
        with mock_stripe():
            handle_event(event("invoice.payment_failed", invoice_obj()))
        self.assertEqual(self.tier(), Tier.FREE)

    def test_invoice_paid_clears_the_anchor_AND_lifts_past_due(self):
        """Clearing the anchor alone would leave ``past_due`` + NULL = grants nothing:
        the customer pays and *immediately* loses access. Both must move."""
        make_sub(
            self.org,
            plan=Tier.FIRM,
            status=SubStatus.PAST_DUE,
            past_due_since=timezone.now() - dt.timedelta(days=2),
        )
        with mock_stripe():
            handle_event(event("invoice.paid", invoice_obj()))

        sub = self.sub()
        self.assertIsNone(sub.past_due_since)
        self.assertEqual(sub.status, SubStatus.ACTIVE)
        self.assertEqual(self.tier(), Tier.FIRM)

    def test_recovering_via_subscription_updated_also_clears_the_anchor(self):
        make_sub(
            self.org,
            plan=Tier.SOLO,
            status=SubStatus.PAST_DUE,
            past_due_since=timezone.now() - dt.timedelta(days=2),
        )
        with mock_stripe():
            handle_event(
                event(
                    "customer.subscription.updated",
                    subscription_obj(org_id=self.org.pk, status="active"),
                )
            )
        self.assertIsNone(self.sub().past_due_since)
        self.assertEqual(self.sub().status, SubStatus.ACTIVE)
        self.assertEqual(self.tier(), Tier.SOLO)


class OrgStatusTests(WebhookBaseTests):
    def test_webhook_never_un_suspends_a_staff_suspended_org(self):
        """``Organization.status`` is the staff kill-switch. A renewal must not
        defeat it — the webhook writes the Subscription, never the org's status."""
        Organization.objects.filter(pk=self.org.pk).update(
            status=Organization.Status.SUSPENDED
        )
        with mock_stripe():
            handle_event(
                event(
                    "customer.subscription.created",
                    subscription_obj(
                        org_id=self.org.pk, status="active", items=[item(PRICE_FIRM, 2)]
                    ),
                )
            )

        self.assertEqual(
            Organization.objects.get(pk=self.org.pk).status,
            Organization.Status.SUSPENDED,
        )
        self.assertEqual(self.sub().status, SubStatus.ACTIVE)
        # Suspended org grants nothing, regardless of a live subscription.
        self.assertEqual(self.tier(), Tier.FREE)
