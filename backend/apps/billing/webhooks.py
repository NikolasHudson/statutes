"""Stripe webhook handlers — the source of truth for ``Subscription`` state.

Nothing else writes billing state. Checkout hands the browser to Stripe and
returns; the *webhook* is what tells us a customer actually paid. So this module
owns three invariants, and every one of them has teeth:

1. **Idempotency.** At-least-once delivery means every event may arrive twice.
   Each is claimed in the :class:`~apps.billing.models.StripeEvent` ledger under
   a row lock; a redelivery of a processed event returns immediately.

2. **The past-due anchor.** ``Subscription.past_due_since`` is the grace-window
   anchor, and :func:`apps.tenancy.services.org_granted_plan` grants **nothing**
   for a ``past_due`` row whose anchor is NULL — it cannot prove the customer is
   inside the window. So a handler that sets ``status=past_due`` MUST stamp
   ``past_due_since`` in the same write, or a paying customer whose card merely
   bounced is downgraded to ``free`` on the spot. Symmetrically, ``invoice.paid``
   clears the anchor **and** lifts ``past_due`` back to ``active``: clearing the
   anchor while leaving the status at ``past_due`` is the same instant-downgrade
   bug wearing a different hat, and we cannot rely on Stripe's
   ``customer.subscription.updated`` landing first — it is a separate event with
   no ordering guarantee.

3. **Every handler ends with** :func:`apps.tenancy.services.sync_org_tiers`.
   ``User.tier`` is a *cache* of the subscription state, and it is what the chat,
   REST and MCP gates actually read. Writing the Subscription row without that
   call changes nothing for the user — it is the line that makes billing enforce.

Org resolution walks three fallbacks, because only some events carry metadata:
``metadata.org_id`` (we stamp it on the Checkout session AND, via
``subscription_data``, on the subscription itself) → the ``Subscription`` row
matching the event's subscription id → ``Organization.stripe_customer_id``.
Invoices in particular carry none of our metadata, so the customer fallback is
load-bearing, not belt-and-braces.

``Organization.status`` is deliberately **never** written here. It is the staff
kill-switch; a renewal webhook must not be able to un-suspend an org that staff
suspended. Billing state lives on the Subscription; the org row is ours.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Callable, Mapping

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Tier
from apps.tenancy import services as tenancy
from apps.tenancy.models import Organization, Subscription

from . import plans, stripe_api
from .models import StripeEvent
from .stripe_api import BillingNotConfigured

logger = logging.getLogger(__name__)


# Stripe subscription status → our Subscription.Status.
#
# The four that grant nothing (``incomplete``, ``incomplete_expired``, ``unpaid``,
# ``paused``) collapse onto canceled/unpaid, which effective_plan already reads as
# ``free`` — no new enforcement code. An UNKNOWN status (Stripe adds one) leaves
# the existing status untouched and logs loudly: guessing would either strand a
# paying customer or hand access to a lapsed one, and neither is a guess worth
# making silently.
STRIPE_STATUS_MAP: dict[str, str] = {
    "trialing": Subscription.Status.TRIAL,
    "active": Subscription.Status.ACTIVE,
    "past_due": Subscription.Status.PAST_DUE,
    "canceled": Subscription.Status.CANCELED,
    "unpaid": Subscription.Status.UNPAID,
    "incomplete": Subscription.Status.UNPAID,
    "incomplete_expired": Subscription.Status.CANCELED,
    "paused": Subscription.Status.UNPAID,
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _ts(value: Any) -> dt.datetime | None:
    """Stripe unix timestamp → aware datetime. None/0/garbage → None."""
    if not value:
        return None
    try:
        return dt.datetime.fromtimestamp(int(value), tz=dt.timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _id_of(value: Any) -> str:
    """Stripe fields are either an id string or an expanded object. Take the id."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return str(value.get("id") or "")
    return str(getattr(value, "id", "") or "")


def _metadata(obj: Mapping[str, Any]) -> Mapping[str, Any]:
    md = obj.get("metadata")
    return md if isinstance(md, Mapping) else {}


