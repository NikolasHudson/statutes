"""Auth + rate limit unit tests, separate from the route tests so each
can stay focused on one concern."""

from __future__ import annotations

from django.core.cache import cache
from django.test import RequestFactory, TestCase, tag
from ninja.errors import HttpError

from apps.accounts.models import Tier
from apps.api.auth import (
    ApiKeyAuth,
    check_rate_limit,
    enforce_rate_limit,
    require_feature,
)

from ._factories import make_api_key, make_user


@tag("postgres")
class ApiKeyAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(tier=Tier.SOLO)
        self.api_key, self.raw = make_api_key(self.user)
        self.auth = ApiKeyAuth()
        self.rf = RequestFactory()

    def test_valid_key_returns_apikey(self):
        request = self.rf.get("/")
        result = self.auth.authenticate(request, self.raw)
        self.assertEqual(result.pk, self.api_key.pk)

    def test_invalid_key_returns_none(self):
        request = self.rf.get("/")
        self.assertIsNone(self.auth.authenticate(request, "garbage"))

    def test_revoked_key_rejected(self):
        from django.utils import timezone

        self.api_key.revoked_at = timezone.now()
        self.api_key.save()
        request = self.rf.get("/")
        self.assertIsNone(self.auth.authenticate(request, self.raw))


@tag("postgres")
class TierGatingTests(TestCase):
    def setUp(self):
        self.free = make_user(email="f@example.com", tier=Tier.FREE)
        self.solo = make_user(email="s@example.com", tier=Tier.SOLO)
        self.free_key, _ = make_api_key(self.free)
        self.solo_key, _ = make_api_key(self.solo)

    def test_free_tier_blocked_from_history(self):
        with self.assertRaises(HttpError) as ctx:
            require_feature(self.free_key, "history")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_free_tier_allowed_lookup(self):
        # Should not raise.
        require_feature(self.free_key, "lookup")

    def test_solo_tier_can_use_history(self):
        require_feature(self.solo_key, "history")


@tag("postgres")
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(tier=Tier.FREE)
        self.api_key, _ = make_api_key(self.user)

    def test_first_call_is_allowed(self):
        decision = check_rate_limit(self.api_key)
        self.assertTrue(decision.allowed)
        self.assertGreaterEqual((decision.remaining or 0), 0)

    def test_quota_exhausts_after_repeated_calls(self):
        # Free tier quota is 200 — burn through it.
        from apps.api.auth import TIER_DAILY_QUOTA

        quota = TIER_DAILY_QUOTA[Tier.FREE]
        for _ in range(quota):
            check_rate_limit(self.api_key)
        # The next call should fail.
        with self.assertRaises(HttpError) as ctx:
            enforce_rate_limit(self.api_key)
        self.assertEqual(ctx.exception.status_code, 429)
