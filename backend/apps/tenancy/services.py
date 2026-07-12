"""The tenancy service layer — orgs, membership, and the ONE tier rule.

Billing attaches to an :class:`~apps.tenancy.models.Organization`, always: a solo
signup gets a personal org (``is_personal=True``) created at registration, and a
firm is just an org with more members. There is no user-held subscription.

``User.tier`` survives as a **derived cache**. The hot paths (``apps/api/chat.py``,
``apps/api/auth.py``, ``apps/mcp_server/gating.py``) keep reading ``user.tier`` and
are not rewritten; this module is what writes it. :func:`effective_plan` is the
single source of truth, and every mutation that could change a user's plan —
a Stripe webhook, a membership change, staff suspending an org — ends by calling
:func:`sync_user_tier` / :func:`sync_org_tiers`.

That indirection is the whole design: ``canceled``, ``unpaid``, ``suspended`` and an
expired past-due grace window all collapse to ``free`` in :func:`effective_plan`, so
every tier gate already in the codebase enforces billing state with **zero new
enforcement code**.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.audit import AuditEvent, record_event
from apps.accounts.models import Tier, User

from .models import (
    Organization,
    OrgInvitation,
    OrgMembership,
    Subscription,
    hash_invitation_token,
)

logger = logging.getLogger(__name__)

# Ordering of the plans. ``effective_plan`` takes the MAX over a user's orgs, so a
# member of a firm who also pays for a personal solo plan keeps the firm plan.
PLAN_RANK: dict[str, int] = {
    Tier.FREE: 0,
    Tier.SOLO: 1,
    Tier.FIRM: 2,
    Tier.CUSTOM: 3,
}

Role = OrgMembership.Role


class TenancyError(Exception):
    """Base for service-layer refusals the API layer maps to 4xx."""


class LastOwnerError(TenancyError):
    """Refusing to remove or demote an org's last owner."""


def _grace_days() -> int:
    # Settings-guarded so this module keeps working if the billing settings block
    # (added with apps/billing) is not present yet.
    return int(getattr(settings, "BILLING_PAST_DUE_GRACE_DAYS", 7) or 0)


# ---------------------------------------------------------------------------
# Seat sync — the one call into apps/billing, which may not exist yet.
# ---------------------------------------------------------------------------


def sync_seats(org: Organization) -> None:
    """Push ``seat_count(org)`` to Stripe as the subscription quantity.

    Indirection on purpose: ``apps.billing`` is a later phase (and is absent in a
    Stripe-less dev/CI checkout), so an ImportError here is a normal, expected
    state and must never break a membership change. When apps/billing lands, its
    ``seats.sync_seats`` is picked up with no edit here.
    """
    try:
        from apps.billing.seats import sync_seats as _sync  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("apps.billing not installed — skipping seat sync for org %s", org.pk)
        return
    try:
        _sync(org)
    except Exception:  # noqa: BLE001 — a Stripe hiccup must not lose the membership write
        logger.exception("seat sync failed for org %s", org.pk)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def billing_org(user) -> Organization | None:
    """The user's **personal** org — the one their own subscription bills through.

    Read-only: returns ``None`` if the user has none (anonymous callers, and rows
    created outside the registration path). Use :func:`ensure_personal_org` where a
    row must exist.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return (
        Organization.objects.filter(
            is_personal=True, memberships__user=user
        )
        .order_by("id")
        .first()
    )


def orgs_for(user) -> QuerySet[Organization]:
    """Every org the user belongs to (personal + any firm/bar)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return Organization.objects.none()
    return Organization.objects.filter(memberships__user=user).distinct()


def seat_count(org: Organization) -> int:
    """Seats consumed = members. One member, one seat — no per-product assignment."""
    return OrgMembership.objects.filter(org=org).count()


def members_of(org: Organization) -> QuerySet[OrgMembership]:
    return OrgMembership.objects.filter(org=org).select_related("user")