def _subscription_id_from_invoice(invoice: Mapping[str, Any]) -> str:
    """The subscription an invoice belongs to.

    Stripe moved this: pre-2025 API versions put ``subscription`` on the invoice;
    current ones nest it under ``parent.subscription_details.subscription`` (and
    on the line items). Read every location so the handler survives whichever API
    version the account is pinned to — and an account upgrading mid-flight.
    """
    direct = _id_of(invoice.get("subscription"))
    if direct:
        return direct
    parent = invoice.get("parent") or {}
    if isinstance(parent, Mapping):
        details = parent.get("subscription_details") or {}
        if isinstance(details, Mapping):
            nested = _id_of(details.get("subscription"))
            if nested:
                return nested
    lines = (invoice.get("lines") or {}).get("data") or []
    for line in lines:
        if not isinstance(line, Mapping):
            continue
        line_parent = line.get("parent") or {}
        if isinstance(line_parent, Mapping):
            details = line_parent.get("subscription_item_details") or {}
            if isinstance(details, Mapping):
                found = _id_of(details.get("subscription"))
                if found:
                    return found
    return ""


def _period_end(sub_obj: Mapping[str, Any]) -> dt.datetime | None:
    """The current period end.

    Also moved by Stripe: it used to live on the subscription; on current API
    versions it lives on each subscription *item*. Prefer the top-level field,
    fall back to the latest item period end.
    """
    top = _ts(sub_obj.get("current_period_end"))
    if top:
        return top
    ends = [
        _ts(item.get("current_period_end"))
        for item in (sub_obj.get("items") or {}).get("data") or []
        if isinstance(item, Mapping)
    ]
    ends = [e for e in ends if e]
    return max(ends) if ends else None


# ---------------------------------------------------------------------------
# Org resolution
# ---------------------------------------------------------------------------


def resolve_org(obj: Mapping[str, Any]) -> Organization | None:
    """The org an event's object belongs to. See the module docstring's three
    fallbacks. None means we cannot attribute the event — logged as an error,
    because a Stripe object we cannot map to an org is money we cannot honour."""
    # 1. metadata.org_id — stamped by us on the Checkout session and, via
    #    subscription_data.metadata, on the subscription itself.
    org_id = _metadata(obj).get("org_id") or obj.get("client_reference_id")
    if org_id:
        try:
            org = Organization.objects.filter(pk=int(org_id)).first()
        except (TypeError, ValueError):
            org = None
        if org is not None:
            return org
        logger.warning("stripe event carried unknown org_id=%r", org_id)

    # 2. The subscription id we already stored (invoices carry no metadata of
    #    ours, but they do name their subscription).
    sub_id = _id_of(obj.get("id")) if obj.get("object") == "subscription" else ""
    sub_id = sub_id or _id_of(obj.get("subscription")) or _subscription_id_from_invoice(obj)
    if sub_id:
        row = (
            Subscription.objects.filter(stripe_subscription_id=sub_id)
            .select_related("org")
            .first()
        )
        if row is not None:
            return row.org

    # 3. The customer.
    customer_id = _id_of(obj.get("customer"))
    if customer_id:
        org = Organization.objects.filter(stripe_customer_id=customer_id).first()
        if org is not None:
            return org

    return None


def _flagship(org: Organization) -> Subscription:
    """The org's flagship (``product IS NULL``) subscription row, created if absent.

    This is the row ``effective_plan`` reads, and the only row Stripe drives. A
    checkout for an org that has never had a subscription lands here.
    """
    sub = tenancy.flagship_subscription(org)
    if sub is None:
        sub = Subscription.objects.create(
            org=org,
            product=None,
            plan=Tier.FREE,
            status=Subscription.Status.TRIAL,
            seats=max(1, tenancy.seat_count(org)),
        )
    return sub


# ---------------------------------------------------------------------------
# The write that matters
# ---------------------------------------------------------------------------


