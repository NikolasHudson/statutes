"""Origin-lock middleware contract (core/middleware.py:OriginLockMiddleware).

The Cloudflare Transform Rule stamps X-Origin-Lock on every proxied request;
the middleware 403s edge traffic without it so the public *.ondigitalocean.app
origin can't be used to bypass the WAF/rate-limit/CF-Connecting-IP controls.
TestCase (not SimpleTestCase): pass-through requests continue down the stack
to ProductResolutionMiddleware, whose host lookup queries Product.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

# A path no URLConf entry matches: a pass-through is provable as a 404 (the
# request reached routing) vs the middleware's 403, with no view/DB coupling.
_UNROUTED = "/api/__origin_lock_probe__"


class OriginLockTests(TestCase):
    def test_inert_when_secret_unset(self):
        # Default settings: ORIGIN_LOCK_SECRET is "" — dev/local/tests must be
        # unaffected, so the request passes through to routing (404).
        self.assertEqual(self.client.get(_UNROUTED).status_code, 404)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_missing_header_is_rejected(self):
        self.assertEqual(self.client.get(_UNROUTED).status_code, 403)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_wrong_header_is_rejected(self):
        response = self.client.get(_UNROUTED, headers={"X-Origin-Lock": "nope"})
        self.assertEqual(response.status_code, 403)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_correct_header_passes_through(self):
        response = self.client.get(
            _UNROUTED, headers={"X-Origin-Lock": "sekrit"}
        )
        self.assertEqual(response.status_code, 404)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_health_probe_stays_exempt(self):
        # App Platform probes /api/health directly (no Cloudflare, no header);
        # HealthCheckMiddleware answers it before the lock runs.
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    @override_settings(ORIGIN_LOCK_SECRET="sekrit")
    def test_locked_request_never_reaches_views(self):
        # A real routed path is refused identically — the 403 comes from the
        # middleware, before auth/CSRF/routing side effects.
        response = self.client.post("/api/auth/login", data={})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content, b"Forbidden.")
