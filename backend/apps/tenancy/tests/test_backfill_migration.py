"""The 0002_billing backfill, exercised through the real migration executor.

Migrates tenancy back to 0001, writes rows through the *historical* models (which
still have the user-held ``Subscription.user`` FK), then migrates forward and
asserts what the RunPython produced. That is the only way to test a data migration
honestly: the current models cannot even express the pre-migration schema.

TransactionTestCase (not TestCase) because migrations run DDL and cannot live
inside the test's transaction. ``serialized_rollback`` restores the seed-migration
data the flush would otherwise drop for the rest of the suite.
"""

from __future__ import annotations

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.accounts.models import User

MIGRATE_FROM = [("tenancy", "0001_initial")]
MIGRATE_TO = [("tenancy", "0002_billing")]


class BackfillBillingOrgsTests(TransactionTestCase):
    serialized_rollback = True

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        executor.loader.build_graph()
        return executor.loader.project_state(targets).apps

    def setUp(self):
        # Roll tenancy (and its dependents) back to the pre-billing schema.
        self.old_apps = self._migrate(MIGRATE_FROM)

    def tearDown(self):
        # Leave the test database on the current schema for whatever runs next.
        self._migrate(MIGRATE_TO)

    def _old(self, name):
        """A tenancy model as it looked BEFORE 0002 (Subscription still has ``user``).

        Only ``tenancy`` is reverted, so users are created through the CURRENT
        ``User`` model — which is exactly what the live accounts schema holds.
        """
        return self.old_apps.get_model("tenancy", name)

    def test_every_user_gets_a_personal_org_and_paid_users_get_a_subscription(self):
        User.objects.create_user(email="free@example.com", password="x", tier="free")
        User.objects.create_user(
            email="paid@example.com", password="x", tier="firm", full_name="Paid Person"
        )

        new_apps = self._migrate(MIGRATE_TO)
        Organization = new_apps.get_model("tenancy", "Organization")
        OrgMembership = new_apps.get_model("tenancy", "OrgMembership")
        Subscription = new_apps.get_model("tenancy", "Subscription")

        self.assertEqual(Organization.objects.filter(is_personal=True).count(), 2)

        free_org = Organization.objects.get(memberships__user__email="free@example.com")
        self.assertTrue(free_org.is_personal)
        self.assertEqual(free_org.status, "active")
        self.assertEqual(free_org.slug, "free")
        self.assertEqual(free_org.name, "free@example.com (Personal)")
        self.assertEqual(
            OrgMembership.objects.get(org=free_org).role, "owner"
        )
        # A free user gets NO subscription row.
        self.assertFalse(Subscription.objects.filter(org=free_org).exists())

        paid_org = Organization.objects.get(memberships__user__email="paid@example.com")
        self.assertEqual(paid_org.name, "Paid Person (Personal)")
        sub = Subscription.objects.get(org=paid_org)
        self.assertIsNone(sub.product)  # flagship = full corpus
        self.assertEqual(sub.plan, "firm")
        self.assertEqual(sub.status, "active")
        self.assertEqual(sub.seats, 1)
        self.assertIsNone(sub.stripe_subscription_id)

    def test_duplicate_email_local_parts_get_deduplicated_slugs(self):
        User.objects.create_user(email="nick@a.com", password="x", tier="free")
        User.objects.create_user(email="nick@b.com", password="x", tier="free")

        new_apps = self._migrate(MIGRATE_TO)
        Organization = new_apps.get_model("tenancy", "Organization")
        slugs = set(
            Organization.objects.filter(is_personal=True).values_list("slug", flat=True)
        )
        self.assertEqual(slugs, {"nick", "nick-2"})

    def test_user_held_subscription_moves_to_the_personal_org(self):
        Product = self._old("Product")
        Subscription = self._old("Subscription")

        user = User.objects.create_user(
            email="holder@example.com", password="x", tier="solo"
        )
        product = Product.objects.create(slug="ethics", name="Ethics")
        # user_id, not user: the historical Subscription's FK refuses an instance
        # of the *current* User class (different model registry, same table).
        Subscription.objects.create(product=product, user_id=user.pk, status="active")

        new_apps = self._migrate(MIGRATE_TO)
        Organization = new_apps.get_model("tenancy", "Organization")
        NewSub = new_apps.get_model("tenancy", "Subscription")

        org = Organization.objects.get(memberships__user__email="holder@example.com")
        moved = NewSub.objects.get(product__slug="ethics")
        self.assertEqual(moved.org_id, org.id)
        self.assertEqual(moved.status, "active")  # product preserved, status intact
        # …and the solo tier still produced its own comped flagship row.
        flagship = NewSub.objects.get(org=org, product__isnull=True)
        self.assertEqual(flagship.plan, "solo")

    def test_existing_non_personal_org_is_left_alone(self):
        Organization = self._old("Organization")
        Organization.objects.create(slug="iowa-bar", name="Iowa Bar", status="active")

        new_apps = self._migrate(MIGRATE_TO)
        NewOrg = new_apps.get_model("tenancy", "Organization")
        bar = NewOrg.objects.get(slug="iowa-bar")
        self.assertFalse(bar.is_personal)
        self.assertEqual(bar.status, "active")

    def test_backfill_is_idempotent_when_re_run(self):
        User.objects.create_user(email="rerun@example.com", password="x", tier="solo")

        new_apps = self._migrate(MIGRATE_TO)
        Organization = new_apps.get_model("tenancy", "Organization")
        Subscription = new_apps.get_model("tenancy", "Subscription")
        OrgMembership = new_apps.get_model("tenancy", "OrgMembership")

        # Re-run the RunPython body against the post-migration state, exactly as a
        # re-applied / partially-applied migration would.
        from importlib import import_module

        migration = import_module("apps.tenancy.migrations.0002_billing")
        migration.backfill_billing_orgs(new_apps, None)

        self.assertEqual(Organization.objects.filter(is_personal=True).count(), 1)
        self.assertEqual(OrgMembership.objects.count(), 1)
        self.assertEqual(Subscription.objects.count(), 1)
