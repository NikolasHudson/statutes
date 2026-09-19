"""Iowa Secretary of State — active business entities.

One row per entity currently on the SOS active list, keyed by ``corp_number``.
The source publishes *active entities only*: there is no dissolution feed, no
filing history and no officers. So we never delete. A row that stops appearing
is marked ``is_active = False`` with ``deactivated_on`` set, which is the only
way this table can ever answer "this entity stopped being listed around then".

Field widths are roughly double the longest value observed in the 2026-09-19
profile (344,639 rows) — the source can grow a column without breaking a load.
``corp_number`` stays a string: it is an identifier, not a number, and the
source has never promised it will not gain a letter.
"""

from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.db import models


class BusinessEntity(models.Model):
    corp_number = models.CharField(max_length=12, unique=True)

    legal_name = models.CharField(max_length=255)
    # apps.resources.normalize.normalize_name(legal_name) — the trigram search
    # column. Written by the sync, never by hand.
    name_normalized = models.CharField(max_length=255, db_index=False)
    entity_type = models.CharField(max_length=100, blank=True)
    # Delayed effective filings are normal here: dates up to ~13 months in the
    # future appear in the source. Never validate against today.
    effective_date = models.DateField(null=True, blank=True)

    registered_agent = models.CharField(max_length=255, blank=True)
    agent_normalized = models.CharField(max_length=255, blank=True)
    ra_address_1 = models.CharField(max_length=160, blank=True)
    ra_address_2 = models.CharField(max_length=160, blank=True)
    ra_city = models.CharField(max_length=80, blank=True)
    # Not always a two-letter code in the source; stored as published.
    ra_state = models.CharField(max_length=32, blank=True)
    ra_zip = models.CharField(max_length=16, blank=True)

    home_office = models.CharField(max_length=160, blank=True)
    ho_address_1 = models.CharField(max_length=160, blank=True)
    ho_address_2 = models.CharField(max_length=160, blank=True)
    ho_city = models.CharField(max_length=120, blank=True)
    ho_state = models.CharField(max_length=32, blank=True)
    ho_zip = models.CharField(max_length=16, blank=True)
    ho_country = models.CharField(max_length=16, blank=True)

    # Plain floats, no PostGIS: nothing renders a map in v1 and the source's
    # own POINT() column is redundant with these two, so it is not stored.
    ra_lat = models.FloatField(null=True, blank=True)
    ra_lon = models.FloatField(null=True, blank=True)
    ho_lat = models.FloatField(null=True, blank=True)
    ho_lon = models.FloatField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    first_seen = models.DateField()
    last_seen = models.DateField()
    deactivated_on = models.DateField(null=True, blank=True)

    last_snapshot = models.ForeignKey(
        "resources.Snapshot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name_plural = "business entities"
        indexes = [
            # The two search paths. word_similarity()/`<%` needs a trigram GIN
            # or it degrades to a sequential scan over every row; pg_trgm is
            # ensured by this app's own first migration.
            GinIndex(
                fields=("name_normalized",),
                name="resources_be_name_trgm",
                opclasses=["gin_trgm_ops"],
            ),
            GinIndex(
                fields=("agent_normalized",),
                name="resources_be_agent_trgm",
                opclasses=["gin_trgm_ops"],
            ),
            # The reverse agent lookup ("what else is this person the
            # registered agent for?") and the detail page's agent count are
            # exact equality on the pair, which a trigram GIN cannot serve.
            models.Index(
                fields=("agent_normalized", "ra_zip"), name="resources_be_agent_zip"
            ),
            # Equality filters offered by the search form.
            models.Index(fields=("ra_city",), name="resources_be_ra_city"),
            models.Index(fields=("ho_city",), name="resources_be_ho_city"),
            models.Index(fields=("ra_zip",), name="resources_be_ra_zip"),
            models.Index(fields=("entity_type",), name="resources_be_type"),
            models.Index(fields=("is_active",), name="resources_be_active"),
        ]

    def __str__(self) -> str:
        return f"{self.corp_number} {self.legal_name}"
