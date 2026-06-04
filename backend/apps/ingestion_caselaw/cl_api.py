"""Minimal CourtListener REST API v4 client (stdlib only).

Used for small samples and (later) ongoing incremental updates — the historical
backfill uses the bulk CSVs instead. The ``/search/`` endpoint is open but the
detail endpoints require a free token; we send it on every request. A fresh
token is rate-limited, so every call retries with backoff on HTTP 429.
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


class CLClient:
    def __init__(self, token: str, *, max_retries: int = 6):
        if not token:
            raise ValueError("CourtListener API token required")
        self.token = token
        self.max_retries = max_retries

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(
            url, headers={"Authorization": f"Token {self.token}", "User-Agent": _UA}
        )
        last_exc = None
        for _ in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code == 429:
                    wait = exc.headers.get("Retry-After")
                    time.sleep(min(int(wait) if wait and wait.isdigit() else 5, 65))
                    continue
                raise
        raise RuntimeError(f"giving up after {self.max_retries} retries: {last_exc}")

    def search_clusters(self, court: str, *, limit: int,
                        order_by: str = "dateFiled desc") -> list[dict]:
        """Return up to ``limit`` search hits (each a cluster) for a court,
        following pagination."""
        params = urllib.parse.urlencode(
            {"type": "o", "court": court, "order_by": order_by, "page_size": 20}
        )
        url = f"{BASE}/search/?{params}"
        out: list[dict] = []
        while url and len(out) < limit:
            page = self._get(url)
            out.extend(page.get("results") or [])
            url = page.get("next")
        return out[:limit]

    def opinions_for_cluster(self, cluster_id: int) -> Iterator[dict]:
        """Yield every opinion (full text) for a cluster, following pagination."""
        url = f"{BASE}/opinions/?{urllib.parse.urlencode({'cluster': cluster_id})}"
        while url:
            page = self._get(url)
            yield from (page.get("results") or [])
            url = page.get("next")