def role_of(user, org: Organization) -> str | None:
    """The user's role in ``org``, or None if they are not a member."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return (
        OrgMembership.objects.filter(org=org, user=user)
        .values_list("role", flat=True)
        .first()
    )


def flagship_subscription(org: Organization) -> Subscription | None:
    """The org's full-corpus subscription (``product IS NULL``) — the only row that
    grants a *plan*. A product-scoped site license grants that product only (see
    :mod:`apps.tenancy.entitlement`)."""
    return Subscription.objects.filter(org=org, product__isnull=True).first()


# ---------------------------------------------------------------------------
# The tier rule
# ---------------------------------------------------------------------------


def org_granted_plan(org: Organization, subscription: Subscription | None = None) -> str:
    """The plan ``org`` currently grants its members — ``free`` if it grants nothing.

    An org grants its flagship subscription's ``plan`` iff ALL of:

      * the org itself is live (not ``suspended`` / ``canceled``), AND
      * that subscription is ``trial`` / ``active``, OR it is ``past_due`` and still
        inside the grace window (``past_due_since`` newer than
        ``settings.BILLING_PAST_DUE_GRACE_DAYS`` ago).

    ``canceled`` / ``unpaid`` / suspended / expired-grace all collapse to ``free``.
    A ``past_due`` row with no ``past_due_since`` anchor grants nothing — the webhook
    stamps that column when it flips the status, and a missing anchor means we cannot
    prove we are inside the window.
    """
    if org.status in (Organization.Status.SUSPENDED, Organization.Status.CANCELED):
        return Tier.FREE

    sub = subscription if subscription is not None else flagship_subscription(org)
    if sub is None:
        return Tier.FREE

    plan = sub.plan if sub.plan in PLAN_RANK else Tier.FREE

    if sub.status in Subscription.LIVE_STATUSES:
        return plan

    if sub.status == Subscription.Status.PAST_DUE:
        if sub.past_due_since is None:
            return Tier.FREE
        deadline = sub.past_due_since + dt.timedelta(days=_grace_days())
        if timezone.now() < deadline:
            return plan

    return Tier.FREE


def effective_plan(user) -> str:
    """The user's plan = MAX over every org that grants them one. ``free`` if none."""
    if user is None or not getattr(user, "is_authenticated", False):
        return Tier.FREE

    best = Tier.FREE
    orgs = list(
        Organization.objects.filter(memberships__user=user)
        .distinct()
        .prefetch_related("subscriptions")
    )
    for org in orgs:
        # prefetched — no query per org.
        flagship = next(
            (s for s in org.subscriptions.all() if s.product_id is None), None
        )
        plan = org_granted_plan(org, flagship)
        if PLAN_RANK.get(plan, 0) > PLAN_RANK.get(best, 0):
            best = plan
    return best


def has_paid_access(user) -> bool:
    """The no-free-tier gate for the interactive surfaces (chat, verify,
    research search, API keys/MCP, the email assistant).

    Decided 2026-07-12: there is no free account — outside the 7-day Stripe
    trial, users must pay. A ``trialing`` Stripe subscription maps to our
    ``trial`` status which grants its plan, so trial users pass; an account
    that registered but never checked out stays ``free`` and is refused.

    Reads ``user.tier`` (the derived cache), NOT :func:`effective_plan` — the
    hot paths stay on the cache by design, and webhooks/membership mutations/
    ``reconcile_tiers`` keep it synced. Staff are exempt (they operate the
    product). While ``BILLING_REQUIRE_PAID`` is off (beta, dev, CI) everyone
    passes: flipping that setting IS the billing launch.
    """
    if not getattr(settings, "BILLING_REQUIRE_PAID", False):
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_staff:
        return True
    return user.tier != Tier.FREE


def sync_user_tier(user) -> bool:
    """Write :func:`effective_plan` onto ``user.tier``. Returns True if it changed.

    Compares against the DB, not the in-memory copy: callers routinely hold a
    ``User`` instance loaded before some other code path (a webhook, a sibling
    ``sync_org_tiers``) already moved the column, and a stale attribute would make
    this a silent no-op. The write is an UPDATE for the same reason — it must not
    flush any other stale field back over the row.
    """
    plan = effective_plan(user)
    current = User.objects.filter(pk=user.pk).values_list("tier", flat=True).first()
    user.tier = plan  # keep the caller's instance honest either way
    if current is None or current == plan:
        return False
    User.objects.filter(pk=user.pk).update(tier=plan)
    return True


def sync_org_tiers(org: Organization) -> None:
    """Re-derive ``tier`` for every member of ``org``.

    The one call that makes billing state actually enforce: every Stripe webhook
    handler and every membership mutation ends here.
    """
    for membership in OrgMembership.objects.filter(org=org).select_related("user"):
        sync_user_tier(membership.user)


