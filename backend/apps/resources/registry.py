"""Slug → dataset wiring.

Importing this module imports every dataset package, which is what makes
``sync_resource <slug>`` resolvable and keeps the dataset models attached to
the ``resources`` app label. ``ResourcesConfig.ready`` imports it once.

Adding a dataset is: a module under ``datasets/``, a line here, a migration
for its table, and a ``Dataset`` row in a data migration.
"""

from __future__ import annotations

from .sync import BaseSync
from .datasets.sos_entities.sync import SosEntitiesSync

SYNC_CLASSES: dict[str, type[BaseSync]] = {
    SosEntitiesSync.slug: SosEntitiesSync,
}


def get_sync(slug: str) -> BaseSync:
    """Instantiate the loader for ``slug``. KeyError if the slug is unknown —
    callers turn that into a CommandError with the list of known slugs."""
    return SYNC_CLASSES[slug]()


def known_slugs() -> list[str]:
    return sorted(SYNC_CLASSES)
