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
from django.http import HttpResponseNotFound, JsonResponse

# Container probe path (statutes service health_check.http_path in .do/app.yaml).
_HEALTH_PATHS = frozenset({"/api/health", "/api/health/"})

# Returned by _resolve() when PRODUCT_HOST_STRICT refuses a Host. Must be a
# distinct sentinel: None already MEANS the flagship, which is exactly the
# outcome strict mode exists to withhold.
_UNKNOWN_HOST = object()


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

    **Failing closed on an unknown host** (``PRODUCT_HOST_STRICT``, default OFF).
    Because an unmatched host resolves to the flagship, a white-label front door
    that reaches DNS + ALLOWED_HOSTS *before* its Product row exists would serve
    the whole corpus with the scope lock gone. Strict mode refuses any host that
    is neither a Product ``hostname`` nor a ``FLAGSHIP_HOSTS`` entry. It is opt-in
    because enabling it with an incomplete FLAGSHIP_HOSTS locks out the flagship
    itself: every legitimate non-product Host — corpus.nick.law, the apex, dev's
    localhost/127.0.0.1, and any pod-IP request that isn't the health probe
    (``/api/health`` never reaches here; HealthCheckMiddleware answers it first) —
    must be enumerated there. Default OFF keeps today's behaviour byte-identical;
    turn it on, with FLAGSHIP_HOSTS populated, when the first white-label host
    launches.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        product = self._resolve(request)
        if product is _UNKNOWN_HOST:
            return HttpResponseNotFound("Unknown host.")
        request.product = product
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
        # Product.save() lowercases hostname, so this is an exact match on the
        # unique index — one indexed lookup, pre-auth, read-only.
        product = Product.objects.filter(hostname=host).first()
        if product is not None:
            return product

        if _flagship_host_is_open(host):
            return None
        return _UNKNOWN_HOST


def _flagship_host_is_open(host: str) -> bool:
    """May ``host`` fall through to the unlocked flagship (product=None)?

    Read via getattr so both settings are optional: absent means OFF, which is
    today's behaviour. Read per-request (not at import) so a deployment can flip
    the switch, and so override_settings works in tests.
    """
    if not getattr(settings, "PRODUCT_HOST_STRICT", False):
        return True
    return host in {
        h.strip().lower()
        for h in (getattr(settings, "FLAGSHIP_HOSTS", None) or [])
        if h and h.strip()
    }
