"""``lookup_business_entity`` — the registry as an agent tool.

JSON-able in, JSON-able out, no transport: the MCP server registers this
(through ``apps.mcp_server.resources_tools``, the one file on that side allowed
to import ``apps.resources``), and the Phase 2 chat tool will call the same
body. It answers from :func:`.api.run_search` / :func:`.api.entity_detail_payload`,
so an agent sees exactly what the web page sees.

Two things are different from the HTTP surface, both on purpose:

* **No paging.** A person pages; a program that pages is walking the registry.
  An agent gets the best ``limit`` rows and a ``total`` that tells it to narrow
  the query, never a cursor. This is the same no-bulk-export rule
  ``apps.resources.api`` states, applied to a caller that does not get tired.
* **Every payload says what it is.** Registry rows are not law. ``kind`` and
  ``notice`` travel with every response so a model cannot mistake a filing for
  authority, and ``as_of`` / ``verify_url`` let it say how stale the answer
  may be and where to confirm it.
"""

from __future__ import annotations

from .api import PAGE_SIZE_DEFAULT, _clean, _dataset, entity_detail_payload, run_search

LIMIT_DEFAULT = 10
LIMIT_MAX = PAGE_SIZE_DEFAULT

KIND = "registry_record"
NOTICE = (
    "Iowa Secretary of State business-entity registry data, from a periodic "
    "extract. This is not legal authority and must not be cited as law. Status "
    "and registered-agent details can change after the as_of date; confirm "
    "against the official Secretary of State business entity search before "
    "relying on it (for example, before serving process)."
)

# Where a person confirms a row. ``source_url`` is where the extract came from,
# which is a data catalog and no use to someone checking one entity.
VERIFY_URL = "https://sos.iowa.gov/search/business/search.aspx"

# The detail payload carries map coordinates for the web page's use. An agent
# has the street address; geocodes of what is often a home add nothing to it.
_DETAIL_DROP = ("lat", "lon")


def _envelope(payload: dict) -> dict:
    dataset = _dataset()
    return {
        "kind": KIND,
        "dataset": "iowa-business-entities",
        "source_name": dataset.source_name if dataset else None,
        "source_url": dataset.source_url if dataset else None,
        "verify_url": VERIFY_URL,
        "notice": NOTICE,
        **payload,
    }


def _strip_geo(detail: dict) -> dict:
    for block in ("registered_agent_address", "home_office_address"):
        address = detail.get(block)
        if isinstance(address, dict):
            for key in _DETAIL_DROP:
                address.pop(key, None)
    return detail


def lookup_business_entity_tool(
    query: str = "",
    corp_number: str = "",
    agent: str = "",
    city: str = "",
    zip_code: str = "",
    entity_type: str = "",
    include_inactive: bool = False,
    limit: int = LIMIT_DEFAULT,
) -> dict:
    corp_number = _clean(corp_number)
    if corp_number:
        detail = entity_detail_payload(corp_number)
        if detail is None:
            return _envelope(
                {
                    "found": False,
                    "corp_number": corp_number,
                    "error": "no entity with that corp number",
                }
            )
        return _envelope({"found": True, "entity": _strip_geo(detail)})

    query = _clean(query)
    agent = _clean(agent)
    city = _clean(city)
    zip_code = _clean(zip_code)
    if not any((query, agent, city, zip_code)):
        return _envelope(
            {
                "found": False,
                "error": (
                    "Provide at least one of: query (entity name or corp "
                    "number), corp_number, agent, city, zip_code. The registry "
                    "cannot be listed unfiltered."
                ),
            }
        )

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = LIMIT_DEFAULT
    page = run_search(
        q=query,
        agent=agent,
        city=city,
        zip_code=zip_code,
        entity_type=_clean(entity_type),
        include_inactive=bool(include_inactive),
        page=1,
        page_size=max(1, min(limit, LIMIT_MAX)),
    )
    results = page["results"]
    out = {
        "found": bool(results),
        "query": page["query"],
        "total": page["total"],
        "total_capped": page["total_capped"],
        "returned": len(results),
        "as_of": page["as_of"],
        "results": results,
    }
    if page["total"] > len(results):
        out["more"] = (
            "More entities match than were returned. Narrow the search (add "
            "city, zip_code, entity_type or a fuller name); results cannot be "
            "paged. Call again with corp_number for one entity's full record."
        )
    return _envelope(out)
