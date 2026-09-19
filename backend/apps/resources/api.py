"""``/api/resources`` — the Resources surface.

Resources are reference datasets that sit beside legal research without being
law: the Iowa SOS business-entity registry today, licensing and UCC filings
later. Nothing here reads or writes ``apps.corpus``.

Two policies apply to every route in this router and in every dataset router
it mounts, and neither is negotiable per-route:

* **Session auth + paid access.** There is no ``auth=None`` route. The SOS
  extract lists registered agents, and a registered agent is very often a
  private individual at a home address — so this data stays behind a login and
  out of search engines. The same reasoning rules out a bulk-export endpoint;
  do not add one.
* **``private, no-store``.** See ``apps.resources.responses``.
"""

from __future__ import annotations

from ninja import Router

from apps.api.paywall import require_paid_access
from apps.api.session_auth import session_auth

from .datasets.sos_entities.api import sos_router
from .models import Dataset, DatasetKind
from .responses import no_store

resources_router = Router()


def _row_count(dataset: Dataset) -> int | None:
    """Live rows a dataset currently offers, or None for kinds with no table."""
    if dataset.kind != DatasetKind.TABLE:
        return None
    if dataset.slug == "iowa-business-entities":
        from .datasets.sos_entities.models import BusinessEntity

        return BusinessEntity.objects.filter(is_active=True).count()
    return None


@resources_router.get("", auth=session_auth)
def list_datasets(request):
    """What the Resources index renders. A new dataset appears here from its
    ``Dataset`` row alone — the frontend index has no per-dataset code."""
    require_paid_access(request.auth)
    out = []
    for dataset in Dataset.objects.filter(enabled=True):
        as_of = dataset.as_of()
        out.append(
            {
                "slug": dataset.slug,
                "title": dataset.title,
                "description": dataset.description,
                "kind": dataset.kind,
                "source_name": dataset.source_name,
                "source_url": dataset.source_url,
                "license": dataset.license,
                "attribution_text": dataset.attribution_text,
                "refresh_cadence": dataset.refresh_cadence,
                "as_of": as_of.isoformat()[:10] if as_of else None,
                "row_count": _row_count(dataset),
            }
        )
    return no_store({"datasets": out})


resources_router.add_router("/iowa-business-entities", sos_router)
