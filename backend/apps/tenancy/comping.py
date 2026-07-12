"""Staff comping — granting a paid plan by hand, in the billing model.

Comping used to be a one-column edit: staff set ``User.tier`` in ``/admin/users``
and every gate believed it. Billing inverted that. ``User.tier`` is now a
**derived cache** of :func:`apps.tenancy.services.effective_plan`, so a hand-set
tier grants nothing (``entitlement`` reads the plan, not the column) and the
``reconcile_tiers`` cron reverts it on its next run.

So comping has to write the thing the tier is derived FROM: a **comped
Subscription** on the user's personal org — flagship (``product IS NULL``),
``status=active``, ``seats=1``, and no Stripe ids. That is exactly the row shape
``tenancy/0002_billing.backfill_billing_orgs`` created for every pre-existing paid
user, which is what makes a comp indistinguishable from a real plan to everything
downstream: :func:`~apps.tenancy.services.sync_user_tier` derives the tier from it
and the chat quota, the REST gate, the MCP gate and ``entitlement`` all enforce it
with no further code.

Un-comping (``plan="free"``) deletes that row again, restoring the "no flagship
subscription" shape a never-paid account has.

**A Stripe-backed subscription is Stripe's, not ours.** A row carrying a
``stripe_subscription_id`` is changed in Stripe (or the customer portal), never by
hand: an edit here would be silently reverted by the next
``customer.subscription.updated`` webhook, and in the window before that the
customer would be getting a plan their invoice does not match.
:func:`set_comped_plan` refuses those rows with :class:`CompingRefused`, which the
admin API turns into a 409.

The AuditEvent is deliberately written by the *caller* (``apps.api.admin_users``),
not here, so that a PATCH changing the plan and the budget together stays one
``admin_user_change`` row with both fields in ``detail.changes``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction

from apps.accounts.models import Tier

from . import services
from .models import Organization, Subscription
from .services import PLAN_RANK, TenancyError

logger = logging.getLogger(__name__)


class CompingRefused(TenancyError):
    """The comp cannot be applied to this account (→ HTTP 409).

    Two cases: the plan is Stripe-managed, or the user's org is suspended/canceled
    (an org in either state grants no plan at all, so writing a comp there would be
    a silent no-op — the exact failure mode this module exists to end).
    """


# `source` values on PlanState — where the user's personal-org plan comes from.
SOURCE_COMPED = "comped"  # staff-granted; free to edit here
SOURCE_STRIPE = "stripe"  # a real paying customer; edit it in Stripe
SOURCE_NONE = "none"  # no flagship subscription on the personal org


@dataclass(frozen=True)
class OrgGrant:
    """A plan granted to the user by some org OTHER than their personal one."""

    org_id: int
    org_name: str
    plan: str


@dataclass(frozen=True)
class PlanState:
    """What staff need to see before touching a plan.

    ``comped_plan`` is the plan on the personal org's flagship subscription — the
    only thing comping writes — and is NOT the same as ``user.tier``: the tier is
    the MAX across every org the user belongs to, so a firm member can be ``firm``
    with no comp at all. ``other_grants`` is what explains that gap, and is why
    un-comping does not always drop someone to free.
    """

    comped_plan: str = Tier.FREE
    source: str = SOURCE_NONE
    status: str = "none"
    editable: bool = True
    org_id: int | None = None
    org_name: str = ""
    org_status: str = ""
    other_grants: list[OrgGrant] = field(default_factory=list)


def plan_state(user) -> PlanState:
    """The comped-vs-paid picture for ``user``'s personal org (read-only)."""
    org = services.billing_org(user)
    if org is None:
        # No personal org yet (an account predating the registration hook). The
        # first comp creates one — see ensure_personal_org in set_comped_plan.
        return PlanState(other_grants=_other_grants(user, None))

    sub = services.flagship_subscription(org)
    if sub is None:
        source, plan, status = SOURCE_NONE, Tier.FREE, "none"
    elif sub.stripe_subscription_id:
        source, plan, status = SOURCE_STRIPE, sub.plan, sub.status
    else:
        source, plan, status = SOURCE_COMPED, sub.plan, sub.status

    return PlanState(
        comped_plan=plan,
        source=source,
        status=status,
        editable=source != SOURCE_STRIPE,
        org_id=org.pk,
        org_name=org.name,
        org_status=org.status,
        other_grants=_other_grants(user, org),
    )


