"""Project-level middleware.

HealthCheckMiddleware answers the container health probe before Django's
host/SSL middleware runs. App Platform's HTTP health check hits the container
by pod IP (or localhost) over plain HTTP, so once ALLOWED_HOSTS was scoped to
corpus.nick.law the probe started getting 400 DisallowedHost (the Host check in
get_host() fires first), and SECURE_SSL_REDIRECT would otherwise 301 it.

Short-circuiting the health path here — as the FIRST middleware, ahead of
SecurityMiddleware/CommonMiddleware — lets the internal probe get a 200 without
relaxing ALLOWED_HOSTS or SECURE_SSL_REDIRECT for real traffic. Real edge
requests (Host: corpus.nick.law, X-Forwarded-Proto: https) are unaffected and
still reach the ninja /api/health view; this just guarantees the IP-addressed
probe never trips host validation. Keep the payload in sync with that view
(apps/api/api.py: health).
"""

from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse

# Container probe path (statutes service health_check.http_path in .do/app.yaml).
_HEALTH_PATHS = frozenset({"/api/health", "/api/health/"})


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in _HEALTH_PATHS:
            return JsonResponse({"status": "ok"})
        return self.get_response(request)


class ProductResolutionMiddleware:
    """Resolve the scoped PRODUCT from the request Host and attach it as
    ``request.product`` (a :class:`apps.tenancy.models.Product` or ``None``).

    A host that matches a product's ``hostname`` (e.g. ``clerk.<domain>``) is a
    *locked* front door — that one product, scope-fixed. A host that matches none
    (the flagship ``app.<domain>`` / the apex) resolves to ``None``: the
    *unlocked* experience, where the user sees everything they're entitled to.

    This only answers "which product front door is this host?" — it does NOT
    decide access. Entitlement (apps.tenancy.entitlement.is_entitled) is the gate,
    enforced at the endpoint. Read-only, one indexed lookup, and pre-auth so
    ``GET /api/branding`` can theme the login screen before anyone logs in.

    In DEBUG only, an ``X-Product-Slug`` header (or ``?product=`` query param)
    overrides host resolution, so a pinned product can be exercised without DNS.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.product = self._resolve(request)
        return self.get_response(request)

    @staticmethod
    def _resolve(request):
        # Imported lazily so the app registry is ready and migrations can run.
        from apps.tenancy.models import Product

        if settings.DEBUG:
            slug = request.headers.get("X-Product-Slug") or request.GET.get("product")
            if slug:
                return Product.objects.filter(slug=slug).first()

        host = request.get_host().split(":")[0].lower()
        return Product.objects.filter(hostname=host).first()
