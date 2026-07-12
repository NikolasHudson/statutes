"""Billing moves onto the Organization.

Schema: Organization gains the billing columns (is_personal, Stripe customer,
status kill-switch, updated_at); Subscription becomes org-only + billing-anchored
(the user FK and its XOR constraint are dropped, ``product`` becomes nullable =
the flagship full-corpus plan, plus plan/Stripe/seat/period columns); OrgInvitation
is new.

Data (``backfill_billing_orgs``): every existing User gets a personal Organization
+ an OWNER membership, a paid tier becomes a comped flagship Subscription, and the
pre-existing user-held Subscriptions move to their owner's personal org. The
function is idempotent — it checks for an existing personal org / flagship
subscription before creating one — so a partially-migrated database can be
re-run without duplicating anything.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.utils.text import slugify

import apps.tenancy.models


def backfill_billing_orgs(apps, schema_editor):
    """Personal orgs + comped plans + move the user-held subscriptions.

    Idempotent: every write is guarded by an existence check, so re-running it (on
    a partially-migrated DB, or by hand) creates nothing twice.
    """
    User = apps.get_model("accounts", "User")
    Organization = apps.get_model("tenancy", "Organization")
    OrgMembership = apps.get_model("tenancy", "OrgMembership")
    Subscription = apps.get_model("tenancy", "Subscription")

    taken_slugs = set(Organization.objects.values_list("slug", flat=True))

    def unique_slug(base: str) -> str:
        stem = (slugify(base) or "user")[:40]
        slug = stem
        n = 1
        while slug in taken_slugs:
            n += 1
            slug = f"{stem}-{n}"
        taken_slugs.add(slug)
        return slug

    # user_id -> their existing personal org (re-run safety).
    personal: dict[int, object] = {}
    for m in OrgMembership.objects.filter(org__is_personal=True).select_related("org"):
        personal.setdefault(m.user_id, m.org)

    for user in User.objects.all().iterator():
        org = personal.get(user.id)
        if org is None:
            display = (user.full_name or user.email or f"user-{user.id}").strip()
            org = Organization.objects.create(
                slug=unique_slug((user.email or "").split("@")[0] or f"user-{user.id}"),
                name=f"{display} (Personal)"[:200],
                status="active",
                is_personal=True,
            )
            OrgMembership.objects.create(user=user, org=org, role="owner")
            personal[user.id] = org

        # A paid tier becomes a comped flagship subscription (no Stripe id).
        if user.tier and user.tier != "free":
            if not Subscription.objects.filter(org=org, product__isnull=True).exists():
                Subscription.objects.create(
                    org=org,
                    product=None,
                    plan=user.tier,
                    status="active",
                    seats=1,
                )

    # The pre-existing user-held subscriptions move to that user's personal org,
    # preserving ``product``. Non-personal orgs (e.g. iowa-bar) are left alone.
    # The field check keeps this callable against the POST-migration model state
    # too (where the ``user`` FK is gone), so re-running the backfill on an
    # already-migrated database is a no-op rather than a FieldError.
    if any(f.name == "user" for f in Subscription._meta.get_fields()):
        for sub in Subscription.objects.filter(user__isnull=False):
            org = personal.get(sub.user_id)
            if org is None:  # pragma: no cover — the user FK guarantees the row
                continue
            clash = (
                Subscription.objects.filter(org=org, product_id=sub.product_id)
                .exclude(pk=sub.pk)
                .exists()
            )
            if clash:
                # Already migrated on an earlier run (or the org holds the same
                # product some other way) — drop the redundant user-held row.
                sub.delete()
                continue
            sub.org = org
            sub.user = None
            sub.save(update_fields=["org", "user"])

    # Postgres refuses to ALTER a table that has pending (deferred) FK trigger
    # events — and Django creates its FKs DEFERRABLE INITIALLY DEFERRED, so the
    # rows written above would block the RemoveField/AlterField operations that
    # follow inside this same transaction. Firing the deferred checks now clears
    # the queue and keeps the whole migration one atomic unit.
    if schema_editor is not None:
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- Organization: billing columns + the extended status kill-switch ---
        migrations.AddField(
            model_name="organization",
            name="is_personal",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="organization",
            name="stripe_customer_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="organization",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="organization",
            name="status",
            field=models.CharField(
                choices=[
                    ("trial", "Trial"),
                    ("active", "Active"),
                    ("past_due", "Past due"),
                    ("suspended", "Suspended"),
                    ("canceled", "Canceled"),
                ],
                default="trial",
                max_length=16,
            ),
        ),
        # --- Subscription: the billing anchor ---
        migrations.AddField(
            model_name="subscription",
            name="plan",
            field=models.CharField(
                choices=[
                    ("free", "Free"),
                    ("solo", "Solo"),
                    ("firm", "Firm"),
                    ("custom", "Custom"),
                ],
                default="free",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="stripe_subscription_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="stripe_price_id",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="subscription",
            name="seats",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="subscription",
            name="current_period_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="cancel_at_period_end",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="subscription",
            name="trial_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="past_due_since",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="subscription",
            name="status",
            field=models.CharField(
                choices=[
                    ("trial", "Trial"),
                    ("active", "Active"),
                    ("past_due", "Past due"),
                    ("canceled", "Canceled"),
                    ("unpaid", "Unpaid"),
                ],
                default="trial",
                max_length=16,
            ),
        ),
        # Drop the holder constraints BEFORE touching the columns they reference.
        migrations.RemoveConstraint(
            model_name="subscription",
            name="subscription_org_xor_user",
        ),
        migrations.RemoveConstraint(
            model_name="subscription",
            name="uniq_org_product_subscription",
        ),
        migrations.RemoveConstraint(
            model_name="subscription",
            name="uniq_user_product_subscription",
        ),
        # product NULL = the flagship full-corpus plan.
        migrations.AlterField(
            model_name="subscription",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                to="tenancy.product",
            ),
        ),
        # --- Data: personal orgs, comped plans, user-held subs move to their org.
        # Runs while ``user`` still exists and before ``org`` goes NOT NULL.
        migrations.RunPython(backfill_billing_orgs, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="subscription",
            name="user",
        ),
        migrations.AlterField(
            model_name="subscription",
            name="org",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscriptions",
                to="tenancy.organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                fields=("org", "product"), name="uniq_org_product_subscription"
            ),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                condition=models.Q(("product__isnull", True)),
                fields=("org",),
                name="uniq_org_flagship_subscription",
            ),
        ),
        # --- Invitations ---
        migrations.CreateModel(
            name="OrgInvitation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("member", "Member"),
                        ],
                        default="member",
                        max_length=16,
                    ),
                ),
                ("token_hash", models.CharField(db_index=True, max_length=64, unique=True)),
                (
                    "expires_at",
                    models.DateTimeField(
                        default=apps.tenancy.models.default_invitation_expiry
                    ),
                ),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_org_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invitations",
                        to="tenancy.organization",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(
                            ("accepted_at__isnull", True), ("revoked_at__isnull", True)
                        ),
                        fields=("org", "email"),
                        name="uniq_pending_invitation_per_org_email",
                    )
                ],
            },
        ),
    ]
