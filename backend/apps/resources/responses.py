"""One helper, so every resources route answers with the same cache policy.

These responses are per-user work product over data that identifies people by
name and address. ``private, no-store`` keeps them out of the Cloudflare edge
cache (which fronts ``/api/browse/*``), out of shared proxies, and out of the
browser's disk cache — the same rule ``/api/research/search`` applies.
"""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse


def no_store(payload: dict, status: int = 200) -> HttpResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "private, no-store"
    return response
