"""Seat sync — push ``seat_count(org)`` to Stripe as the subscription quantity.

:func:`apps.tenancy.services.sync_seats` already calls this behind a
``try/except ImportError`` and swallows Stripe errors, so every membership
mutation (add / remove / role change / invitation accept) reaches here for free.
The contract that buys is: **a member is a seat, and a seat is a line on the
bill.** No per-product seat assignment, no manual reconciliation.

Three refusals keep it safe:

* **Never below 1.** Stripe rejects quantity 0 on a licensed price, and an org
  transiently at zero members (mid-migration, a botched removal) must not blow up
  the membership write that caused it.
* **No-op when unchanged.** ``proration_behavior="create_prorations"`` means every
  write is a line on the customer's next invoice; re-sending the same quantity
  would litter it with zero-value prorations.
* **No-op when Stripe is unconfigured, or when there is nothing to sync** — a
  comped subscription (backfilled, no Stripe object) and a dev box with no keys
  both land here, and neither is an error. Log and return.
"""

from __future__ import annotations

import logging

from apps.tenancy.models import Organization, Subscription
from apps.tenancy.services import flagship_subscription, seat_count

from . import plans, stripe_api

logger = logging.getLogger(__name__)


def sync_seats(org: Organization) -> int | None:
    """Set the Stripe quantity for ``org``'s flagship subscription to its seat count.

    Returns the quantity written, or None when nothing was done. Exceptions from
    Stripe propagate to ``tenancy.services.sync_seats``, which logs them and lets
    the membership change stand — losing a member because Stripe hiccuped would be
    a far worse failure than a stale quantity, which the next mutation (or the
    next webhook) repairs.
    """
    if not stripe_api.is_configured():
        logger.info(
            "stripe not configured — skipping seat sync for org %s (seats would be %s)",
            org.pk,
            seat_count(org),
        )
        return None

    sub = flagship_subscription(org)
    if sub is None or not sub.stripe_subscription_id:
        logger.debug("org %s has no Stripe subscription — no seats to sync", org.pk)
        return None
    if sub.status == Subscription.Status.CANCELED:
        # Stripe refuses to modify items on a canceled subscription, and there is
        # no bill to move anyway.
        logger.debug("org %s subscription is canceled — no seats to sync", org.pk)
        return None

    quantity = max(1, seat_count(org))

    client = stripe_api.get_stripe()
    stripe_sub = client.Subscription.retrieve(sub.stripe_subscription_id)
    items = (stripe_sub.get("items") or {}).get("data") or []

    item = plans.seat_item(items)
    if item is None:
        logger.warning(
            "cannot identify the seat line item on stripe subscription %s (org %s, "
            "%d items) — leaving the quantity alone. Set STRIPE_PRICE_FIRM_SEAT to "
            "disambiguate a multi-item subscription.",
            sub.stripe_subscription_id,
            org.pk,
            len(items),
        )
        return None

    current = int(item.get("quantity") or 0)
    if current == quantity:
        # Keep our column honest even when Stripe needs no write.
        if sub.seats != quantity:
            Subscription.objects.filter(pk=sub.pk).update(seats=quantity)
        return quantity

    client.SubscriptionItem.modify(
        item["id"],
        quantity=quantity,
        proration_behavior="create_prorations",
    )
    Subscription.objects.filter(pk=sub.pk).update(seats=quantity)
    logger.info(
        "org %s seats %s → %s on stripe subscription %s",
        org.pk,
        current,
        quantity,
        sub.stripe_subscription_id,
    )
    return quantity


__all__ = ["sync_seats"]