def apply_subscription(org: Organization, sub_obj: Mapping[str, Any]) -> Subscription:
    """Fold a Stripe subscription object into the org's flagship Subscription row.

    Shared by ``checkout.session.completed`` and ``customer.subscription.*`` so a
    subscription lands identically whichever event wins the race.
    """
    sub = _flagship(org)
    items = (sub_obj.get("items") or {}).get("data") or []

    # Plan: the line items are authoritative. If none of the prices is one we
    # know (a legacy price, a subscription created by hand in the dashboard), fall
    # back to the plan we stamped in metadata at checkout, and only then to what
    # the row already says. Never silently downgrade to free on an unknown price.
    plan = plans.plan_from_items(items)
    if plan is None:
        meta_plan = _metadata(sub_obj).get("plan")
        if meta_plan in tenancy.PLAN_RANK:
            plan = meta_plan
        else:
            price_ids = [
                (item.get("price") or {}).get("id") for item in items if isinstance(item, Mapping)
            ]
            logger.error(
                "stripe subscription %s for org %s has no recognised price (%r) and no "
                "metadata.plan — keeping plan=%s. Is STRIPE_PRICE_* set for this price?",
                sub_obj.get("id"),
                org.pk,
                price_ids,
                sub.plan,
            )
            plan = sub.plan

    stripe_status = str(sub_obj.get("status") or "")
    status = STRIPE_STATUS_MAP.get(stripe_status)
    if status is None:
        logger.error(
            "unknown Stripe subscription status %r on %s (org %s) — leaving status=%s",
            stripe_status,
            sub_obj.get("id"),
            org.pk,
            sub.status,
        )
        status = sub.status

    sub.plan = plan
    sub.status = status
    sub.stripe_subscription_id = _id_of(sub_obj.get("id")) or sub.stripe_subscription_id
    sub.stripe_price_id = plans.price_id_from_items(items) or sub.stripe_price_id
    sub.seats = plans.seats_from_items(items, default=sub.seats or 1)
    sub.current_period_end = _period_end(sub_obj) or sub.current_period_end
    sub.cancel_at_period_end = bool(sub_obj.get("cancel_at_period_end"))
    sub.trial_end = _ts(sub_obj.get("trial_end"))

    # THE landmine (see module docstring): past_due without an anchor grants
    # nothing. Stamp on entry, clear on exit.
    if status == Subscription.Status.PAST_DUE:
        if sub.past_due_since is None:
            sub.past_due_since = timezone.now()
    else:
        sub.past_due_since = None

    sub.save()
    return sub


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_checkout_completed(org: Organization, obj: Mapping[str, Any]) -> None:
    """``checkout.session.completed`` — the customer paid. Attach the subscription.

    Prefers to re-read the subscription from Stripe so plan/status/seats/period all
    come from the authoritative object rather than being inferred from a Checkout
    session. If that read fails (or Stripe is unconfigured, as in tests that only
    replay the session), fall back to the metadata we stamped at checkout so the
    customer is not left on ``free`` waiting for ``customer.subscription.created``.
    """
    customer_id = _id_of(obj.get("customer"))
    if customer_id and org.stripe_customer_id != customer_id:
        Organization.objects.filter(pk=org.pk).update(stripe_customer_id=customer_id)
        org.stripe_customer_id = customer_id

    sub_id = _id_of(obj.get("subscription"))
    if not sub_id:
        # A one-off (mode=payment) session, or a session that produced no
        # subscription. Nothing for us to attach.
        logger.info("checkout.session.completed with no subscription for org %s", org.pk)
        return

    sub_obj: Mapping[str, Any] | None = None
    if stripe_api.is_configured():
        try:
            client = stripe_api.get_stripe()
            sub_obj = client.Subscription.retrieve(sub_id)
        except BillingNotConfigured:
            sub_obj = None
        except Exception:  # noqa: BLE001 — a Stripe read must not lose the payment
            logger.exception(
                "could not retrieve stripe subscription %s after checkout (org %s) — "
                "falling back to checkout metadata",
                sub_id,
                org.pk,
            )
            sub_obj = None

    if sub_obj is not None:
        apply_subscription(org, sub_obj)
        return

    # Fallback: trust what we stamped on the session at checkout time.
    sub = _flagship(org)
    meta_plan = _metadata(obj).get("plan")
    sub.stripe_subscription_id = sub_id
    if meta_plan in tenancy.PLAN_RANK:
        sub.plan = meta_plan
    sub.status = Subscription.Status.ACTIVE
    sub.past_due_since = None
    sub.seats = max(1, tenancy.seat_count(org), sub.seats or 1)
    sub.save()


def handle_subscription_upsert(org: Organization, obj: Mapping[str, Any]) -> None:
    """``customer.subscription.created`` / ``.updated`` — the whole state, restated."""
    apply_subscription(org, obj)


def handle_subscription_deleted(org: Organization, obj: Mapping[str, Any]) -> None:
    """``customer.subscription.deleted`` — the subscription is gone. Plan → nothing.

    ``canceled`` collapses to ``free`` in ``effective_plan``, so this is the whole
    downgrade. The ``plan`` column is left as-bought: it is a record of what they
    had, and the status is what governs.
    """
    sub = _flagship(org)
    sub.status = Subscription.Status.CANCELED
    sub.cancel_at_period_end = False
    sub.past_due_since = None
    sub.save(
        update_fields=["status", "cancel_at_period_end", "past_due_since", "updated_at"]
    )


