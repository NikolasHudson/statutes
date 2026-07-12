"""Price ID → plan. The only place Stripe's vocabulary meets ours.

The invariant this file really guards is negative: **no dollar amount appears
anywhere in apps/billing.** Prices live in the Stripe dashboard; Python only ever
holds price *IDs*. A re-price is then an env change, not a deploy.
"""

from __future__ import annotations

import pathlib
import re

from django.test import SimpleTestCase, override_settings

from apps.accounts.models import Tier
from apps.billing import plans

from ._stripe import PRICE_FIRM, PRICE_FIRM_SEAT, PRICE_SOLO, STRIPE_SETTINGS


@override_settings(**STRIPE_SETTINGS)
class PriceMapTests(SimpleTestCase):
    def test_maps_configured_prices_to_plans(self):
        self.assertEqual(plans.plan_for_price(PRICE_SOLO), Tier.SOLO)
        self.assertEqual(plans.plan_for_price(PRICE_FIRM), Tier.FIRM)

    def test_unknown_or_empty_price_is_none_not_free(self):
        """None means 'we don't recognise this'; the caller falls back to metadata
        rather than downgrading a paying customer to free."""
        self.assertIsNone(plans.plan_for_price("price_nope"))
        self.assertIsNone(plans.plan_for_price(""))
        self.assertIsNone(plans.plan_for_price(None))

    @override_settings(**{**STRIPE_SETTINGS, "STRIPE_PRICE_FIRM_SEAT": PRICE_FIRM_SEAT})
    def test_the_seat_price_also_means_firm(self):
        self.assertEqual(plans.plan_for_price(PRICE_FIRM_SEAT), Tier.FIRM)

    @override_settings(STRIPE_PRICE_SOLO="", STRIPE_PRICE_FIRM="", STRIPE_PRICE_FIRM_SEAT="")
    def test_unconfigured_prices_map_nothing(self):
        self.assertEqual(plans.price_plan_map(), {})

    def test_plan_from_items_takes_the_highest_rank(self):
        items = [
            {"price": {"id": PRICE_SOLO}, "quantity": 1},
            {"price": {"id": PRICE_FIRM}, "quantity": 3},
        ]
        self.assertEqual(plans.plan_from_items(items), Tier.FIRM)

    def test_plan_from_items_tolerates_an_unexpanded_price(self):
        self.assertEqual(
            plans.plan_from_items([{"price": PRICE_SOLO, "quantity": 1}]), Tier.SOLO
        )

    def test_seats_from_items_never_returns_zero(self):
        self.assertEqual(
            plans.seats_from_items([{"price": {"id": PRICE_FIRM}, "quantity": 0}]), 1
        )
        self.assertEqual(plans.seats_from_items([]), 1)


@override_settings(**STRIPE_SETTINGS)
class LineItemTests(SimpleTestCase):
    def test_refuses_an_unpurchasable_plan(self):
        for plan in (Tier.FREE, Tier.CUSTOM, "bogus"):
            with self.assertRaises(ValueError):
                plans.line_items_for(plan, 1)

    @override_settings(**{**STRIPE_SETTINGS, "STRIPE_PRICE_FIRM": ""})
    def test_refuses_when_the_price_id_is_not_configured(self):
        with self.assertRaises(ValueError):
            plans.line_items_for(Tier.FIRM, 2)

    def test_quantity_is_floored_at_one(self):
        self.assertEqual(
            plans.line_items_for(Tier.FIRM, 0), [{"price": PRICE_FIRM, "quantity": 1}]
        )


class NoHardcodedPricesTests(SimpleTestCase):
    """Application code must never know a dollar amount — only price IDs.

    Scans apps/billing for anything that looks like a dollar amount or a Stripe
    amount-in-cents constant. The one exemption is ``management/`` — the
    ``setup_stripe_products`` bootstrap is the tool that *puts* the decided price
    points (PRICING_STRATEGY.md §5, 2026-07-11) into Stripe, so it is the single
    legitimate holder of amounts. Request-path modules (plans/api/webhooks/seats)
    stay amount-free: repricing is a dashboard change plus an env-var swap,
    never a deploy.
    """

    def test_no_dollar_amounts_in_the_billing_package(self):
        package = pathlib.Path(__file__).resolve().parent.parent
        # $29 / 29.00 / unit_amount=2900 — the three ways a price sneaks in.
        dollars = re.compile(r"\$\s?\d|unit_amount|\bprice_data\b|\bamount\s*=\s*\d")
        offenders = []
        for path in package.rglob("*.py"):
            if {"tests", "migrations", "management"} & set(path.parts):
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if dollars.search(line):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
        self.assertEqual(offenders, [], "prices belong in Stripe, not in Python")
