"""HTTP surface for the Iowa SOS business-entity registry.

Mounted by ``apps.resources.api`` under ``/api/resources/iowa-business-entities``.
Every route is session-authenticated and paywalled — see the module docstring
there for why this dataset in particular never gets an anonymous route.

Search shape: a candidate pool is taken with an index-backed predicate and a
LIMIT, and only then sorted. That is the same bargain ``/api/browse/suggest``
strikes (and for the same reason): a generic query like "smith" matches tens of
thousands of rows at the same similarity, and sorting all of them costs
hundreds of milliseconds to produce an ordering no more useful than sorting an
arbitrary thousand of them.
"""

from __future__ import annotations

import datetime as dt
import re

from django.core.cache import cache
from django.db import connection
from ninja import Router
from ninja.errors import HttpError

from apps.api.paywall import require_paid_access
from apps.api.session_auth import session_auth
from apps.resources.normalize import normalize_name
from apps.resources.ratelimit import enforce_user_rate_limit
from apps.resources.responses import no_store

from .models import BusinessEntity

sos_router = Router()

LIVE = BusinessEntity._meta.db_table

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 50

# How many rows a predicate may contribute before we stop looking. Also the
# ceiling on the reported total: a UI that says "1,000+" is honest, and a
# count(*) over a fuzzy match set is not cheap.
CANDIDATE_POOL = 1000

