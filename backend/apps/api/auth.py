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
FEATURES_BY_TIER: dict[str, set[str]] = {
    Tier.FREE: {"lookup", "search"},
    Tier.SOLO: {
        "lookup", "search", "history", "at_date", "cross_refs",
        "definitions", "amendments", "validate",
    },
    Tier.FIRM: {
        "lookup", "search", "history", "at_date", "cross_refs",
        "definitions", "amendments", "validate",
    },
    Tier.CUSTOM: {
        "lookup", "search", "history", "at_date", "cross_refs",
        "definitions", "amendments", "validate",
    },
}


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


def require_feature(api_key: APIKey, feature: str) -> None:
    """Raise 403 if ``api_key``'s tier doesn't include ``feature``."""
    allowed = FEATURES_BY_TIER.get(api_key.user.tier, set())
    if feature not in allowed:
        raise HttpError(
            403,
            f"Feature '{feature}' is not available on the {api_key.user.tier} tier.",
        )


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
