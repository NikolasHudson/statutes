"""The one place the MCP server touches ``apps.resources``.

Everything else in ``apps.mcp_server`` is corpus: law, the citator, the
verification tools. Resources are reference datasets that are *not* law
(RESOURCES_PLAN.md), and ``apps/resources/tests/test_isolation.py`` fails the
build if any other module here imports them — the same arrangement as
``apps/api/api.py``, which is the single meeting point on the REST side.

Keep this file an adapter: re-export the tool body, and own the extra throttle.
No registry logic lives here.
"""

from __future__ import annotations

from apps.resources.datasets.sos_entities.tool import (  # noqa: F401
    lookup_business_entity_tool,
)
from apps.resources.ratelimit import enforce_user_rate_limit

# Tools that answer from apps.resources. gating.py runs
# ``enforce_resources_rate_limit`` for these on top of the ordinary gate.
RESOURCE_TOOLS: frozenset[str] = frozenset({"lookup_business_entity"})


def enforce_resources_rate_limit(principal) -> None:
    """The registry's own per-user throttle, on top of the per-key daily quota.

    Keyed on the *user* and on the same ``search`` bucket the web route uses,
    deliberately: one person gets one budget for walking the registry, however
    many API keys or OAuth tokens they hold and whichever surface they use.
    Raises ninja ``HttpError`` 429, which auth.py already translates."""
    enforce_user_rate_limit(getattr(principal, "user", None), "search")
