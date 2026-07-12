"""The tier rule — apps.tenancy.services.

``effective_plan`` is the load-bearing function of the whole billing design: every
tier gate in the codebase (chat, REST, MCP, entitlement) reads ``user.tier``, which
is nothing but a cache of this. So the truth table below — subscription status ×
org status × grace window × multi-org max — is the test that matters most.
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Tier, User
from apps.corpus.models import Jurisdiction
from apps.tenancy.entitlement import is_entitled
from apps.tenancy.models import (
    Organization,
    OrgMembership,
    Product,
    Subscription,
)
from apps.tenancy.services import (
    LastOwnerError,
    Role,
    TenancyError,
    accept_invitation,
    add_member,
    billing_org,
    change_role,
    effective_plan,
    ensure_personal_org,
    orgs_for,
    remove_member,
    seat_count,
    sync_org_tiers,
    sync_user_tier,
)

OrgStatus = Organization.Status
SubStatus = Subscription.Status


def make_user(email: str, tier: str = Tier.FREE) -> User:
    return User.objects.create_user(email=email, password="x", tier=tier)


def make_org(
    slug: str = "acme", status: str = OrgStatus.ACTIVE, *, is_personal: bool = False
) -> Organization:
    return Organization.objects.create(
        slug=slug, name=slug.title(), status=status, is_personal=is_personal
    )


def make_sub(
    org: Organization,
    *,
    plan: str = Tier.SOLO,
    status: str = SubStatus.ACTIVE,
    past_due_since=None,
    product: Product | None = None,
) -> Subscription:
    return Subscription.objects.create(
        org=org,
        product=product,
        plan=plan,
        status=status,
        past_due_since=past_due_since,
    )


@override_settings(BILLING_PAST_DUE_GRACE_DAYS=7)
class EffectivePlanTruthTableTests(TestCase):
    """Every (subscription status × org status) cell, plus the grace window."""

    def setUp(self):
        self.user = make_user("truth@example.com")
        self.org = make_org("truth-org", is_personal=True)
        OrgMembership.objects.create(user=self.user, org=self.org, role=Role.OWNER)

    def _plan(self) -> str:
        return effective_plan(self.user)

    # --- no subscription at all -------------------------------------------------
    def test_no_org_at_all_is_free(self):
        loner = make_user("loner@example.com")
        self.assertEqual(effective_plan(loner), Tier.FREE)

    def test_org_without_subscription_is_free(self):
        self.assertEqual(self._plan(), Tier.FREE)

    # --- subscription status axis (org active) ----------------------------------
    def test_subscription_status_axis(self):
        cases = {
            SubStatus.TRIAL: Tier.SOLO,
            SubStatus.ACTIVE: Tier.SOLO,
            SubStatus.CANCELED: Tier.FREE,
            SubStatus.UNPAID: Tier.FREE,
        }
        for status, expected in cases.items():
            with self.subTest(subscription=status):
                Subscription.objects.filter(org=self.org).delete()
                make_sub(self.org, plan=Tier.SOLO, status=status)
                self.assertEqual(self._plan(), expected)

    # --- org status axis (subscription active) ----------------------------------
    def test_org_status_axis(self):
        cases = {
            OrgStatus.TRIAL: Tier.SOLO,
            OrgStatus.ACTIVE: Tier.SOLO,
            OrgStatus.PAST_DUE: Tier.SOLO,  # org-level past_due still grants;
            # the SUBSCRIPTION's status + grace window is what revokes.
            OrgStatus.SUSPENDED: Tier.FREE,  # staff kill-switch
            OrgStatus.CANCELED: Tier.FREE,
        }
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        for status, expected in cases.items():
            with self.subTest(org=status):
                self.org.status = status
                self.org.save(update_fields=["status"])
                self.assertEqual(self._plan(), expected)

    def test_suspended_org_revokes_even_a_trialing_subscription(self):
        make_sub(self.org, plan=Tier.FIRM, status=SubStatus.TRIAL)
        self.org.status = OrgStatus.SUSPENDED
        self.org.save(update_fields=["status"])
        self.assertEqual(self._plan(), Tier.FREE)

    # --- the past_due grace window ----------------------------------------------
    def test_past_due_inside_grace_still_grants(self):
        make_sub(
            self.org,
            plan=Tier.FIRM,
            status=SubStatus.PAST_DUE,
            past_due_since=timezone.now() - dt.timedelta(days=3),
        )
        self.assertEqual(self._plan(), Tier.FIRM)

    def test_past_due_past_grace_collapses_to_free(self):
        make_sub(
            self.org,
            plan=Tier.FIRM,
            status=SubStatus.PAST_DUE,
            past_due_since=timezone.now() - dt.timedelta(days=8),
        )
        self.assertEqual(self._plan(), Tier.FREE)

    def test_past_due_on_the_grace_boundary_is_free(self):
        make_sub(
            self.org,
            plan=Tier.FIRM,
            status=SubStatus.PAST_DUE,
            past_due_since=timezone.now() - dt.timedelta(days=7, seconds=1),
        )
        self.assertEqual(self._plan(), Tier.FREE)

    def test_past_due_without_an_anchor_grants_nothing(self):
        """The webhook stamps ``past_due_since`` when it flips the status. With no
        anchor we cannot prove we are inside the window, so we do not grant."""
        make_sub(self.org, plan=Tier.FIRM, status=SubStatus.PAST_DUE)
        self.assertEqual(self._plan(), Tier.FREE)

    @override_settings(BILLING_PAST_DUE_GRACE_DAYS=30)
    def test_grace_window_is_settings_driven(self):
        make_sub(
            self.org,
            plan=Tier.SOLO,
            status=SubStatus.PAST_DUE,
            past_due_since=timezone.now() - dt.timedelta(days=8),
        )
        self.assertEqual(self._plan(), Tier.SOLO)

    # --- product-scoped subscriptions never grant a plan ------------------------
    def test_scoped_product_subscription_grants_no_plan(self):
        jur = Jurisdiction.objects.create(slug="iowa-x", name="Iowa X", abbreviation="IX")
        product = Product.objects.create(
            slug="ethics", name="Ethics", jurisdiction=jur,
            allowed_source_slugs=["iowa-court-rules"],
        )
        make_sub(self.org, plan=Tier.FIRM, status=SubStatus.ACTIVE, product=product)
        # A site license to a scoped app is not a full-corpus plan.
        self.assertEqual(self._plan(), Tier.FREE)

    # --- multi-org: the MAX plan wins -------------------------------------------
    def test_multi_org_takes_the_max_plan(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        firm = make_org("firm")
        make_sub(firm, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        OrgMembership.objects.create(user=self.user, org=firm, role=Role.MEMBER)
        self.assertEqual(self._plan(), Tier.FIRM)

    def test_multi_org_falls_back_when_the_better_org_lapses(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        firm = make_org("firm2")
        firm_sub = make_sub(firm, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        OrgMembership.objects.create(user=self.user, org=firm, role=Role.MEMBER)
        self.assertEqual(self._plan(), Tier.FIRM)

        firm_sub.status = SubStatus.CANCELED
        firm_sub.save(update_fields=["status"])
        self.assertEqual(self._plan(), Tier.SOLO)  # personal plan still stands

    def test_multi_org_all_dead_is_free(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.CANCELED)
        firm = make_org("firm3", status=OrgStatus.SUSPENDED)
        make_sub(firm, plan=Tier.CUSTOM, status=SubStatus.ACTIVE)
        OrgMembership.objects.create(user=self.user, org=firm, role=Role.MEMBER)
        self.assertEqual(self._plan(), Tier.FREE)

    def test_custom_outranks_firm_outranks_solo(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        for slug, plan in (("o-firm", Tier.FIRM), ("o-custom", Tier.CUSTOM)):
            org = make_org(slug)
            make_sub(org, plan=plan, status=SubStatus.ACTIVE)
            OrgMembership.objects.create(user=self.user, org=org, role=Role.MEMBER)
        self.assertEqual(self._plan(), Tier.CUSTOM)


class TierSyncTests(TestCase):
    def setUp(self):
        self.user = make_user("sync@example.com", tier=Tier.FREE)
        self.org = ensure_personal_org(self.user)

    def test_sync_writes_and_reports_change(self):
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        self.assertTrue(sync_user_tier(self.user))
        self.user.refresh_from_db()
        self.assertEqual(self.user.tier, Tier.SOLO)
        # Idempotent: a second sync is a no-op.
        self.assertFalse(sync_user_tier(self.user))

    def test_cancellation_drops_the_cached_tier_to_free(self):
        sub = make_sub(self.org, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        sync_user_tier(self.user)
        sub.status = SubStatus.CANCELED
        sub.save(update_fields=["status"])
        self.assertTrue(sync_user_tier(self.user))
        self.user.refresh_from_db()
        self.assertEqual(self.user.tier, Tier.FREE)

    def test_sync_org_tiers_touches_every_member(self):
        firm = make_org("bigfirm")
        make_sub(firm, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        members = [make_user(f"m{i}@example.com") for i in range(3)]
        for m in members:
            OrgMembership.objects.create(user=m, org=firm, role=Role.MEMBER)

        sync_org_tiers(firm)
        for m in members:
            m.refresh_from_db()
            self.assertEqual(m.tier, Tier.FIRM)

        firm.status = OrgStatus.SUSPENDED
        firm.save(update_fields=["status"])
        sync_org_tiers(firm)
        for m in members:
            m.refresh_from_db()
            self.assertEqual(m.tier, Tier.FREE)


class PersonalOrgTests(TestCase):
    def test_ensure_is_idempotent_and_makes_an_owner(self):
        user = make_user("solo@example.com")
        org = ensure_personal_org(user)
        again = ensure_personal_org(user)
        self.assertEqual(org.pk, again.pk)
        self.assertTrue(org.is_personal)
        self.assertEqual(org.status, OrgStatus.ACTIVE)
        self.assertEqual(
            OrgMembership.objects.get(user=user, org=org).role, Role.OWNER
        )
        self.assertEqual(billing_org(user).pk, org.pk)
        self.assertEqual(seat_count(org), 1)

    def test_slug_is_derived_from_the_email_and_deduplicated(self):
        a = ensure_personal_org(make_user("nick@example.com"))
        b = ensure_personal_org(make_user("nick@other.com"))
        self.assertEqual(a.slug, "nick")
        self.assertEqual(b.slug, "nick-2")

    def test_billing_org_is_the_personal_one_not_the_firm(self):
        user = make_user("dual@example.com")
        personal = ensure_personal_org(user)
        firm = make_org("dual-firm")
        OrgMembership.objects.create(user=user, org=firm, role=Role.MEMBER)
        self.assertEqual(billing_org(user).pk, personal.pk)
        self.assertEqual(orgs_for(user).count(), 2)


class MembershipMutationTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.org = make_org("firm-x")
        OrgMembership.objects.create(user=self.owner, org=self.org, role=Role.OWNER)
        make_sub(self.org, plan=Tier.FIRM, status=SubStatus.ACTIVE)
        sync_org_tiers(self.org)

    def test_add_member_grants_the_org_plan_and_a_seat(self):
        newbie = make_user("new@example.com")
        self.assertEqual(seat_count(self.org), 1)
        add_member(self.org, newbie, Role.MEMBER, actor=self.owner)
        newbie.refresh_from_db()
        self.assertEqual(newbie.tier, Tier.FIRM)
        self.assertEqual(seat_count(self.org), 2)

    def test_add_member_is_idempotent(self):
        newbie = make_user("new2@example.com")
        add_member(self.org, newbie, Role.MEMBER)
        add_member(self.org, newbie, Role.ADMIN)  # already a member → no change
        self.assertEqual(seat_count(self.org), 2)
        self.assertEqual(
            OrgMembership.objects.get(org=self.org, user=newbie).role, Role.MEMBER
        )

    def test_remove_member_drops_them_back_to_free(self):
        newbie = make_user("new3@example.com")
        add_member(self.org, newbie, Role.MEMBER)
        remove_member(self.org, newbie, actor=self.owner)
        newbie.refresh_from_db()
        self.assertEqual(newbie.tier, Tier.FREE)
        self.assertEqual(seat_count(self.org), 1)

    def test_removed_member_keeps_a_plan_from_another_org(self):
        newbie = make_user("new4@example.com")
        personal = ensure_personal_org(newbie)
        make_sub(personal, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        add_member(self.org, newbie, Role.MEMBER)
        newbie.refresh_from_db()
        self.assertEqual(newbie.tier, Tier.FIRM)

        remove_member(self.org, newbie)
        newbie.refresh_from_db()
        self.assertEqual(newbie.tier, Tier.SOLO)

    def test_cannot_remove_the_last_owner(self):
        with self.assertRaises(LastOwnerError):
            remove_member(self.org, self.owner)
        self.assertEqual(seat_count(self.org), 1)

    def test_can_remove_an_owner_when_another_remains(self):
        second = make_user("owner2@example.com")
        add_member(self.org, second, Role.OWNER)
        remove_member(self.org, self.owner)
        self.assertEqual(seat_count(self.org), 1)

    def test_cannot_demote_the_last_owner(self):
        with self.assertRaises(LastOwnerError):
            change_role(self.org, self.owner, Role.MEMBER)
        self.assertEqual(
            OrgMembership.objects.get(org=self.org, user=self.owner).role, Role.OWNER
        )

    def test_change_role_promotes(self):
        member = make_user("prom@example.com")
        add_member(self.org, member, Role.MEMBER)
        change_role(self.org, member, Role.ADMIN, actor=self.owner)
        self.assertEqual(
            OrgMembership.objects.get(org=self.org, user=member).role, Role.ADMIN
        )

    def test_unknown_role_is_refused(self):
        member = make_user("bad@example.com")
        add_member(self.org, member, Role.MEMBER)
        with self.assertRaises(TenancyError):
            change_role(self.org, member, "sysadmin")

    def test_audit_rows_are_written(self):
        from apps.accounts.audit import AuditEvent

        member = make_user("aud@example.com")
        add_member(self.org, member, Role.MEMBER, actor=self.owner)
        change_role(self.org, member, Role.ADMIN, actor=self.owner)
        remove_member(self.org, member, actor=self.owner)
        types = list(
            AuditEvent.objects.filter(actor=self.owner).values_list(
                "event_type", flat=True
            )
        )
        self.assertCountEqual(
            types,
            [
                AuditEvent.Event.ORG_MEMBER_ADD,
                AuditEvent.Event.ORG_ROLE_CHANGE,
                AuditEvent.Event.ORG_MEMBER_REMOVE,
            ],
        )


class EntitlementTests(TestCase):
    """The scoped-product gate, now reading plans instead of the raw tier column."""

    def setUp(self):
        jur = Jurisdiction.objects.create(slug="iowa-e", name="Iowa E", abbreviation="IE")
        self.product = Product.objects.create(
            slug="ethics-e", name="Ethics", jurisdiction=jur,
            allowed_source_slugs=["iowa-court-rules"],
        )
        self.user = make_user("ent@example.com")
        self.personal = ensure_personal_org(self.user)

    def test_free_user_is_not_entitled(self):
        self.assertFalse(is_entitled(self.user, self.product))

    def test_full_corpus_plan_is_entitled_to_the_scoped_app(self):
        make_sub(self.personal, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        self.assertTrue(is_entitled(self.user, self.product))

    def test_a_stale_tier_column_does_not_grant_access(self):
        """The whole point of routing entitlement through effective_plan: a user
        whose subscription was canceled but whose cached tier was not yet synced
        must NOT still get in."""
        sub = make_sub(self.personal, plan=Tier.SOLO, status=SubStatus.ACTIVE)
        sync_user_tier(self.user)
        sub.status = SubStatus.CANCELED
        sub.save(update_fields=["status"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.tier, Tier.SOLO)  # cache is stale on purpose
        self.assertFalse(is_entitled(self.user, self.product))

    def test_org_site_license_entitles_a_free_member(self):
        bar = make_org("iowa-bar-t")
        make_sub(bar, plan=Tier.FREE, status=SubStatus.ACTIVE, product=self.product)
        OrgMembership.objects.create(user=self.user, org=bar, role=Role.MEMBER)
        self.assertTrue(is_entitled(self.user, self.product))

    def test_suspended_org_site_license_does_not_entitle(self):
        bar = make_org("iowa-bar-s", status=OrgStatus.SUSPENDED)
        make_sub(bar, plan=Tier.FREE, status=SubStatus.ACTIVE, product=self.product)
        OrgMembership.objects.create(user=self.user, org=bar, role=Role.MEMBER)
        self.assertFalse(is_entitled(self.user, self.product))


class InvitationServiceTests(TestCase):
    """``accept_invitation`` is implemented in this module (the org REST API in
    apps/api/orgs.py and the registration hook both call it). Its full validation
    matrix — expiry, revocation, email binding, idempotency — is exercised in
    apps/api/tests/test_orgs.py alongside the endpoints; this is the smoke test
    that the service-layer entry point exists and refuses a garbage token."""

    def test_unknown_token_is_refused(self):
        user = make_user("inv@example.com")
        with self.assertRaises(TenancyError):
            accept_invitation(user, "sometoken")


class ReconcileTiersCommandTests(TestCase):
    """The cron-able drift reconciler for the derived ``User.tier`` cache."""

    def setUp(self):
        self.user = make_user("drift@example.com", tier=Tier.FIRM)  # cache lies
        self.org = ensure_personal_org(self.user)
        make_sub(self.org, plan=Tier.SOLO, status=SubStatus.ACTIVE)

    def _run(self, *args) -> str:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command("reconcile_tiers", *args, stdout=out)
        except SystemExit:  # exit(1) signals "drift found, not fixed"
            pass
        return out.getvalue()

    def test_dry_run_reports_but_does_not_write(self):
        output = self._run()
        self.assertIn("drift@example.com: firm → solo", output)
        self.user.refresh_from_db()
        self.assertEqual(self.user.tier, Tier.FIRM)

    def test_fix_writes_the_effective_plan(self):
        self._run("--fix")
        self.user.refresh_from_db()
        self.assertEqual(self.user.tier, Tier.SOLO)
        # Clean second pass.
        self.assertIn("no tier drift", self._run())
