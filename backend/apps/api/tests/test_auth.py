"""Auth + rate limit unit tests, separate from the route tests so each
can stay focused on one concern."""

from __future__ import annotations

from django.core.cache import cache
from django.test import RequestFactory, TestCase, tag
from ninja.errors import HttpError

from apps.accounts.models import Tier
from apps.api.auth import (
    ALL_FEATURES,
    ApiKeyAuth,
    check_rate_limit,
    enforce_rate_limit,
    features_for,
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

    def test_staff_get_every_feature_without_a_plan(self):
        """Staff operate the product. Requiring a comped subscription before a
        staff account can reproduce a customer's bug is a support burden, not a
        security boundary — and ``has_paid_access`` already exempts them from
        the billing half of the gate, so the feature half has to agree."""
        staff = make_user(email="staff@example.com", tier=Tier.FREE)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        staff_key, _ = make_api_key(staff)
        self.assertEqual(set(features_for(staff)), set(ALL_FEATURES))
        for feature in sorted(ALL_FEATURES):
            require_feature(staff_key, feature)  # must not raise

    def test_non_staff_free_tier_does_not_get_edms(self):
        """The paid-feature decision, pinned: EDMSpro is not a free feature."""
        self.assertNotIn("edms", features_for(self.free))
        with self.assertRaises(HttpError) as ctx:
            require_feature(self.free_key, "edms")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_features_list_and_gate_cannot_disagree(self):
        """/api/auth/me drives the SPA nav; the gate drives the 403. They read
        the same function so a user can never see an entry they cannot use."""
        for user, key in ((self.free, self.free_key), (self.solo, self.solo_key)):
            listed = set(features_for(user))
            for feature in sorted(ALL_FEATURES):
                if feature in listed:
                    require_feature(key, feature)
                else:
                    with self.assertRaises(HttpError):
                        require_feature(key, feature)


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
