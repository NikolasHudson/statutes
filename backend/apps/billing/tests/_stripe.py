"""Stripe test doubles + event fixtures. **No test in this package touches the
network.**

Every Stripe call in ``apps/billing`` goes through ``stripe_api.get_stripe()``
(module attribute, looked up at call time), so :func:`mock_stripe` patching that
one function is enough to intercept the whole SDK.

Webhook signatures are the exception: those are computed *for real* with the
documented ``t=<ts>,v1=<hmac>`` scheme against a test secret, so the tests
exercise the actual ``stripe.Webhook.construct_event`` verification path rather
than mocking it away. A bad-signature test that mocks the verifier proves
nothing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from typing import Any
from unittest import mock

TEST_SECRET_KEY = "sk_test_fake"
TEST_WEBHOOK_SECRET = "whsec_test_fake"
PRICE_SOLO = "price_solo_test"
PRICE_FIRM = "price_firm_test"
PRICE_FIRM_SEAT = "price_firm_seat_test"

STRIPE_SETTINGS = {
    "STRIPE_SECRET_KEY": TEST_SECRET_KEY,
    "STRIPE_WEBHOOK_SECRET": TEST_WEBHOOK_SECRET,
    "STRIPE_PRICE_SOLO": PRICE_SOLO,
    "STRIPE_PRICE_FIRM": PRICE_FIRM,
    "STRIPE_PRICE_FIRM_SEAT": "",  # flat per-seat firm price by default
    "STRIPE_RETURN_BASE_URL": "https://app.example.com",
}


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def sign(payload: bytes, secret: str = TEST_WEBHOOK_SECRET, timestamp: int | None = None) -> str:
    """A real Stripe-Signature header for ``payload``. Same scheme Stripe uses."""
    ts = timestamp or int(time.time())
    signed = f"{ts}.{payload.decode()}".encode()
    mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


# ---------------------------------------------------------------------------
# The fake SDK
# ---------------------------------------------------------------------------


class FakeStripe:
    """Just enough Stripe to satisfy apps/billing, with call recording.

    ``Webhook`` is the *real* module — signature verification is genuine — while
    everything that would hit the network is a recorded fake.
    """

    def __init__(self, *, subscription: dict[str, Any] | None = None):
        import stripe as real_stripe

        self.Webhook = real_stripe.Webhook
        self.api_key = None
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._subscription = subscription or subscription_obj()

        outer = self

        class _Customer:
            @staticmethod
            def create(**kwargs):
                outer.calls.append(("Customer.create", kwargs))
                return {"id": "cus_new_test"}

        class _Session:
            @staticmethod
            def create(**kwargs):
                outer.calls.append(("checkout.Session.create", kwargs))
                return {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}

        class _Checkout:
            Session = _Session

        class _PortalSession:
            @staticmethod
            def create(**kwargs):
                outer.calls.append(("billing_portal.Session.create", kwargs))
                return {"id": "bps_test_1", "url": "https://billing.stripe.com/p/session/test"}

        class _BillingPortal:
            Session = _PortalSession

        class _Subscription:
            @staticmethod
            def retrieve(sub_id, **kwargs):
                outer.calls.append(("Subscription.retrieve", {"id": sub_id}))
                return outer._subscription

        class _SubscriptionItem:
            @staticmethod
            def modify(item_id, **kwargs):
                outer.calls.append(("SubscriptionItem.modify", {"id": item_id, **kwargs}))
                return {"id": item_id, "quantity": kwargs.get("quantity")}

        self.Customer = _Customer
        self.checkout = _Checkout
        self.billing_portal = _BillingPortal
        self.Subscription = _Subscription
        self.SubscriptionItem = _SubscriptionItem

    def set_subscription(self, sub: dict[str, Any]) -> None:
        self._subscription = sub

    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def call_args(self, name: str) -> dict[str, Any]:
        for called, kwargs in self.calls:
            if called == name:
                return kwargs
        raise AssertionError(f"{name} was never called; got {self.call_names()}")


@contextmanager
def mock_stripe(fake: FakeStripe | None = None):
    """Patch ``stripe_api.get_stripe`` — the single seam the whole app calls through."""
    fake = fake or FakeStripe()
    with mock.patch("apps.billing.stripe_api.get_stripe", return_value=fake):
        yield fake


# ---------------------------------------------------------------------------
# Event fixtures
# ---------------------------------------------------------------------------


def item(price_id: str = PRICE_SOLO, quantity: int = 1, item_id: str = "si_test_1") -> dict:
    return {
        "id": item_id,
        "object": "subscription_item",
        "quantity": quantity,
        "price": {"id": price_id, "object": "price"},
    }


def subscription_obj(
    *,
    sub_id: str = "sub_test_1",
    customer: str = "cus_test_1",
    status: str = "active",
    org_id: int | None = None,
    plan: str | None = None,
    items: list[dict] | None = None,
    current_period_end: int | None = 1_800_000_000,
    cancel_at_period_end: bool = False,
    trial_end: int | None = None,
) -> dict:
    metadata: dict[str, str] = {}
    if org_id is not None:
        metadata["org_id"] = str(org_id)
    if plan is not None:
        metadata["plan"] = plan
    return {
        "id": sub_id,
        "object": "subscription",
        "customer": customer,
        "status": status,
        "metadata": metadata,
        "items": {"object": "list", "data": items if items is not None else [item()]},
        "current_period_end": current_period_end,
        "cancel_at_period_end": cancel_at_period_end,
        "trial_end": trial_end,
    }


def checkout_session_obj(
    *,
    session_id: str = "cs_test_1",
    customer: str = "cus_test_1",
    subscription: str | None = "sub_test_1",
    org_id: int | None = None,
    plan: str = "solo",
) -> dict:
    return {
        "id": session_id,
        "object": "checkout.session",
        "customer": customer,
        "subscription": subscription,
        "client_reference_id": str(org_id) if org_id is not None else None,
        "metadata": {
            **({"org_id": str(org_id)} if org_id is not None else {}),
            "plan": plan,
        },
        "mode": "subscription",
        "status": "complete",
    }


def invoice_obj(
    *,
    invoice_id: str = "in_test_1",
    customer: str = "cus_test_1",
    subscription: str | None = "sub_test_1",
) -> dict:
    return {
        "id": invoice_id,
        "object": "invoice",
        "customer": customer,
        "subscription": subscription,
        "metadata": {},
        "lines": {"data": []},
    }


def event(event_type: str, obj: dict, *, event_id: str = "evt_test_1") -> dict:
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "api_version": "2024-06-20",
        "created": 1_700_000_000,
        "data": {"object": obj},
    }


def event_body(event_type: str, obj: dict, *, event_id: str = "evt_test_1") -> bytes:
    return json.dumps(event(event_type, obj, event_id=event_id)).encode()
