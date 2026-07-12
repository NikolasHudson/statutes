"""``setup_stripe_products`` — the bootstrap must be idempotent and must refuse
to silently accept a Stripe price that has drifted from its spec.

The fake here is stateful (a tiny in-memory Stripe): the second run of the
command sees what the first run created, which is the whole point.
"""

from __future__ import annotations

from io import StringIO
from typing import Any
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.billing.management.commands.setup_stripe_products import PRICES, PRODUCTS


class _MissingError(Exception):
    code = "resource_missing"


class StatefulFakeStripe:
    """Product/Price CRUD over in-memory dicts, enough for the command."""

    def __init__(self):
        self.api_key = "sk_test_fake"
        self.products: dict[str, dict[str, Any]] = {}
        self.prices: dict[str, dict[str, Any]] = {}  # keyed by price id
        self.created_prices = 0
        outer = self

        class _Product:
            @staticmethod
            def retrieve(product_id):
                if product_id not in outer.products:
                    raise _MissingError(product_id)
                return outer.products[product_id]

            @staticmethod
            def create(**kwargs):
                outer.products[kwargs["id"]] = {"active": True, **kwargs}
                return outer.products[kwargs["id"]]

            @staticmethod
            def modify(product_id, **kwargs):
                outer.products[product_id].update(kwargs)
                return outer.products[product_id]

        class _Price:
            @staticmethod
            def list(*, lookup_keys, limit=1, expand=()):
                data = [
                    p for p in outer.prices.values()
                    if p.get("lookup_key") in lookup_keys and p.get("active", True)
                ]
                return {"data": data[:limit]}

            @staticmethod
            def create(**kwargs):
                outer.created_prices += 1
                price_id = f"price_fake_{outer.created_prices}"
                if kwargs.pop("transfer_lookup_key", False):
                    for p in outer.prices.values():
                        if p.get("lookup_key") == kwargs.get("lookup_key"):
                            p["lookup_key"] = None
                price = {"id": price_id, "active": True, **kwargs}
                # normalise the catch-all tier the way Stripe echoes it back
                for tier in price.get("tiers", []) or []:
                    if tier.get("up_to") == "inf":
                        tier["up_to"] = None
                outer.prices[price_id] = price
                return price

        self.Product = _Product
        self.Price = _Price


def run(fake: StatefulFakeStripe, *args) -> str:
    out = StringIO()
    with mock.patch("apps.billing.stripe_api.get_stripe", return_value=fake):
        call_command("setup_stripe_products", *args, stdout=out)
    return out.getvalue()


@override_settings(STRIPE_SECRET_KEY="sk_test_fake")
class SetupStripeProductsTests(TestCase):
    def test_unconfigured_stripe_is_a_clean_error(self):
        with override_settings(STRIPE_SECRET_KEY=""):
            with self.assertRaises(CommandError) as ctx:
                call_command("setup_stripe_products", stdout=StringIO())
        self.assertIn("STRIPE_SECRET_KEY", str(ctx.exception))

    def test_creates_every_product_and_price_and_prints_the_env_block(self):
        fake = StatefulFakeStripe()
        output = run(fake)
        self.assertEqual(set(fake.products), {p["id"] for p in PRODUCTS})
        self.assertEqual(len(fake.prices), len(PRICES))
        for var in ("STRIPE_PRICE_SOLO=", "STRIPE_PRICE_FIRM=", "STRIPE_PRICE_FIRM_SEAT="):
            self.assertIn(var, output)
        # the annual price exists but is not wired to an env var
        self.assertIn("hudson_solo_annual", output)
        self.assertNotIn("STRIPE_PRICE_SOLO_ANNUAL", output)

    def test_the_seat_price_is_graduated_with_three_included_seats(self):
        fake = StatefulFakeStripe()
        run(fake)
        seat = next(
            p for p in fake.prices.values()
            if p["lookup_key"] == "hudson_firm_seat_monthly"
        )
        self.assertEqual(seat["billing_scheme"], "tiered")
        self.assertEqual(seat["tiers_mode"], "graduated")
        self.assertEqual(
            seat["tiers"],
            [{"up_to": 3, "unit_amount": 0}, {"up_to": None, "unit_amount": 3900}],
        )

    def test_second_run_creates_nothing_and_prints_the_same_ids(self):
        fake = StatefulFakeStripe()
        first = run(fake)
        created = fake.created_prices
        second = run(fake)
        self.assertEqual(fake.created_prices, created)
        env = lambda out: [l for l in out.splitlines() if l.startswith("STRIPE_")]  # noqa: E731
        self.assertEqual(env(first), env(second))

    def test_drifted_price_fails_loudly_without_rotate(self):
        fake = StatefulFakeStripe()
        run(fake)
        solo = next(
            p for p in fake.prices.values() if p["lookup_key"] == "hudson_solo_monthly"
        )
        solo["unit_amount"] = 2900  # someone repriced behind our back
        with self.assertRaises(CommandError) as ctx:
            run(fake)
        self.assertIn("hudson_solo_monthly", str(ctx.exception))
        self.assertIn("--rotate", str(ctx.exception))

    def test_rotate_replaces_the_drifted_price_and_moves_the_lookup_key(self):
        fake = StatefulFakeStripe()
        run(fake)
        solo = next(
            p for p in fake.prices.values() if p["lookup_key"] == "hudson_solo_monthly"
        )
        old_id = solo["id"]
        solo["unit_amount"] = 2900
        output = run(fake, "--rotate")
        replacement = next(
            p for p in fake.prices.values()
            if p.get("lookup_key") == "hudson_solo_monthly"
        )
        self.assertNotEqual(replacement["id"], old_id)
        self.assertEqual(replacement["unit_amount"], 4900)
        self.assertIn(f"STRIPE_PRICE_SOLO={replacement['id']}", output)
