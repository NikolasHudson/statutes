"""Create the Stripe Products/Prices for the 2026-07-11 price points — idempotently.

This command is the automated form of BILLING_PLAN §7.1 ("create the Products/
Prices in the dashboard"): run it once against a test key, once against the live
key, paste the env block it prints into ``backend/.env`` / the App Platform spec.

The dollar amounts below are the ONLY place they appear in the codebase, and the
application never reads them — it reads *price IDs* from ``STRIPE_PRICE_*``
(apps/billing/plans.py). Re-pricing stays a dashboard operation: create a new
Price there (or edit the specs here and re-run with ``--rotate``), then swap the
env var. Price points per PRICING_STRATEGY.md §5:

* Solo — $49/mo, $490/yr (annual is created but not yet sold via Checkout).
* Firm — $149/mo base including 3 seats, +$39/seat beyond. Modelled as the
  base+seat shape plans.py already supports: the base price rides at quantity 1
  and the seat price carries ``quantity = seat_count`` with graduated tiers
  (first 3 units $0, then $39/unit), so 3 seats = $149, 5 = $227, 10 = $422 —
  and apps/billing/seats.py can keep moving a plain quantity.

The 7-day trial is NOT a property of these prices — Stripe trials live on the
Checkout session (``subscription_data.trial_period_days``), wired in
apps/billing/api.py from ``STRIPE_TRIAL_DAYS``.

Idempotency: products get fixed ids (``hudson-solo``…), prices are found by
``lookup_key``. Re-running verifies the existing objects match the specs and
creates nothing. A mismatch (someone edited a spec — prices are immutable in
Stripe) is reported and fails the run unless ``--rotate`` is passed, which
creates a replacement price and moves the lookup_key onto it.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.billing import stripe_api
from apps.billing.stripe_api import BillingNotConfigured

PRODUCTS = [
    {"id": "hudson-solo", "name": "Hudson Solo"},
    {"id": "hudson-firm", "name": "Hudson Firm"},
    {"id": "hudson-firm-seat", "name": "Hudson Firm — Additional seats"},
]

# amounts are integer cents. ``tiers`` marks a graduated tiered price.
PRICES: list[dict[str, Any]] = [
    {
        "lookup_key": "hudson_solo_monthly",
        "product": "hudson-solo",
        "env": "STRIPE_PRICE_SOLO",
        "interval": "month",
        "unit_amount": 4900,
    },
    {
        # Created so it exists for portal/dashboard use; Checkout only sells the
        # monthly prices today (line_items_for knows nothing of intervals).
        "lookup_key": "hudson_solo_annual",
        "product": "hudson-solo",
        "env": None,
        "interval": "year",
        "unit_amount": 49000,
    },
    {
        "lookup_key": "hudson_firm_base_monthly",
        "product": "hudson-firm",
        "env": "STRIPE_PRICE_FIRM",
        "interval": "month",
        "unit_amount": 14900,
    },
    {
        "lookup_key": "hudson_firm_seat_monthly",
        "product": "hudson-firm-seat",
        "env": "STRIPE_PRICE_FIRM_SEAT",
        "interval": "month",
        # First 3 seats are inside the $149 base; each seat past that is $39.
        "tiers": [
            {"up_to": 3, "unit_amount": 0},
            {"up_to": "inf", "unit_amount": 3900},
        ],
    },
]


class Command(BaseCommand):
    help = (
        "Idempotently create the Hudson Products/Prices in Stripe and print the "
        "STRIPE_PRICE_* env block. Uses STRIPE_SECRET_KEY (test or live)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--rotate",
            action="store_true",
            help=(
                "When an existing price no longer matches its spec, create a "
                "replacement and transfer the lookup_key onto it (the old price "
                "stays valid for existing subscribers)."
            ),
        )

    def handle(self, *args, **options):
        try:
            stripe = stripe_api.get_stripe()
        except BillingNotConfigured as exc:
            raise CommandError(
                f"{exc}. Put a Stripe secret key (test mode first) in backend/.env "
                "as STRIPE_SECRET_KEY and re-run."
            ) from exc

        mode = "TEST" if str(stripe.api_key or "").startswith(("sk_test", "rk_test")) else "LIVE"
        self.stdout.write(f"Stripe key mode: {mode}")

        for spec in PRODUCTS:
            self._ensure_product(stripe, spec)

        env_lines: list[str] = []
        extra_lines: list[str] = []
        mismatches: list[str] = []
        for spec in PRICES:
            price_id, note = self._ensure_price(stripe, spec, rotate=options["rotate"])
            if price_id is None:
                mismatches.append(note)
                continue
            self.stdout.write(f"  {spec['lookup_key']}: {price_id} ({note})")
            if spec["env"]:
                env_lines.append(f"{spec['env']}={price_id}")
            else:
                extra_lines.append(f"# {spec['lookup_key']} (not sold via checkout): {price_id}")

        if mismatches:
            raise CommandError(
                "price spec mismatch — Stripe prices are immutable; re-run with "
                "--rotate to create replacements:\n  " + "\n  ".join(mismatches)
            )

        self.stdout.write(self.style.SUCCESS("\nPaste into backend/.env (and the prod spec):"))
        for line in env_lines + extra_lines:
            self.stdout.write(line)

    # ------------------------------------------------------------------
    # Products — fixed ids make retrieve-or-create trivial
    # ------------------------------------------------------------------

    def _ensure_product(self, stripe, spec: dict) -> None:
        try:
            product = stripe.Product.retrieve(spec["id"])
        except Exception as exc:  # noqa: BLE001 — stripe.InvalidRequestError
            if getattr(exc, "code", "") != "resource_missing":
                raise
            product = stripe.Product.create(id=spec["id"], name=spec["name"])
            self.stdout.write(f"  created product {spec['id']}")
            return
        if not _get(product, "active", True):
            stripe.Product.modify(spec["id"], active=True)
            self.stdout.write(f"  reactivated product {spec['id']}")

    # ------------------------------------------------------------------
    # Prices — found by lookup_key, verified against the spec
    # ------------------------------------------------------------------

    def _ensure_price(self, stripe, spec: dict, *, rotate: bool) -> tuple[str | None, str]:
        existing = stripe.Price.list(
            lookup_keys=[spec["lookup_key"]], limit=1, expand=["data.tiers"]
        )
        rows = _get(existing, "data", []) or []
        if rows:
            price = rows[0]
            price_id = _get(price, "id", "")
            problem = _spec_mismatch(price, spec)
            if not problem:
                return price_id, "exists"
            if not rotate:
                return None, f"{spec['lookup_key']} ({price_id}): {problem}"
            price = self._create_price(stripe, spec, transfer_lookup_key=True)
            return _get(price, "id", ""), f"rotated (was {price_id}: {problem})"

        price = self._create_price(stripe, spec)
        return _get(price, "id", ""), "created"

    def _create_price(self, stripe, spec: dict, *, transfer_lookup_key: bool = False):
        kwargs: dict[str, Any] = {
            "product": spec["product"],
            "currency": "usd",
            "recurring": {"interval": spec["interval"]},
            "lookup_key": spec["lookup_key"],
            "transfer_lookup_key": transfer_lookup_key,
            "metadata": {"managed_by": "setup_stripe_products"},
        }
        if "tiers" in spec:
            kwargs["billing_scheme"] = "tiered"
            kwargs["tiers_mode"] = "graduated"
            kwargs["tiers"] = spec["tiers"]
        else:
            kwargs["unit_amount"] = spec["unit_amount"]
        return stripe.Price.create(**kwargs)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Stripe objects are dict-like; test fakes are plain dicts. Read either."""
    if hasattr(obj, "get"):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _spec_mismatch(price: Any, spec: dict) -> str:
    """Why ``price`` no longer matches ``spec`` — empty string when it does."""
    if str(_get(price, "currency", "usd")).lower() != "usd":
        return f"currency is {_get(price, 'currency')}"
    recurring = _get(price, "recurring") or {}
    if _get(recurring, "interval") != spec["interval"]:
        return f"interval is {_get(recurring, 'interval')}, spec says {spec['interval']}"
    if not _get(price, "active", True):
        return "price is inactive"
    if "tiers" in spec:
        got = [
            {"up_to": _get(t, "up_to"), "unit_amount": _get(t, "unit_amount")}
            for t in (_get(price, "tiers") or [])
        ]
        want = [
            # Stripe returns the catch-all tier's up_to as None, not "inf".
            {"up_to": None if t["up_to"] == "inf" else t["up_to"], "unit_amount": t["unit_amount"]}
            for t in spec["tiers"]
        ]
        if got != want:
            return f"tiers are {got}, spec says {want}"
        return ""
    if _get(price, "unit_amount") != spec["unit_amount"]:
        return f"unit_amount is {_get(price, 'unit_amount')}, spec says {spec['unit_amount']}"
    return ""
