"""Per-connection Postgres session setup for the corpus app.

pgvector's HNSW recall is governed by ``hnsw.ef_search`` — the search-time beam
width. Its default of 40 is too narrow for the caselaw chunk index (~500K
vectors): the ``eval_caselaw`` harness found cases that rank #1/#2 by cosine
silently dropping out of the result set entirely at 40, recovered in full at 200
(see ``HNSW_EF_SEARCH`` in ``services.search``). We raise it once per connection,
and on pgvector >= 0.8 also enable ``hnsw.iterative_scan`` so a selective metadata
filter (court / precedential status) can't make a vector query silently under-return.

Why a connection signal and not ``SET LOCAL`` inside the retriever: pgvector
registers the ``hnsw.ef_search`` GUC only after its shared module is loaded into
the backend, so the first ``SET`` on a fresh connection fails with "unrecognized
configuration parameter" until a vector op has run. Loading the module once here
(a trivial ``::vector`` cast) and then issuing a session-level ``SET`` makes the
setting apply to every later query on the connection with no per-query cost and no
transaction juggling. Anything going wrong here must never block DB access, so
failures are logged and swallowed — search simply falls back to the ef=40 default.
"""

from __future__ import annotations

import logging

from django.db.backends.signals import connection_created
from django.dispatch import receiver

log = logging.getLogger(__name__)


@receiver(connection_created)
def configure_pgvector_session(sender, connection, **kwargs):
    if connection.vendor != "postgresql":
        return
    from apps.corpus.services.search import (
        HNSW_EF_SEARCH,
        HNSW_ITERATIVE_SCAN,
        HNSW_MAX_SCAN_TUPLES,
    )

    if not HNSW_EF_SEARCH:
        return
    try:
        with connection.cursor() as cur:
            # The extension may not exist yet on a brand-new database — e.g. the
            # connection opened during test-DB creation, before the 0001_extensions
            # migration runs, or a connection to the maintenance DB. Skip quietly.
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
            if cur.fetchone() is None:
                return
            # Force the pgvector module to load (registers the GUCs), then widen
            # the search beam for the rest of this connection's life.
            cur.execute("SELECT '[1]'::vector;")
            cur.execute("SET hnsw.ef_search = %s;", [HNSW_EF_SEARCH])
            # Filtered-ANN completeness (pgvector >= 0.8). Isolated so an older
            # pgvector — where these GUCs don't exist — keeps the ef_search widening
            # above instead of losing the whole session setup to one failed SET.
            if HNSW_ITERATIVE_SCAN:
                try:
                    cur.execute(
                        "SET hnsw.iterative_scan = %s;", [HNSW_ITERATIVE_SCAN]
                    )
                    cur.execute(
                        "SET hnsw.max_scan_tuples = %s;", [HNSW_MAX_SCAN_TUPLES]
                    )
                except Exception:  # noqa: BLE001 — pre-0.8 pgvector; keep ef_search
                    log.warning(
                        "could not set hnsw.iterative_scan (pgvector < 0.8?); "
                        "filtered vector queries may under-return",
                        exc_info=True,
                    )
    except Exception:  # noqa: BLE001 — never let session tuning break the connection
        log.warning(
            "could not set hnsw.ef_search=%s; using pgvector default",
            HNSW_EF_SEARCH,
            exc_info=True,
        )
