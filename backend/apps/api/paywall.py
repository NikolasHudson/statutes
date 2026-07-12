"""The 402 paywall for session-authenticated interactive endpoints.

There is no free account (decided 2026-07-12): outside the 7-day Stripe trial,
the interactive surfaces require a paid plan. The rule itself lives in
:func:`apps.tenancy.services.has_paid_access` (and is a no-op until
``BILLING_REQUIRE_PAID`` is flipped); this module is only the API-layer
translation of "no" into a response.

402 Payment Required — deliberately distinct from 403 so the SPA can route the
user to the plan picker instead of showing a permissions error. The API-key /
MCP surface goes through :func:`apps.api.auth.require_feature` instead, which
applies the same rule.
"""

from __future__ import annotations

from ninja.errors import HttpError

from apps.tenancy.services import has_paid_access

PAYWALL_DETAIL = (
    "This feature requires an active plan. Start your free trial or manage "
    "your subscription under Account → Billing."
)


def require_paid_access(user) -> None:
    """Raise 402 unless ``user`` holds a live paid plan (or billing
    enforcement is off)."""
    if not has_paid_access(user):
        raise HttpError(402, PAYWALL_DETAIL)
