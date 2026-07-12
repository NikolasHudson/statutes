"""Seat sync — a member is a seat, and a seat is a line on the bill.

Also covers the wiring: ``tenancy.services.add_member`` / ``remove_member`` reach
``apps.billing.seats.sync_seats`` through the ImportError-guarded indirection in
``tenancy.services.sync_seats``, so adding a member really does move the Stripe
quantity with no edit to the tenancy layer.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.accounts.models import Tier, User
from apps.billing.seats import sync_seats
from apps.tenancy import services as tenancy
from apps.tenancy.models import Organization, OrgMembership, Subscription

from ._stripe import (
    PRICE_FIRM,
    PRICE_FIRM_SEAT,
    STRIPE_SETTINGS,
    FakeStripe,
    item,
    mock_stripe,
    subscription_obj,
)

SubStatus = Subscription.Status


def make_user(email: str) -> User:
    return User.objects.create_user(email=email, password="x", tier=Tier.FREE)


class SeatSyncTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.org = Organization.objects.create(
            slug="acme", name="Acme", status=Organization.Status.ACTIVE,
            is_personal=True, stripe_customer_id="cus_test_1",
        )
        OrgMembership.objects.create(
            user=self.owner, org=self.org, role=OrgMembership.Role.OWNER
        )
        self.sub = Subscription.objects.create(
            org=self.org, product=None, plan=Tier.FIRM, status=SubStatus.ACTIVE,
            seats=1, stripe_subscription_id="sub_test_1",
        )

    def add_members(self, n: int) -> None:
        for i in range(n):
            OrgMembership.objects.create(
                user=make_user(f"m{i}@example.com"),
                org=self.org,
                role=OrgMembership.Role.MEMBER,
            )

    # -- the no-ops --------------------------------------------------------

    @override_settings(STRIPE_SECRET_KEY="")
    def test_no_op_when_stripe_is_unconfigured(self):
        self.add_members(2)
        with mock_stripe() as stripe:
            self.assertIsNone(sync_seats(self.org))
        self.assertEqual(stripe.call_names(), [])

    @override_settings(**STRIPE_SETTINGS)
    def test_no_op_for_a_comped_subscription_with_no_stripe_id(self):
        Subscription.objects.filter(pk=self.sub.pk).update(stripe_subscription_id=None)
        with mock_stripe() as stripe:
            self.assertIsNone(sync_seats(self.org))
        self.assertEqual(stripe.call_names(), [])

    @override_settings(**STRIPE_SETTINGS)
    def test_no_op_for_a_canceled_subscription(self):
        Subscription.objects.filter(pk=self.sub.pk).update(status=SubStatus.CANCELED)
        with mock_stripe() as stripe:
            self.assertIsNone(sync_seats(self.org))
        self.assertEqual(stripe.call_names(), [])

    @override_settings(**STRIPE_SETTINGS)
    def test_no_write_when_the_quantity_already_matches(self):
        """create_prorations means every write is a line on the next invoice —
        re-sending the same quantity would litter it with zero-value prorations."""
        fake = FakeStripe(subscription=subscription_obj(items=[item(PRICE_FIRM, 1)]))
        with mock_stripe(fake):
            self.assertEqual(sync_seats(self.org), 1)
        self.assertNotIn("SubscriptionItem.modify", fake.call_names())

    # -- the writes --------------------------------------------------------

    @override_settings(**STRIPE_SETTINGS)
    def test_pushes_the_seat_count_with_prorations(self):
        self.add_members(3)  # 4 members total
        fake = FakeStripe(
            subscription=subscription_obj(items=[item(PRICE_FIRM, 1, item_id="si_x")])
        )
        with mock_stripe(fake):
            self.assertEqual(sync_seats(self.org), 4)

        args = fake.call_args("SubscriptionItem.modify")
        self.assertEqual(args["id"], "si_x")
        self.assertEqual(args["quantity"], 4)
        self.assertEqual(args["proration_behavior"], "create_prorations")
        self.assertEqual(Subscription.objects.get(pk=self.sub.pk).seats, 4)

    @override_settings(**STRIPE_SETTINGS)
    def test_quantity_never_drops_below_one(self):
        OrgMembership.objects.filter(org=self.org).delete()  # 0 members
        fake = FakeStripe(subscription=subscription_obj(items=[item(PRICE_FIRM, 5)]))
        with mock_stripe(fake):
            self.assertEqual(sync_seats(self.org), 1)
        self.assertEqual(fake.call_args("SubscriptionItem.modify")["quantity"], 1)

    @override_settings(**{**STRIPE_SETTINGS, "STRIPE_PRICE_FIRM_SEAT": PRICE_FIRM_SEAT})
    def test_moves_the_seat_item_not_the_base_item(self):
        self.add_members(2)  # 3 members
        fake = FakeStripe(
            subscription=subscription_obj(
                items=[
                    item(PRICE_FIRM, 1, item_id="si_base"),
                    item(PRICE_FIRM_SEAT, 1, item_id="si_seats"),
                ]
            )
        )
        with mock_stripe(fake):
            sync_seats(self.org)
        args = fake.call_args("SubscriptionItem.modify")
        self.assertEqual(args["id"], "si_seats")  # NOT si_base
        self.assertEqual(args["quantity"], 3)

    @override_settings(**STRIPE_SETTINGS)
    def test_ambiguous_multi_item_subscription_is_left_alone(self):
        """Two unlabelled items and no STRIPE_PRICE_FIRM_SEAT: moving the wrong
        line would mis-bill. Log and leave it."""
        fake = FakeStripe(
            subscription=subscription_obj(
                items=[item(PRICE_FIRM, 1, item_id="a"), item("price_addon", 1, item_id="b")]
            )
        )
        with mock_stripe(fake):
            self.assertIsNone(sync_seats(self.org))
        self.assertNotIn("SubscriptionItem.modify", fake.call_names())


@override_settings(**STRIPE_SETTINGS)
class TenancyWiringTests(TestCase):
    """apps.tenancy.services.sync_seats resolves to us at call time (ImportError
    guard). These prove the seam is actually connected."""

    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.org = Organization.objects.create(
            slug="acme", name="Acme", status=Organization.Status.ACTIVE,
            stripe_customer_id="cus_test_1",
        )
        OrgMembership.objects.create(
            user=self.owner, org=self.org, role=OrgMembership.Role.OWNER
        )
        Subscription.objects.create(
            org=self.org, product=None, plan=Tier.FIRM, status=SubStatus.ACTIVE,
            seats=1, stripe_subscription_id="sub_test_1",
        )

    def test_add_member_bumps_the_stripe_quantity(self):
        newcomer = make_user("new@example.com")
        fake = FakeStripe(subscription=subscription_obj(items=[item(PRICE_FIRM, 1)]))
        with mock_stripe(fake):
            tenancy.add_member(self.org, newcomer, OrgMembership.Role.MEMBER)

        self.assertEqual(fake.call_args("SubscriptionItem.modify")["quantity"], 2)
        # …and the new member inherits the org's plan.
        self.assertEqual(User.objects.get(pk=newcomer.pk).tier, Tier.FIRM)

    def test_remove_member_drops_the_stripe_quantity(self):
        leaver = make_user("leaver@example.com")
        OrgMembership.objects.create(
            user=leaver, org=self.org, role=OrgMembership.Role.MEMBER
        )
        fake = FakeStripe(subscription=subscription_obj(items=[item(PRICE_FIRM, 2)]))
        with mock_stripe(fake):
            tenancy.remove_member(self.org, leaver)

        self.assertEqual(fake.call_args("SubscriptionItem.modify")["quantity"], 1)
        self.assertEqual(User.objects.get(pk=leaver.pk).tier, Tier.FREE)

    def test_last_owner_cannot_be_removed(self):
        with mock_stripe():
            with self.assertRaises(tenancy.LastOwnerError):
                tenancy.remove_member(self.org, self.owner)
        self.assertEqual(tenancy.seat_count(self.org), 1)

    def test_a_stripe_outage_does_not_lose_the_membership_change(self):
        """tenancy.services.sync_seats swallows Stripe errors on purpose: losing a
        member because Stripe hiccuped is far worse than a stale quantity."""
        newcomer = make_user("new@example.com")
        fake = FakeStripe()

        def boom(*args, **kwargs):
            raise RuntimeError("stripe is down")

        fake.Subscription.retrieve = boom
        with mock_stripe(fake):
            tenancy.add_member(self.org, newcomer, OrgMembership.Role.MEMBER)

        self.assertTrue(
            OrgMembership.objects.filter(org=self.org, user=newcomer).exists()
        )
        self.assertEqual(User.objects.get(pk=newcomer.pk).tier, Tier.FIRM)