# ---------------------------------------------------------------------------
# Org creation
# ---------------------------------------------------------------------------


def _unique_org_slug(base: str) -> str:
    """``base`` slugified, de-duplicated with a numeric suffix."""
    stem = slugify(base) or "org"
    stem = stem[:40]
    slug = stem
    n = 1
    while Organization.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{stem}-{n}"
    return slug


def personal_org_name(user) -> str:
    return f"{user.get_full_name() or user.email} (Personal)"


@transaction.atomic
def ensure_personal_org(user) -> Organization:
    """The user's personal org, creating it (+ their OWNER membership) if absent.

    Idempotent — safe to call on every registration, from the backfill migration,
    and defensively from ``/api/auth/me`` for accounts that predate the hook.
    """
    existing = billing_org(user)
    if existing is not None:
        return existing

    local_part = (user.email or "").split("@")[0]
    org = Organization.objects.create(
        slug=_unique_org_slug(local_part or f"user-{user.pk}"),
        name=personal_org_name(user),
        status=Organization.Status.ACTIVE,
        is_personal=True,
    )
    OrgMembership.objects.create(user=user, org=org, role=Role.OWNER)
    return org


# ---------------------------------------------------------------------------
# Membership mutations — mutate, re-derive tiers, sync seats, audit.
# ---------------------------------------------------------------------------


def _owner_count(org: Organization) -> int:
    return OrgMembership.objects.filter(org=org, role=Role.OWNER).count()


def _audit(event_type: str, *, actor, request, org: Organization, target, extra=None):
    detail = {"org_id": org.pk, "org_slug": org.slug}
    if target is not None:
        detail["target_user_id"] = getattr(target, "pk", None)
        detail["target_email"] = getattr(target, "email", "")
    if extra:
        detail.update(extra)
    record_event(
        event_type=event_type,
        request=request,
        actor=actor,
        outcome=AuditEvent.Outcome.SUCCESS,
        detail=detail,
    )


@transaction.atomic
def add_member(
    org: Organization,
    user,
    role: str = Role.MEMBER,
    *,
    actor=None,
    request=None,
) -> OrgMembership:
    """Add (or no-op re-add) ``user`` to ``org``. Adds a seat → changes the bill."""
    membership, created = OrgMembership.objects.get_or_create(
        org=org, user=user, defaults={"role": role}
    )
    if created:
        sync_org_tiers(org)
        sync_seats(org)
        _audit(
            AuditEvent.Event.ORG_MEMBER_ADD,
            actor=actor,
            request=request,
            org=org,
            target=user,
            extra={"role": membership.role},
        )
    return membership


@transaction.atomic
def remove_member(org: Organization, user, *, actor=None, request=None) -> None:
    """Remove ``user`` from ``org``. Refuses to remove the last owner."""
    membership = OrgMembership.objects.filter(org=org, user=user).first()
    if membership is None:
        return
    if membership.role == Role.OWNER and _owner_count(org) <= 1:
        raise LastOwnerError("an organization must always have at least one owner")

    membership.delete()
    # The removed user keeps whatever OTHER orgs grant them — sync them too.
    sync_user_tier(user)
    sync_org_tiers(org)
    sync_seats(org)
    _audit(
        AuditEvent.Event.ORG_MEMBER_REMOVE,
        actor=actor,
        request=request,
        org=org,
        target=user,
    )


@transaction.atomic
def change_role(
    org: Organization, user, role: str, *, actor=None, request=None
) -> OrgMembership:
    """Change ``user``'s role in ``org``. Refuses to demote the last owner."""
    if role not in set(Role.values):
        raise TenancyError(f"unknown role: {role!r}")

    membership = OrgMembership.objects.filter(org=org, user=user).first()
    if membership is None:
        raise TenancyError("not a member of this organization")
    if membership.role == role:
        return membership
    if membership.role == Role.OWNER and role != Role.OWNER and _owner_count(org) <= 1:
        raise LastOwnerError("an organization must always have at least one owner")

    previous = membership.role
    membership.role = role
    membership.save(update_fields=["role"])
    # Role does not change entitlement today, but keep the contract uniform: every
    # membership mutation re-derives tiers and re-syncs seats.
    sync_org_tiers(org)
    sync_seats(org)
    _audit(
        AuditEvent.Event.ORG_ROLE_CHANGE,
        actor=actor,
        request=request,
        org=org,
        target=user,
        extra={"from": previous, "to": role},
    )
    return membership


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


