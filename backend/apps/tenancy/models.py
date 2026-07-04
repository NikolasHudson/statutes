"""Multi-tenant packaging layer — products, organizations, subscriptions, members.

The corpus itself stays one shared, read-only public asset (see ``apps.corpus``).
"Multi-tenancy" here is **not** data isolation — every tenant queries the same
public law. It is a packaging layer that answers two questions: *which scoped app
is this?* (by host) and *is this user allowed into it?* (by entitlement).

  * :class:`Product` — a scoped "app" definition AND its own brand. Carries the
    ``hostname`` of its locked front door (e.g. ``clerk.<domain>`` = the Ethics
    app), the corpus sources it may search, the system-prompt variant, and the
    jurisdiction it is locked to. A host that matches no product's ``hostname``
    (the flagship ``app.<domain>`` / the apex) is the *unlocked* experience.
  * :class:`Organization` — a distribution + billing vehicle: a bar association /
    regulator / firm. Members inherit the org's subscriptions. Invisible in the
    URL; carries only optional co-brand for a later "Provided by <bar>" ribbon.
  * :class:`Subscription` — an active license of a product, attached to **a user
    OR an org** (individual purchase OR bar-wide license). Status only for now;
    seats + billing are deferred to a later phase.
  * :class:`OrgMembership` — which users belong to which org (many-to-many — a
    lawyer may belong to several bars; entitlement is a union, so that's fine).

Access is decided by **entitlement** (see :mod:`apps.tenancy.entitlement`), not by
the URL: a user gets a product if they bought it directly, belong to an org that
licensed it, or hold the full corpus (superset). The host only chooses *which*
front door; entitlement chooses *who gets in*. Tenant/product resolution is by
HOST and runs pre-auth (see :class:`core.middleware.ProductResolutionMiddleware`)
so ``GET /api/branding`` can theme the login screen before anyone authenticates.

The single load-bearing security change that makes a *sold, scoped* product safe
is the server-side scope lock: the chat endpoint clamps the client's requested
``source_slug`` to :attr:`Product.allowed_source_slugs`. Everything downstream
already keys off ``source_slug`` (retrieval, system prompt, verification).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q


class Product(models.Model):
    """A scoped "app" definition — CONFIG, not a tenant — plus its own brand.

    Separate from :class:`Organization` so many orgs can license the same product
    with their own co-brand. The scope lock and the host front door live here.
    """

    slug = models.SlugField(unique=True)  # "iowa-ethics-procedure"
    name = models.CharField(max_length=200)  # "Iowa Ethics & Procedure"

    # The locked front door. A request whose Host matches this resolves to this
    # product (scope-locked). NULL = not host-pinned (the flagship/unlocked app,
    # which has no single product). Stored NULL when unset so the unique
    # constraint allows many products without a dedicated host.
    hostname = models.CharField(max_length=255, unique=True, null=True, blank=True)

    # The scope lock: the corpus source slugs this product may search. An EMPTY
    # list means "full corpus" (the flagship / firm product). The chat endpoint
    # clamps the client's requested source_slug to this set.
    allowed_source_slugs = ArrayField(
        models.SlugField(max_length=100), default=list, blank=True
    )

    # Which system-prompt variant to load (tone / scope framing / citation
    # rules). Blank = the default flagship prompt.
    system_prompt_key = models.CharField(max_length=64, blank=True)

    # Lock the product to one jurisdiction — the multi-state insurance. When set,
    # the system prompt + citation formatting are parameterized by this instead
    # of literal "Iowa" text, so a second state is data, not code.
    jurisdiction = models.ForeignKey(
        "corpus.Jurisdiction",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="products",
    )

    # --- the app's own white-label brand (served pre-login by /api/branding) ---
    brand_name = models.CharField(max_length=120, blank=True)
    logo_url = models.CharField(max_length=500, blank=True)
    primary_color = models.CharField(
        max_length=9, blank=True, help_text="Hex e.g. #0b3d2e. Blank = flagship default."
    )
    accent_color = models.CharField(max_length=9, blank=True)
    login_tagline = models.CharField(max_length=200, blank=True)
    support_email = models.EmailField(blank=True)
    disclaimer = models.TextField(
        blank=True, help_text="'Not legal advice' copy shown in-app."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.hostname:
            self.hostname = None
        super().save(*args, **kwargs)

    @property
    def is_scoped(self) -> bool:
        return bool(self.allowed_source_slugs)


class Organization(models.Model):
    """A distribution + billing vehicle: a bar association, regulator, or firm.

    Members inherit the org's subscriptions. Per-tenant data is limited to this
    row, its memberships, its subscriptions, and members' own chat threads
    (already per-user) — never any walled-off copy of the corpus. Not in the URL.
    """

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    slug = models.SlugField(unique=True)  # "iowa-bar"
    name = models.CharField(max_length=200)  # "Iowa State Bar Association"
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.TRIAL
    )

    # Optional co-brand for the post-login "Provided by <bar>" ribbon (deferred
    # nicety — the login screen shows the *product's* brand, not the org's).
    brand_name = models.CharField(max_length=120, blank=True)
    logo_url = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Subscription(models.Model):
    """An active license of a product, held by **a user XOR an org**.

    user-held  → an individual who bought the product directly.
    org-held   → a bar/firm site license; every member inherits it.
    """

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="subscriptions"
    )
    org = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.TRIAL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Exactly one holder: an org license XOR an individual license.
            models.CheckConstraint(
                check=(
                    Q(org__isnull=False, user__isnull=True)
                    | Q(org__isnull=True, user__isnull=False)
                ),
                name="subscription_org_xor_user",
            ),
            # One subscription per (holder, product), enforced per holder type
            # since the other column is NULL.
            models.UniqueConstraint(
                fields=("org", "product"),
                condition=Q(org__isnull=False),
                name="uniq_org_product_subscription",
            ),
            models.UniqueConstraint(
                fields=("user", "product"),
                condition=Q(user__isnull=False),
                name="uniq_user_product_subscription",
            ),
        ]

    def __str__(self) -> str:
        holder = self.org.slug if self.org_id else f"user:{self.user_id}"
        return f"{holder} → {self.product.slug} ({self.status})"


class OrgMembership(models.Model):
    """Which users belong to which org, and their role.

    For v1, membership in an org with an active subscription IS the entitlement
    — no per-product seat assignment yet (that arrives with per-seat firm sales).
    A user may belong to several orgs; entitlement is a union across them.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_memberships",
    )
    org = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(
        max_length=16, choices=Role.choices, default=Role.MEMBER
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "org"), name="uniq_membership_per_user_org"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.org.slug} ({self.role})"
