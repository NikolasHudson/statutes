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
    regulator / firm — and, since billing moved onto orgs, ALSO the one-person
    "personal" org auto-created for every solo signup (``is_personal=True``).
    Members inherit the org's subscriptions. Invisible in the URL; carries only
    optional co-brand for a later "Provided by <bar>" ribbon.
  * :class:`Subscription` — a license held by **an org, always** (billing anchors
    on the org; there is no user-held subscription). ``product IS NULL`` is the
    flagship full-corpus plan; a non-null product is a scoped site license.
    Carries the Stripe anchor (customer/subscription/price ids, seats, period).
  * :class:`OrgMembership` — which users belong to which org (many-to-many — a
    lawyer may belong to several bars; entitlement is a union, so that's fine).
    ``role`` is load-bearing: owner/admin may manage billing + members.
  * :class:`OrgInvitation` — a pending email invite into an org. Only the SHA-256
    of the token is stored; the raw token is emailed and never persisted.

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

import datetime as dt
import hashlib
import secrets

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Plans mirror ``accounts.models.Tier`` exactly — a Subscription's ``plan`` is
# what ``User.tier`` is derived FROM (see apps.tenancy.services.sync_user_tier),
# so the two vocabularies must not drift.
from apps.accounts.models import Tier


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

    def _normalize_hostname(self) -> None:
        # Hosts are matched case-insensitively: ProductResolutionMiddleware
        # lowercases request.get_host(), so a row stored as "Clerk.Example.com"
        # would match nothing — and a host that matches nothing resolves to the
        # UNLOCKED flagship, making the typo a silent scope-lock bypass rather
        # than a visible 404. Normalize so the two sides cannot drift.
        # Empty stays NULL: the unique index must allow many host-less products.
        self.hostname = (self.hostname or "").strip().lower() or None

    def clean_fields(self, exclude=None):
        # Normalize BEFORE validation, not only in save(): hostname is unique, and
        # a ModelForm (the admin) runs validate_unique() against the raw value. Given
        # an existing "clerk.example.com", the input "Clerk.Example.com" would find no
        # clash, validate, and only then be lowercased by save() — surfacing as an
        # unhandled IntegrityError 500 instead of a "already exists" field error.
        self._normalize_hostname()
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self._normalize_hostname()
        super().save(*args, **kwargs)

    @property
    def is_scoped(self) -> bool:
        return bool(self.allowed_source_slugs)


class Organization(models.Model):
    """A distribution + billing vehicle: a bar association, regulator, firm — or
    the personal one-person org auto-created for a solo signup.

    Members inherit the org's subscriptions. Per-tenant data is limited to this
    row, its memberships, its subscriptions, and members' own chat threads
    (already per-user) — never any walled-off copy of the corpus. Not in the URL.

    ``status`` is the org-level kill-switch: ``suspended`` / ``canceled`` stop the
    org granting ANY plan (see :func:`apps.tenancy.services.effective_plan`), which
    is what makes staff suspension and a lapsed account actually bite — every
    existing tier gate then sees ``free``.
    """

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        SUSPENDED = "suspended", "Suspended"
        CANCELED = "canceled", "Canceled"

    # Org statuses that still allow the org to grant its subscription's plan.
    # (Whether the SUBSCRIPTION grants is a separate check — see services.)
    LIVE_STATUSES = frozenset({Status.TRIAL, Status.ACTIVE, Status.PAST_DUE})

    slug = models.SlugField(unique=True)  # "iowa-bar"
    name = models.CharField(max_length=200)  # "Iowa State Bar Association"
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.TRIAL
    )

    # True for the org auto-created at registration for a single user. Exactly
    # one per user; it is that user's *billing org* (services.billing_org).
    is_personal = models.BooleanField(default=False)

    # Stripe customer this org bills through. Null until the org first checks out.
    stripe_customer_id = models.CharField(
        max_length=64, null=True, blank=True, unique=True
    )

    # Optional co-brand for the post-login "Provided by <bar>" ribbon (deferred
    # nicety — the login screen shows the *product's* brand, not the org's).
    brand_name = models.CharField(max_length=120, blank=True)
    logo_url = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Subscription(models.Model):
    """A license held by an **org** — always. Billing anchors here.

    Two flavours, distinguished by ``product``:

      * ``product IS NULL`` → **the flagship full-corpus plan**. This is the row
        Stripe drives and the only row :func:`apps.tenancy.services.effective_plan`
        reads, so a personal org's ``solo`` plan and a firm's ``firm`` plan are the
        same shape.
      * ``product`` set → a scoped site license (e.g. a bar association licensing
        the Ethics app for its members). Grants that product via
        :mod:`apps.tenancy.entitlement`; it does not grant a full-corpus plan.

    There is no user-held subscription: a solo buyer holds theirs through the
    personal org created at registration.
    """

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        UNPAID = "unpaid", "Unpaid"

    # Subscription statuses that grant outright. ``past_due`` grants only inside
    # the grace window (services.effective_plan); everything else grants nothing.
    LIVE_STATUSES = frozenset({Status.TRIAL, Status.ACTIVE})

    # NULL = the flagship full-corpus plan (see class docstring).
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )

    # Which plan this subscription grants its org's members. Mirrors User.Tier —
    # User.tier is a derived cache of the max plan across a user's orgs.
    plan = models.CharField(max_length=16, choices=Tier.choices, default=Tier.FREE)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.TRIAL
    )

    # --- Stripe anchor. All null/blank for a comped or manually-granted row. ---
    stripe_subscription_id = models.CharField(
        max_length=64, null=True, blank=True, unique=True
    )
    stripe_price_id = models.CharField(max_length=64, blank=True)
    # The Stripe quantity. Kept in step with seat_count(org) by billing.seats.
    seats = models.PositiveIntegerField(default=1)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    trial_end = models.DateTimeField(null=True, blank=True)
    # When the subscription first went past_due — the grace-window anchor. Cleared
    # on invoice.paid. Null while not past_due.
    past_due_since = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One subscription per (org, product).
            models.UniqueConstraint(
                fields=("org", "product"),
                name="uniq_org_product_subscription",
            ),
            # …and, because Postgres treats NULLs as distinct, the (org, product)
            # unique above does NOT stop two flagship rows for one org. This does:
            # exactly one flagship (product IS NULL) subscription per org, which is
            # what effective_plan assumes when it reads "the" flagship row.
            models.UniqueConstraint(
                fields=("org",),
                condition=Q(product__isnull=True),
                name="uniq_org_flagship_subscription",
            ),
        ]

    def __str__(self) -> str:
        what = self.product.slug if self.product_id else f"plan:{self.plan}"
        return f"{self.org.slug} → {what} ({self.status})"

    @property
    def is_flagship(self) -> bool:
        return self.product_id is None


