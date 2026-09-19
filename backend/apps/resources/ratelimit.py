"""Per-user request throttle for the resources search routes.

``apps.api.auth.enforce_rate_limit`` is API-key shaped (it reads a tier quota
off an ``APIKey`` row); these routes are session-authenticated, so this is the
same cache-counter technique keyed on the user instead.

Why any throttle at all: the registry lists registered agents, and a registered
agent is often a private individual at a home address. There is deliberately no
bulk export, so a scraper's only route is the paginated search — this makes
that slow enough to be pointless without inconveniencing a person doing
research.
"""

from __future__ import annotations

import time

from django.core.cache import cache
from ninja.errors import HttpError

# 120 requests per 10 minutes per user, per route family. A human searching
# hard does a few dozen; a scraper walking pages hits this in under a minute.
RATE_LIMIT = 120
RATE_WINDOW_SECONDS = 600


def enforce_user_rate_limit(
    user, bucket: str, *, limit: int = RATE_LIMIT, window: int = RATE_WINDOW_SECONDS
) -> None:
    """Raise 429 once ``user`` exceeds ``limit`` calls to ``bucket`` in the
    current fixed window."""
    user_id = getattr(user, "pk", None)
    if user_id is None:
        return
    slot = int(time.time() // window)
    key = f"ratelimit:resources:{bucket}:{user_id}:{slot}"
    try:
        used = cache.incr(key)
    except ValueError:
        # incr() on a missing key raises; seed it. A tiny race here can let a
        # couple of extra requests through, which is fine for an abuse control.
        cache.set(key, 1, timeout=window)
        used = 1
    if used > limit:
        retry_after = window - int(time.time() % window)
        raise HttpError(
            429,
            f"Too many resource searches. Try again in {retry_after} seconds.",
        )
