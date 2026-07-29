"""API key auth + tier-based rate limiting for the Ninja API.

The API key lives in the ``X-API-Key`` request header. Verification goes
through :func:`apps.accounts.models.verify_key`, which already handles the
prefix lookup + SHA-256 hash check + revoked-at filter. On success we set
``request.auth`` to the ``APIKey`` row so downstream handlers can read the
user and tier off it.

Rate limiting is intentionally minimal here: a per-key sliding window backed
by Django's cache. Production will swap this for a Redis-backed token bucket
on Cross-cutting Phase. The current implementation is correct for a single
process and gives us a real 429 surface without paying the Redis bill yet.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.core.cache import cache
from django.utils import timezone
from ninja.errors import HttpError
from ninja.security import APIKeyHeader

from apps.accounts.models import APIKey, Tier, verify_key


# Per-tier daily quotas. The free tier number matches the brief
# ("142/500 monthly queries" in the Profile UI) interpreted as a generous
# daily ceiling for now — Phase 6 will make this monthly with a quota model
# of its own.
TIER_DAILY_QUOTA: dict[str, int | None] = {
    Tier.FREE: 200,
    Tier.SOLO: 5_000,
    Tier.FIRM: 50_000,
    Tier.CUSTOM: None,  # unlimited
}


# Features locked behind paid tiers. Free callers can do citation lookups and
# a small amount of search; everything else is gated.
#
# ``edms`` (Hudson EDMSpro — court-filing routing, apps/edms) is included in
# every paid tier rather than sold as an add-on: it is the differentiator
# against LexIowa, and a feature you have to notice and buy separately is a
# feature most subscribers never discover. One row here is all that has to
# change if that decision is ever revisited.
FEATURES_BY_TIER: dict[str, set[str]] = {
    Tier.FREE: {"lookup", "search"},
    Tier.SOLO: {
        "lookup", "search", "history", "at_date", "cross_refs",
        "definitions", "amendments", "validate", "edms",
    },
    Tier.FIRM: {
        "lookup", "search", "history", "at_date", "cross_refs",
        "definitions", "amendments", "validate", "edms",
    },
    Tier.CUSTOM: {
        "lookup", "search", "history", "at_date", "cross_refs",
        "definitions", "amendments", "validate", "edms",
    },
}


# Every feature the product defines, derived rather than restated so a feature
# added to a tier above cannot be forgotten here.
ALL_FEATURES: frozenset[str] = frozenset().union(*FEATURES_BY_TIER.values())


def allowed_features_for(user) -> set[str]:
    """The features ``user`` may actually use.

    One answer, read by both the display list and the enforcement gate, so the
    nav and the 403 can never disagree about what someone owns.

    Staff get everything, unconditionally and without a plan. They operate the
    product: a staff account that has to be comped a subscription before it can
    reproduce a customer's bug is a support burden, not a security boundary, and
    ``has_paid_access`` already exempts them from the billing half of the gate —
    this makes the feature half agree.
    """
    # Deliberately duck-typed: the enforcement path is handed whatever the
    # credential carries — a real User, or a lightweight principal that only
    # promises ``.tier``. Requiring ``is_authenticated`` here would silently
    # empty the set for those callers and 403 a request that should pass. The
    # anonymous case is handled where it can actually occur, in features_for.
    if user is None:
        return set()
    if getattr(user, "is_staff", False):
        return set(ALL_FEATURES)
    return set(FEATURES_BY_TIER.get(getattr(user, "tier", None), set()))


def features_for(user) -> list[str]:
    """The feature strings this user may use, sorted.

    Display-only — served by ``/api/auth/me`` so the SPA can hide nav entries
    for products the user has no plan for. Every endpoint still enforces its own
    gate server-side; a stale or forged list buys nothing."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    return sorted(allowed_features_for(user))


@dataclass
class RateLimitDecision:
    allowed: bool
    remaining: int | None
    reset_at_epoch: int