def handle_payment_failed(org: Organization, obj: Mapping[str, Any]) -> None:
    """``invoice.payment_failed`` — dunning starts. Stamp the grace anchor.

    Without ``past_due_since`` the grace window cannot be proved and the customer
    is downgraded immediately (see module docstring). Stamp it here and only here
    on entry — a second failed invoice inside the window must NOT push the
    deadline out, so an existing anchor is left alone.
    """
    sub = _flagship(org)
    sub.status = Subscription.Status.PAST_DUE
    if sub.past_due_since is None:
        sub.past_due_since = timezone.now()
    sub.save(update_fields=["status", "past_due_since", "updated_at"])


def handle_invoice_paid(org: Organization, obj: Mapping[str, Any]) -> None:
    """``invoice.paid`` — money arrived. Clear the grace anchor AND the past_due.

    Clearing the anchor alone would leave ``status=past_due, past_due_since=NULL``,
    which grants **nothing** — the customer would pay and immediately lose access.
    So a paid invoice also lifts ``past_due``/``unpaid`` back to ``active`` rather
    than waiting for a ``customer.subscription.updated`` that may arrive later, or
    out of order, or (for an org whose subscription we never attached) not at all.
    """
    sub = _flagship(org)
    fields = ["updated_at"]
    if sub.past_due_since is not None:
        sub.past_due_since = None
        fields.append("past_due_since")
    if sub.status in (Subscription.Status.PAST_DUE, Subscription.Status.UNPAID):
        sub.status = Subscription.Status.ACTIVE
        fields.append("status")
    if len(fields) > 1:
        sub.save(update_fields=fields)


HANDLERS: dict[str, Callable[[Organization, Mapping[str, Any]], None]] = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.created": handle_subscription_upsert,
    "customer.subscription.updated": handle_subscription_upsert,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.payment_failed": handle_payment_failed,
    "invoice.paid": handle_invoice_paid,
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def handle_event(event: Mapping[str, Any]) -> str:
    """Apply one signature-verified Stripe event. Returns a short outcome string.

    Outcomes: ``processed`` | ``duplicate`` | ``unhandled`` | ``no_org`` |
    ``malformed``. The caller (the webhook view) answers 200 for all of them — a
    non-2xx makes Stripe retry, and there is no point retrying an event we do not
    handle. Only an *exception* (a bug, a DB outage) escapes, becomes a 500, and
    earns a redelivery.
    """
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id:
        logger.error("stripe webhook with no event id: type=%r", event_type)
        return "malformed"

    # Claim the event. get_or_create is the dedupe; the row lock below is what
    # makes two simultaneous redeliveries safe.
    StripeEvent.objects.get_or_create(
        event_id=event_id,
        defaults={"type": event_type, "payload": event},
    )

    with transaction.atomic():
        ledger = (
            StripeEvent.objects.select_for_update().filter(event_id=event_id).first()
        )
        if ledger is None:  # pragma: no cover — we just created it
            return "malformed"
        if ledger.processed_at is not None:
            logger.info("stripe event %s (%s) already processed — skipping", event_id, event_type)
            return "duplicate"

        handler = HANDLERS.get(event_type)
        if handler is None:
            ledger.processed_at = timezone.now()
            ledger.save(update_fields=["processed_at"])
            return "unhandled"

        obj = (event.get("data") or {}).get("object") or {}
        org = resolve_org(obj)
        if org is None:
            logger.error(
                "stripe event %s (%s) could not be attributed to an org "
                "(no metadata.org_id, no known subscription, no matching customer)",
                event_id,
                event_type,
            )
            ledger.processed_at = timezone.now()
            ledger.save(update_fields=["processed_at"])
            return "no_org"

        handler(org, obj)

        # THE line that makes billing enforce: User.tier is a cache of the
        # subscription state, and every gate in the codebase reads User.tier.
        tenancy.sync_org_tiers(org)

        ledger.processed_at = timezone.now()
        ledger.save(update_fields=["processed_at"])

    return "processed"


__all__ = [
    "HANDLERS",
    "STRIPE_STATUS_MAP",
    "apply_subscription",
    "handle_event",
    "resolve_org",
]