class OrgMembership(models.Model):
    """Which users belong to which org, and their role.

    Membership in an org with a live subscription IS the entitlement — there is no
    per-product seat assignment; a member = a Stripe seat (billing.seats keeps the
    quantity in step). A user may belong to several orgs; entitlement is a union
    across them and the plan is the max (services.effective_plan).

    ``role`` is load-bearing: owner/admin may manage members + billing. Invariant:
    **an org always has ≥1 owner** — enforced in :mod:`apps.tenancy.services`, not
    in the DB (a check constraint cannot span rows).
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


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

INVITATION_TTL_DAYS = 14


def default_invitation_expiry():
    """Module-level (not a lambda) so migrations can serialize the default."""
    return timezone.now() + dt.timedelta(days=INVITATION_TTL_DAYS)


def hash_invitation_token(raw_token: str) -> str:
    """SHA-256 hex of a raw invitation token — what we store and look up by."""
    return hashlib.sha256((raw_token or "").encode()).hexdigest()


def generate_invitation_token() -> tuple[str, str]:
    """(raw_token, token_hash). The raw token goes in the emailed link exactly
    once and is never persisted — same posture as :func:`accounts.generate_key`."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_invitation_token(raw)


class OrgInvitation(models.Model):
    """A pending email invite into an org.

    The raw token is emailed as ``${APP_URL}/invite/<raw-token>`` and never
    stored; the row keeps only its SHA-256, so a DB leak cannot be replayed into
    org access. An invitation is *pending* while it has neither been accepted nor
    revoked and has not expired — one pending invite per (org, email), enforced by
    a partial unique index.
    """

    org = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    # Lowercased on save; matched against the accepting user's login email.
    email = models.EmailField()
    role = models.CharField(
        max_length=16,
        choices=OrgMembership.Role.choices,
        default=OrgMembership.Role.MEMBER,
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_org_invitations",
    )
    expires_at = models.DateTimeField(default=default_invitation_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("org", "email"),
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="uniq_pending_invitation_per_org_email",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.email} → {self.org.slug} ({self.role})"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_pending(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )
