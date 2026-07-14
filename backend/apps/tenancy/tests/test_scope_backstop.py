"""Fail-closed backstop for the host-scoped corpus (DOMAIN_AND_BRAND_PLAN #9).

Search / browse / verify / research do not yet clamp their scope to
``request.product``, so on a white-label front door they would serve the whole
flagship corpus. ProductResolutionMiddleware refuses those prefixes outright
whenever a product resolves, turning the fail-OPEN break into fail-closed —
while leaving the flagship (product=None) and non-corpus endpoints untouched.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.tenancy.models import Product


@override_settings(ALLOWED_HOSTS=["clerk.testserver", "testserver"])
class ScopeBackstopTests(TestCase):
    def setUp(self):
        Product.objects.create(
            slug="iowa-ethics-procedure",
            name="Iowa Ethics & Procedure",
            hostname="clerk.testserver",
            allowed_source_slugs=["iowa-court-rules"],
        )

    def test_scoped_host_is_refused_on_unclamped_corpus_endpoints(self):
        for path in (
            "/api/search",
            "/api/browse/sources",
            "/api/research/search",
            "/api/verify/document",
        ):
            resp = self.client.get(path, headers={"host": "clerk.testserver"})
            self.assertEqual(resp.status_code, 403, f"{path} should be refused")

    def test_flagship_host_is_not_blocked_by_the_backstop(self):
        # product is None on the flagship apex, so the backstop never fires: the
        # public source list answers on its own terms (200), not the 403 body.
        resp = self.client.get("/api/browse/sources", headers={"host": "testserver"})
        self.assertEqual(resp.status_code, 200)

    def test_scoped_host_still_reaches_non_corpus_endpoints(self):
        # A white-label host must still log in / theme / bill — only the
        # corpus readers are gated, not the whole API.
        resp = self.client.get("/api/branding", headers={"host": "clerk.testserver"})
        self.assertNotEqual(resp.status_code, 403)