@transaction.atomic
def accept_invitation(user, raw_token: str) -> OrgMembership:
    """Spend an emailed invitation token: join ``user`` to the inviting org.

    Two callers, one implementation: the ``/invite/<token>`` page (POST
    ``/api/org/invitations/{token}/accept``) and the registration hook, which
    passes ``?invite=`` straight through so an invitee who signs up from the link
    lands inside the org on their very first request.

    The raw token is never stored — we look the row up by its SHA-256
    (:func:`~apps.tenancy.models.hash_invitation_token`), which is also why an
    unknown token is indistinguishable from a wrong one.

    An invitation is spendable only if it is *pending* (neither accepted nor
    revoked, not past ``expires_at``) **and** it was addressed to this user's own
    email. That last check is the security boundary: the token alone must not be
    enough — a leaked/forwarded link cannot be redeemed by whoever happens to hold
    it, only by the mailbox it was sent to.

    Idempotent: re-accepting an invitation this user already spent returns the
    existing membership rather than raising, so a double-clicked Accept button, or
    a registration that accepted the token followed by the /invite page's own
    Accept, is a no-op instead of an error.

    Raises :class:`TenancyError` with a machine-readable ``code`` attribute
    (``unknown`` / ``email_mismatch`` / ``already_accepted`` / ``revoked`` /
    ``expired``) so the API layer can map each refusal to its own status code
    without re-doing the lookup. (An attribute rather than an exception subclass
    per reason: the caller that matters, ``apps/api/orgs.py``, needs the
    distinction only to pick a number.)
    """

    def refuse(code: str, message: str) -> TenancyError:
        error = TenancyError(message)
        error.code = code
        return error

    # Locked so two concurrent redemptions of one token (a double-clicked Accept,
    # or register-with-invite racing the /invite page) serialize instead of both
    # passing the "not yet accepted" check. ``of=self``: lock the invitation row,
    # not the joined Organization — an org rename must not block on this.
    invitation = (
        OrgInvitation.objects.select_for_update(of=("self",))
        .select_related("org")
        .filter(token_hash=hash_invitation_token(raw_token))
        .first()
    )
    if invitation is None:
        raise refuse("unknown", "this invitation link is not valid")

    invited_email = (invitation.email or "").strip().lower()
    if (getattr(user, "email", "") or "").strip().lower() != invited_email:
        raise refuse(
            "email_mismatch",
            f"this invitation was sent to {invited_email}",
        )

    org = invitation.org
    existing = OrgMembership.objects.filter(org=org, user=user).first()

    if invitation.accepted_at is not None:
        if existing is not None:
            return existing  # already spent by this same user — a no-op, not an error
        raise refuse("already_accepted", "this invitation has already been used")
    if invitation.revoked_at is not None:
        raise refuse("revoked", "this invitation has been revoked")
    if invitation.expires_at <= timezone.now():
        raise refuse("expired", "this invitation has expired")

    # add_member is what syncs tiers + seats and writes the ORG_MEMBER_ADD row;
    # a user already in the org (invited to one they had joined another way) keeps
    # the role they have rather than being silently re-graded by an invite.
    membership = add_member(org, user, invitation.role, actor=user)
    # add_member re-derives tiers via sync_org_tiers, which loads its OWN User
    # instances — so the caller's ``user`` object still holds the pre-join tier.
    # The registration hook serializes that very instance into its response, so a
    # user who signs up from an invite link would be told they are ``free`` while
    # the DB (correctly) says otherwise. Cheap: the row already matches, so this
    # only refreshes the in-memory attribute.
    sync_user_tier(user)

    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    _audit(
        AuditEvent.Event.ORG_INVITE_ACCEPT,
        actor=user,
        request=None,
        org=org,
        target=user,
        extra={"invitation_id": invitation.pk, "role": invitation.role},
    )
    return membership


__all__ = [
    "PLAN_RANK",
    "LastOwnerError",
    "Role",
    "TenancyError",
    "accept_invitation",
    "add_member",
    "billing_org",
    "change_role",
    "effective_plan",
    "ensure_personal_org",
    "flagship_subscription",
    "has_paid_access",
    "members_of",
    "org_granted_plan",
    "orgs_for",
    "remove_member",
    "role_of",
    "seat_count",
    "sync_org_tiers",
    "sync_seats",
    "sync_user_tier",
]
