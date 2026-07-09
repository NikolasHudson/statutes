"""Minimal CourtListener REST API v4 client (stdlib only).

Used for small samples and the ongoing incremental updates — the historical
backfill uses the bulk CSVs instead. The ``/search/`` endpoint is open but the
detail endpoints require a free token; we send it on every request. A fresh
token is rate-limited (5/min, 50/hr, 125/day), so every call retries with
backoff on HTTP 429.

List queries that join through ``docket → court`` are slow on CL's side (an
~1-month ``date_created`` window was measured at ~83 s), so the read timeout
is generous and timeouts/5xx retry like 429s. Never request ``count=on`` —
in v4 the count is a lazily-computed separate URL and it times out on these
filtered queries.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

BASE = "https://www.courtlistener.com/api/rest/v4"
_UA = "iowa-statutes-caselaw-sampler"
_TIMEOUT = 180
# Sustained request spacing that stays under the 5/min throttle window.
_PACE_SECONDS = 13.0
# Total time one call may spend sleeping on 429s. 90 min outlasts an exhausted
# 50/hr window; a blown 125/day budget aborts instead of stalling until reset.
_MAX_THROTTLE_SLEEP = 5400
_SINGLE_THROTTLE_SLEEP = 3700  # never trust one Retry-After past ~an hour


class CLClient:
    def __init__(self, token: str, *, max_retries: int = 6, timeout: int = _TIMEOUT,
                 pace_seconds: float = _PACE_SECONDS):
        if not token:
            raise ValueError("CourtListener API token required")
        self.token = token
        self.max_retries = max_retries
        self.timeout = timeout
        self.pace_seconds = pace_seconds
        self._last_request = 0.0

    def _pace(self) -> None:
        wait = self._last_request + self.pace_seconds - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(
            url, headers={"Authorization": f"Token {self.token}", "User-Agent": _UA}
        )
        errors = 0
        throttle_slept = 0.0
        while True:
            self._pace()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    # Throttling is a time budget, not a retry count: an
                    # exhausted hourly window needs to be slept out, however
                    # many 429s that takes.
                    ra = exc.headers.get("Retry-After")
                    wait = min(int(ra) if ra and ra.isdigit() else 60,
                               _SINGLE_THROTTLE_SLEEP)
                    if throttle_slept + wait > _MAX_THROTTLE_SLEEP:
                        raise RuntimeError(
                            f"rate-limited beyond {_MAX_THROTTLE_SLEEP}s budget "
                            f"(daily quota likely exhausted): {exc}"
                        ) from exc
                    time.sleep(wait)
                    throttle_slept += wait
                    continue
                errors += 1
                if exc.code >= 500 and errors < self.max_retries:
                    time.sleep(5 * errors)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as exc:
                # Read timeout on a slow filtered query, connect failure, etc.
                errors += 1
                if errors >= self.max_retries:
                    raise RuntimeError(
                        f"giving up after {self.max_retries} retries: {exc}"
                    ) from exc
                time.sleep(5 * errors)

    def paginate(self, path: str, params: dict) -> Iterator[dict]:
        """Yield every result of a filtered list query, following v4 cursor
        pagination."""
        url = f"{BASE}/{path}/?{urllib.parse.urlencode(params)}"
        while url:
            page = self._get(url)
            yield from (page.get("results") or [])
            url = page.get("next")

    # -- incremental-update sweeps (date_created = when CL added the row, NOT
    # -- date_filed: CL harvests cases late, so a filed-date cursor would skip
    # -- them). ``docket__court`` is exact-only (``__in`` is a 400), hence one
    # -- sweep per court.

    def clusters_since(self, court: str, since_iso: str) -> Iterator[dict]:
        return self.paginate("clusters", {
            "docket__court": court,
            "date_created__gte": since_iso,
            "order_by": "date_created",
        })

    def opinions_since(self, court: str, since_iso: str) -> Iterator[dict]:
        """Full-text opinions in bulk — one paged sweep instead of one request
        per cluster, to stay inside the 125/day budget on release days."""
        return self.paginate("opinions", {
            "cluster__docket__court": court,
            "date_created__gte": since_iso,
            "order_by": "date_created",
        })

    def dockets_since(self, court: str, since_iso: str) -> Iterator[dict]:
        return self.paginate("dockets", {
            "court": court,
            "date_created__gte": since_iso,
            "order_by": "date_created",
        })

    def get_cluster(self, cluster_id: int) -> dict:
        return self._get(f"{BASE}/clusters/{cluster_id}/")

    def get_docket(self, docket_id: int) -> dict:
        return self._get(f"{BASE}/dockets/{docket_id}/")

    # -- sample/smoke-test helpers -------------------------------------------

    def search_clusters(self, court: str, *, limit: int,
                        order_by: str = "dateFiled desc") -> list[dict]:
        """Return up to ``limit`` search hits (each a cluster) for a court,
        following pagination."""
        out: list[dict] = []
        for hit in self.paginate("search", {
            "type": "o", "court": court, "order_by": order_by, "page_size": 20,
        }):
            out.append(hit)
            if len(out) >= limit:
                break
        return out

    def opinions_for_cluster(self, cluster_id: int) -> Iterator[dict]:
        """Yield every opinion (full text) for a cluster, following pagination."""
        return self.paginate("opinions", {"cluster": cluster_id})
