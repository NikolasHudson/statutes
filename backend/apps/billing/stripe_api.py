"""The one place ``import stripe`` happens.

Two jobs, both about keeping Stripe *optional*:

* **Booting without Stripe.** ``import stripe`` is lazy (inside
  :func:`get_stripe`), so a checkout that lacks the dependency — CI on an old
  lock, a dev box that never ran ``pip install`` — still boots Django, runs the
  test suite, and serves every non-billing route. Stripe is a runtime
  dependency of three endpoints, not of the application.
* **One patch point.** Every caller reaches Stripe through
  ``stripe_api.get_stripe()`` (module attribute, resolved at call time), so the
  whole test suite mocks Stripe by patching this single function. No test ever
  touches the network.

"Configured" means exactly one thing: a non-empty ``STRIPE_SECRET_KEY``. When it
is empty the Stripe-calling endpoints answer a clean 503 and
:func:`apps.billing.seats.sync_seats` no-ops with a log line — a membership
change must never fail because nobody has set up billing yet.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class BillingNotConfigured(RuntimeError):
    """No ``STRIPE_SECRET_KEY`` (or no ``stripe`` package). Maps to a 503."""


def is_configured() -> bool:
    """True when Stripe API calls are possible. The single source of that truth."""
    return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))


def get_stripe() -> Any:
    """The ``stripe`` module, api_key already set.

    Raises :class:`BillingNotConfigured` rather than returning a half-configured
    client — an unconfigured Stripe must fail as a 503 at the edge, never as a
    confusing ``AuthenticationError`` from deep inside a request.
    """
    if not is_configured():
        raise BillingNotConfigured("billing not configured: STRIPE_SECRET_KEY is unset")
    try:
        import stripe  # noqa: PLC0415 — deliberately lazy; see module docstring
    except ImportError as exc:  # pragma: no cover — dependency is in requirements
        raise BillingNotConfigured(
            "billing not configured: the 'stripe' package is not installed"
        ) from exc

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def webhook_secret() -> str:
    return getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or ""


__all__ = ["BillingNotConfigured", "get_stripe", "is_configured", "webhook_secret"]