def _other_grants(user, personal: Organization | None) -> list[OrgGrant]:
    """Every OTHER org currently granting this user a plan (a firm seat, a bar)."""
    grants: list[OrgGrant] = []
    orgs = services.orgs_for(user).prefetch_related("subscriptions")
    for org in orgs:
        if personal is not None and org.pk == personal.pk:
            continue
        flagship = next(
            (s for s in org.subscriptions.all() if s.product_id is None), None
        )
        granted = services.org_granted_plan(org, flagship)
        if granted != Tier.FREE:
            grants.append(OrgGrant(org_id=org.pk, org_name=org.name, plan=granted))
    return grants


@transaction.atomic
def set_comped_plan(user, plan: str, *, actor=None) -> Subscription | None:
    """Comp ``user`` onto ``plan`` (``"free"`` un-comps them). Returns the row.

    Upserts the flagship subscription on the user's personal org and re-derives the
    tier of everyone in that org. ``actor`` is the staff member, for the log line —
    the AuditEvent belongs to the caller (see the module docstring).

    Raises :class:`CompingRefused` (→ 409) if the plan is Stripe-managed or the org
    is suspended/canceled, and ``ValueError`` on an unknown plan.
    """
    if plan not in PLAN_RANK:
        raise ValueError(f"unknown plan {plan!r}")

    # Idempotent, and it covers accounts created before the registration hook (and
    # in tests / the shell) that have no personal org yet.
    org = services.ensure_personal_org(user)

    sub = (
        Subscription.objects.select_for_update()
        .filter(org=org, product__isnull=True)
        .first()
    )

    if sub is not None and sub.stripe_subscription_id:
        raise CompingRefused(
            "this account pays through Stripe — change or cancel the plan in "
            "Stripe (or send them to the customer portal), not here"
        )
    if org.status in (Organization.Status.SUSPENDED, Organization.Status.CANCELED):
        raise CompingRefused(
            f"{org.name} is {org.get_status_display().lower()} — a suspended or "
            "canceled organization grants no plan, so this comp would do nothing. "
            "Restore the organization first."
        )

    if plan == Tier.FREE:
        # Un-comp: back to the shape of a never-paid account — no flagship row.
        if sub is not None:
            sub.delete()
            sub = None
    elif sub is None:
        sub = Subscription.objects.create(
            org=org,
            product=None,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            seats=1,
        )
    else:
        sub.plan = plan
        sub.status = Subscription.Status.ACTIVE
        # A comped row carries no billing state — clear anything a previous life
        # (e.g. a lapsed Stripe plan since detached) left behind.
        sub.past_due_since = None
        sub.cancel_at_period_end = False
        sub.save(
            update_fields=[
                "plan",
                "status",
                "past_due_since",
                "cancel_at_period_end",
                "updated_at",
            ]
        )

    # The one call that makes it bite. sync_user_tier again afterwards so the
    # CALLER's in-memory ``user`` (a different instance from the one sync_org_tiers
    # loaded) also carries the new tier.
    services.sync_org_tiers(org)
    services.sync_user_tier(user)

    logger.info(
        "comp: %s set %s to plan=%s (org=%s) → tier=%s",
        getattr(actor, "email", "system"),
        getattr(user, "email", user.pk),
        plan,
        org.slug,
        user.tier,
    )
    return sub


__all__ = [
    "SOURCE_COMPED",
    "SOURCE_NONE",
    "SOURCE_STRIPE",
    "CompingRefused",
    "OrgGrant",
    "PlanState",
    "plan_state",
    "set_comped_plan",
]