class ApiKeyAuth(APIKeyHeader):
    """Bearer-style auth via the ``X-API-Key`` header.

    Returning ``None`` from ``authenticate`` makes Ninja respond 401, which
    is what we want — never reveal whether a prefix exists."""

    param_name = "X-API-Key"

    def authenticate(self, request, key):
        if not key:
            return None
        api_key = verify_key(key)
        if api_key is None:
            return None
        # Update last_used_at lazily — once per minute is plenty and avoids
        # writing on every request. The model field has no index that
        # matters for hot-path latency.
        if (
            api_key.last_used_at is None
            or (timezone.now() - api_key.last_used_at).total_seconds() > 60
        ):
            APIKey.objects.filter(pk=api_key.pk).update(
                last_used_at=timezone.now()
            )
        return api_key


api_key_auth = ApiKeyAuth()


def require_feature_for_user(user, feature: str) -> None:
    """Raise 402/403 if ``user``'s plan doesn't include ``feature``.

    The gate itself, expressed in terms of the user — because the caller is not
    always an API key any more. ``/api/edms`` accepts three credential shapes
    (OAuth Bearer from the extension, ``X-API-Key``, session cookie from the
    SPA) and all three must land on exactly this policy; a gate that only knew
    how to read an ``APIKey`` row would have meant a second, drifting copy for
    the other two.
    """
    from apps.tenancy.services import has_paid_access

    if not has_paid_access(user):
        raise HttpError(
            402,
            "An active plan is required to use the API. Start your free trial "
            "at Account → Billing in the app.",
        )
    if feature not in allowed_features_for(user):
        raise HttpError(
            403,
            f"Feature '{feature}' is not available on the {user.tier} tier.",
        )


def require_feature(api_key: APIKey, feature: str) -> None:
    """Raise 403 if ``api_key``'s tier doesn't include ``feature``.

    With ``BILLING_REQUIRE_PAID`` on there is no free tier at all: a free-tier
    key gets 402 for every feature (the FEATURES_BY_TIER free set only exists
    for the beta era). One chokepoint covers both headless surfaces — the REST
    ``X-API-Key`` routes and MCP (apps/mcp_server/gating.py calls this).
    """
    require_feature_for_user(api_key.user, feature)


def check_rate_limit(api_key: APIKey) -> RateLimitDecision:
    """Per-key daily quota. Returns the decision; the caller decides what to
    do with it (we raise 429 from the dependency, but tests poke this
    function directly)."""

    quota = TIER_DAILY_QUOTA.get(api_key.user.tier)
    if quota is None:
        # Unlimited tier — still report a synthetic remaining for headers.
        return RateLimitDecision(allowed=True, remaining=None, reset_at_epoch=0)

    # Day-bucket key. Resets at the next UTC midnight; good enough for
    # quota accounting and easy to reason about in tests.
    now = timezone.now()
    day_key = now.strftime("%Y-%m-%d")
    cache_key = f"ratelimit:apikey:{api_key.pk}:{day_key}"

    # incr() is atomic in the cache backend; we initialize to 0 if missing.
    try:
        used = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=86_400)
        used = 1

    midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                + timezone.timedelta(days=1))
    reset_at_epoch = int(time.mktime(midnight.timetuple()))

    return RateLimitDecision(
        allowed=used <= quota,
        remaining=max(quota - used, 0),
        reset_at_epoch=reset_at_epoch,
    )


def enforce_rate_limit(api_key: APIKey) -> RateLimitDecision:
    """Check the limit and raise 429 if exceeded. Returns the decision so
    callers can attach quota headers to a successful response."""
    decision = check_rate_limit(api_key)
    if not decision.allowed:
        raise HttpError(
            429,
            f"Daily quota exceeded for tier '{api_key.user.tier}'. "
            f"Resets at {decision.reset_at_epoch} (unix epoch).",
        )
    return decision
