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