# pg_trgm indexes runs of letters and digits; a query with no two-character
# alphanumeric word has no trigrams at all, so `<%` could not use the GIN index
# and would sequential-scan the table. Fall back to prefix matching there.
_HAS_WORD_RE = re.compile(r"[A-Za-z0-9]{2,}")
_DIGITS_RE = re.compile(r"^\d{1,12}$")
_CORP_NUMBER_RE = re.compile(r"^[A-Za-z0-9-]{1,12}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

MAX_QUERY_CHARS = 120

TYPES_CACHE_KEY = "resources:sos:types:v1"
TYPES_CACHE_SECONDS = 3600


def _clean(value: str | None) -> str:
    text = _CONTROL_CHARS_RE.sub(" ", value or "")
    return " ".join(text.split())[:MAX_QUERY_CHARS]


def _gate(request, bucket: str | None = None):
    require_paid_access(request.auth)
    if bucket:
        enforce_user_rate_limit(request.auth, bucket)


def _dataset():
    # Imported lazily: apps.resources.models imports this package's models, so
    # a module-level import here would be circular.
    from apps.resources.models import Dataset

    return Dataset.objects.filter(slug="iowa-business-entities").first()


def _as_of() -> dt.date | dt.datetime | None:
    ds = _dataset()
    return ds.as_of() if ds else None


def _as_of_iso() -> str | None:
    value = _as_of()
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    return value.isoformat()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class _Query:
    """Assembles the candidate SQL for one search. Each predicate is kept in
    its own UNION branch so the planner gets a single indexable condition per
    scan instead of an OR it may decline to use an index for."""

    def __init__(
        self,
        *,
        q: str,
        agent: str,
        city: str,
        zip_code: str,
        entity_type: str,
        include_inactive: bool,
    ):
        self.params: dict[str, object] = {"pool": CANDIDATE_POOL}
        self.filters: list[str] = []
        if not include_inactive:
            self.filters.append("is_active")
        if city:
            self.filters.append("(ra_city = %(city)s OR ho_city = %(city)s)")
            self.params["city"] = city.upper()
        if zip_code:
            self.filters.append("(ra_zip = %(zip)s OR ho_zip = %(zip)s)")
            self.params["zip"] = zip_code
        if entity_type:
            self.filters.append("entity_type = %(etype)s")
            self.params["etype"] = entity_type.upper()

        self.qn = normalize_name(q) if q else ""
        self.an = normalize_name(agent) if agent else ""
        if self.qn:
            self.params["qn"] = self.qn
            self.params["qprefix"] = f"{self.qn}%"
        if self.an:
            self.params["an"] = self.an
            self.params["aprefix"] = f"{self.an}%"

    @property
    def _where(self) -> str:
        return " AND ".join(self.filters) if self.filters else "TRUE"

    def _branch(self, predicate: str) -> str:
        return (
            "(SELECT id, legal_name, name_normalized, agent_normalized "
            f"FROM {LIVE} WHERE {self._where} AND {predicate} "
            "LIMIT %(pool)s)"
        )

    def _candidates(self) -> tuple[str, str]:
        """(candidate CTE body, ORDER BY clause)."""
        branches: list[str] = []
        if self.qn:
            branches.append(self._branch("name_normalized LIKE %(qprefix)s"))
            if _HAS_WORD_RE.search(self.qn):
                branches.append(self._branch("%(qn)s <%% name_normalized"))
        if self.an:
            branches.append(self._branch("agent_normalized LIKE %(aprefix)s"))
            if _HAS_WORD_RE.search(self.an):
                branches.append(self._branch("%(an)s <%% agent_normalized"))

        if branches:
            return "\nUNION\n".join(branches), self._fuzzy_order()
        # Filter-only search (city / zip / type): a plain indexed scan,
        # alphabetical, capped at the same pool so the count stays cheap.
        return (
            "(SELECT id, legal_name, name_normalized, agent_normalized "
            f"FROM {LIVE} WHERE {self._where} ORDER BY legal_name "
            "LIMIT %(pool)s)",
            "legal_name, id",
        )

    def page_sql(self) -> str:
        candidates, order = self._candidates()
        return (
            f"WITH cand AS (\n{candidates}\n)\n"
            "SELECT id, count(*) OVER () AS total FROM cand\n"
            f"ORDER BY {order}\n"
            "LIMIT %(limit)s OFFSET %(offset)s"
        )

    def count_sql(self) -> str:
        """Only used for a page past the end, where the page query returns no
        rows and therefore no window-function total."""
        candidates, _ = self._candidates()
        return f"WITH cand AS (\n{candidates}\n)\nSELECT count(*) FROM cand"

    def _fuzzy_order(self) -> str:
        """Exact normalized match first, then prefix, then fuzzy — within each
        bucket by similarity, then alphabetically so paging is stable."""
        keys: list[str] = []
        if self.qn:
            keys.append(
                "(CASE WHEN name_normalized = %(qn)s THEN 0 "
                "WHEN name_normalized LIKE %(qprefix)s THEN 1 ELSE 2 END)"
            )
        if self.an:
            keys.append(
                "(CASE WHEN agent_normalized = %(an)s THEN 0 "
                "WHEN agent_normalized LIKE %(aprefix)s THEN 1 ELSE 2 END)"
            )
        if self.qn:
            keys.append("word_similarity(%(qn)s, name_normalized) DESC")
        if self.an:
            keys.append("word_similarity(%(an)s, agent_normalized) DESC")
        keys.append("legal_name")
        keys.append("id")
        return ", ".join(keys)


def _row_out(e: BusinessEntity) -> dict:
    return {
        "corp_number": e.corp_number,
        "legal_name": e.legal_name,
        "entity_type": e.entity_type,
        "effective_date": e.effective_date.isoformat() if e.effective_date else None,
        "registered_agent": e.registered_agent,
        "city": e.ra_city or e.ho_city,
        "state": e.ra_state or e.ho_state,
        "is_active": e.is_active,
        "deactivated_on": (
            e.deactivated_on.isoformat() if e.deactivated_on else None
        ),
    }


def _fetch_ordered(ids: list[int]) -> list[BusinessEntity]:
    by_id = BusinessEntity.objects.in_bulk(ids)
    return [by_id[i] for i in ids if i in by_id]


@sos_router.get("/search", auth=session_auth)
def search(
    request,
    q: str = "",
    agent: str = "",
    city: str = "",
    zip: str = "",  # noqa: A002 — the query-string name users expect
    type: str = "",  # noqa: A002 — ditto
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
):
    _gate(request, "search")

    q = _clean(q)
    agent = _clean(agent)
    city = _clean(city)
    zip_code = _clean(zip)
    entity_type = _clean(type)

    # No unfiltered listing: this is a registry of named people at named
    # addresses, and "show me everything" is not a research query.
    if not any((q, agent, city, zip_code)):
        raise HttpError(
            422,
            "Provide at least one of: q (name or corp number), agent, city, zip.",
        )

    page = max(1, page)
    page_size = max(1, min(page_size, PAGE_SIZE_MAX))
    offset = (page - 1) * page_size

    # A pure-digit query is a corp-number lookup. Pin the exact row on page 1
    # and let the same string go on to match names too (some do contain digits).
    pinned: BusinessEntity | None = None
    if _DIGITS_RE.match(q):
        pinned = BusinessEntity.objects.filter(corp_number=q).first()

    builder = _Query(
        q=q,
        agent=agent,
        city=city,
        zip_code=zip_code,
        entity_type=entity_type,
        include_inactive=include_inactive,
    )
    params = builder.params
    # The pinned row is prepended to page 1, so that page asks for one fewer
    # and every later page shifts its offset back by the same one.
    pin_offset = 1 if pinned else 0
    params["limit"] = max(0, page_size - pin_offset) if page == 1 else page_size
    params["offset"] = 0 if page == 1 else max(0, offset - pin_offset)

    ids: list[int] = []
    total = 0
    with connection.cursor() as cur:
        if params["limit"] > 0:
            cur.execute(builder.page_sql(), params)
            rows = cur.fetchall()
            ids = [r[0] for r in rows]
            total = rows[0][1] if rows else 0
        if not ids:
            # Page past the end (or a page-size of one taken by the pin): the
            # window function had no row to ride on, so count separately.
            cur.execute(builder.count_sql(), params)
            total = cur.fetchone()[0]

    results = [
        _row_out(e)
        for e in _fetch_ordered(ids)
        if pinned is None or e.pk != pinned.pk
    ]
    if pinned and page == 1:
        results.insert(0, _row_out(pinned))

    # The pinned row is dropped from the pool's rows above so it cannot be
    # listed twice. It can still be counted twice in the one degenerate case
    # where an entity's name normalizes to the digits that are also a corp
    # number, which nothing in the current data does.
    total_with_pin = total + (1 if pinned else 0)
    return no_store(
        {
            "query": q,
            "page": page,
            "page_size": page_size,
            "total": min(total_with_pin, CANDIDATE_POOL),
            # True when the pool filled: the UI should render "1,000+".
            "total_capped": total >= CANDIDATE_POOL,
            "as_of": _as_of_iso(),
            "results": results,
        }
    )


# ---------------------------------------------------------------------------
# Detail + reverse agent lookup + facet values
# ---------------------------------------------------------------------------


@sos_router.get("/entities/{corp_number}", auth=session_auth)
def entity_detail(request, corp_number: str):
    _gate(request)
    if not _CORP_NUMBER_RE.match(corp_number or ""):
        raise HttpError(404, "No such entity.")
    entity = BusinessEntity.objects.filter(corp_number=corp_number).first()
    if entity is None:
        raise HttpError(404, "No such entity.")

    # "Other entities with this registered agent": same normalized agent at the
    # same agent ZIP. The ZIP is what keeps two unrelated "JOHN SMITH"s apart;
    # it is a heuristic, and the UI says so.
    agent_entity_count = 0
    if entity.agent_normalized:
        agent_entity_count = (
            BusinessEntity.objects.filter(
                is_active=True,
                agent_normalized=entity.agent_normalized,
                ra_zip=entity.ra_zip,
            )
            .exclude(pk=entity.pk)
            .count()
        )

    payload = _row_out(entity)
    payload.update(
        {
            "name_normalized": entity.name_normalized,
            "registered_agent_address": {
                "address_1": entity.ra_address_1,
                "address_2": entity.ra_address_2,
                "city": entity.ra_city,
                "state": entity.ra_state,
                "zip": entity.ra_zip,
                "lat": entity.ra_lat,
                "lon": entity.ra_lon,
            },
            "home_office": entity.home_office,
            "home_office_address": {
                "address_1": entity.ho_address_1,
                "address_2": entity.ho_address_2,
                "city": entity.ho_city,
                "state": entity.ho_state,
                "zip": entity.ho_zip,
                "country": entity.ho_country,
                "lat": entity.ho_lat,
                "lon": entity.ho_lon,
            },
            "first_seen": entity.first_seen.isoformat(),
            "last_seen": entity.last_seen.isoformat(),
            "agent_entity_count": agent_entity_count,
            "as_of": _as_of_iso(),
        }
    )
    return no_store(payload)


@sos_router.get("/agents", auth=session_auth)
def agent_entities(
    request,
    name: str = "",
    zip: str = "",  # noqa: A002
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
):
    """Reverse lookup: everything a registered agent is listed on.

    Exact on the normalized agent name (this is reached from a detail page, so
    we already hold the agent's name as published), optionally narrowed by the
    agent ZIP to separate namesakes.
    """
    _gate(request, "agents")
    name_normalized = normalize_name(_clean(name))
    if not name_normalized:
        raise HttpError(422, "name is required.")

    page = max(1, page)
    page_size = max(1, min(page_size, PAGE_SIZE_MAX))
    offset = (page - 1) * page_size

    qs = BusinessEntity.objects.filter(
        is_active=True, agent_normalized=name_normalized
    )
    zip_code = _clean(zip)
    if zip_code:
        qs = qs.filter(ra_zip=zip_code)
    total = qs.count()
    rows = qs.order_by("legal_name", "id")[offset : offset + page_size]

    return no_store(
        {
            "agent": name,
            "zip": zip_code,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_capped": False,
            "as_of": _as_of_iso(),
            "results": [_row_out(e) for e in rows],
        }
    )


@sos_router.get("/types", auth=session_auth)
def entity_types(request):
    """Distinct entity types with active counts, for the search filter.

    Built from the data, never a hardcoded enum: the source carries 32 types
    today, down to single-digit tails like "MULTIPLE HOUSING ACT", and adds
    them without notice.
    """
    _gate(request)
    cached = cache.get(TYPES_CACHE_KEY)
    if cached is None:
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT entity_type, count(*) FROM {LIVE} "
                "WHERE is_active AND entity_type <> '' "
                "GROUP BY entity_type ORDER BY count(*) DESC, entity_type"
            )
            cached = [{"type": t, "count": c} for t, c in cur.fetchall()]
        cache.set(TYPES_CACHE_KEY, cached, TYPES_CACHE_SECONDS)
    return no_store({"types": cached, "as_of": _as_of_iso()})
