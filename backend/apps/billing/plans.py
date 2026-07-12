"""Price ID → plan, and back. The only mapping between Stripe and our tiers.

**No dollar amount ever appears in this codebase.** Prices live in the Stripe
dashboard; we hold their *IDs* in ``STRIPE_PRICE_SOLO`` / ``STRIPE_PRICE_FIRM`` /
``STRIPE_PRICE_FIRM_SEAT`` and translate a subscription's line items into one of
``accounts.Tier``'s plans. Re-pricing is then a Stripe dashboard change (new
price ID → new env var), never a deploy.

Two shapes of firm plan are supported, decided purely by whether
``STRIPE_PRICE_FIRM_SEAT`` is set:

* **flat per-seat** (FIRM_SEAT empty) — one line item, ``FIRM`` at quantity =
  seats.
* **base + per-seat** (FIRM_SEAT set) — ``FIRM`` at quantity 1 (the platform
  fee) plus ``FIRM_SEAT`` at quantity = seats. The seat-bearing item is the one
  :mod:`apps.billing.seats` moves, and the one the webhook reads ``seats`` from.

Both map to the ``firm`` plan, so :func:`plan_for_price` is many-to-one.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from django.conf import settings

from apps.accounts.models import Tier
from apps.tenancy.services import PLAN_RANK

logger = logging.getLogger(__name__)

# Plans a customer may self-serve into via Checkout. ``custom`` is sales-led and
# ``free`` is the absence of a subscription — neither is purchasable here.
PURCHASABLE_PLANS = (Tier.SOLO, Tier.FIRM)


def _price(name: str) -> str:
    return getattr(settings, name, "") or ""


def price_plan_map() -> dict[str, str]:
    """``{price_id: plan}`` for every configured price. Unconfigured → absent."""
    mapping: dict[str, str] = {}
    if _price("STRIPE_PRICE_SOLO"):
        mapping[_price("STRIPE_PRICE_SOLO")] = Tier.SOLO
    if _price("STRIPE_PRICE_FIRM"):
        mapping[_price("STRIPE_PRICE_FIRM")] = Tier.FIRM
    if _price("STRIPE_PRICE_FIRM_SEAT"):
        mapping[_price("STRIPE_PRICE_FIRM_SEAT")] = Tier.FIRM
    return mapping


def plan_for_price(price_id: str | None) -> str | None:
    """The plan a Stripe price grants, or None if we don't recognise the price.

    None is meaningful: it means someone bought a price we have no env var for
    (a legacy price, a hand-made subscription in the dashboard). Callers fall
    back to the subscription's ``metadata.plan`` rather than silently
    downgrading a paying customer to ``free``.
    """
    if not price_id:
        return None
    return price_plan_map().get(price_id)


def seat_price_id() -> str:
    """The price whose *quantity* is the seat count, if a separate one exists."""
    return _price("STRIPE_PRICE_FIRM_SEAT")


def line_items_for(plan: str, quantity: int) -> list[dict[str, Any]]:
    """Stripe Checkout ``line_items`` for ``plan`` at ``quantity`` seats.

    Raises ValueError when the plan is not purchasable or its price ID is not
    configured — the API layer turns that into a 503, because a missing price ID
    is a deployment gap, not a client mistake.
    """
    if plan not in PURCHASABLE_PLANS:
        raise ValueError(f"plan {plan!r} is not purchasable")
    quantity = max(1, int(quantity))

    if plan == Tier.SOLO:
        price = _price("STRIPE_PRICE_SOLO")
        if not price:
            raise ValueError("STRIPE_PRICE_SOLO is not configured")
        # A solo plan bills one person: the personal org that holds it has one
        # member by construction.
        return [{"price": price, "quantity": 1}]

    base = _price("STRIPE_PRICE_FIRM")
    if not base:
        raise ValueError("STRIPE_PRICE_FIRM is not configured")
    seat = seat_price_id()
    if seat:
        # base + per-seat: the base rides at qty 1, seats ride on the seat price.
        return [
            {"price": base, "quantity": 1},
            {"price": seat, "quantity": quantity},
        ]
    return [{"price": base, "quantity": quantity}]


# ---------------------------------------------------------------------------
# Reading a live Stripe subscription's items back into our columns
# ---------------------------------------------------------------------------


def _item_price_id(item: Mapping[str, Any]) -> str:
    price = item.get("price") or {}
    if isinstance(price, str):
        return price
    return str(price.get("id") or "")


def plan_from_items(items: Iterable[Mapping[str, Any]]) -> str | None:
    """The best (highest-ranked) plan across a subscription's line items.

    A base+seat firm subscription has two items that both map to ``firm``; taking
    the max also means a subscription that somehow carries both a solo and a firm
    price resolves to ``firm`` rather than to whichever item Stripe listed first.
    """
    best: str | None = None
    for item in items or ():
        plan = plan_for_price(_item_price_id(item))
        if plan is None:
            continue
        if best is None or PLAN_RANK.get(plan, 0) > PLAN_RANK.get(best, 0):
            best = plan
    return best


def seat_item(items: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The line item whose quantity IS the seat count.

    The configured per-seat price wins. Failing that, a single-item subscription
    is unambiguous — its one item is the seat item (the flat per-seat firm plan,
    and the solo plan). Anything else is ambiguous and returns None: better to
    log and leave the quantity alone than to move the wrong line and mis-bill.
    """
    items = list(items or ())
    seat_price = seat_price_id()
    if seat_price:
        for item in items:
            if _item_price_id(item) == seat_price:
                return item
    if len(items) == 1:
        return items[0]
    return None


def seats_from_items(items: Iterable[Mapping[str, Any]], default: int = 1) -> int:
    """Seat count carried by a subscription's items. Never below 1."""
    item = seat_item(items)
    if item is None:
        return max(1, default)
    return max(1, int(item.get("quantity") or default or 1))


def price_id_from_items(items: Iterable[Mapping[str, Any]]) -> str:
    """The price ID we record on ``Subscription.stripe_price_id`` — the seat item's
    (the one that identifies what they're actually paying per head), else the
    first item's."""
    item = seat_item(items)
    if item is None:
        items = list(items or ())
        item = items[0] if items else None
    return _item_price_id(item) if item else ""


__all__ = [
    "PURCHASABLE_PLANS",
    "line_items_for",
    "plan_for_price",
    "plan_from_items",
    "price_id_from_items",
    "price_plan_map",
    "seat_item",
    "seat_price_id",
    "seats_from_items",
]
