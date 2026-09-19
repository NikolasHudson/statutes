"""Shared resources infrastructure: the dataset registry rows and the sync log.

"Resources" are reference datasets a lawyer uses *alongside* legal research —
they are not law. The hard rule for this whole app (RESOURCES_PLAN.md §1) is
that nothing here touches ``apps.corpus``: no Node/Source/edge rows, no
embeddings, no foreign keys in either direction, and no imports either way.
Same Postgres database, separate tables, separate code.

Per-dataset models live in ``apps.resources.datasets.<name>.models`` and are
imported at the bottom of this module so they land under the single
``resources`` app label and share one migration history.
"""

from __future__ import annotations

from django.db import models


class DatasetKind(models.TextChoices):
    # We hold the rows ourselves and refresh them on a schedule.
    TABLE = "table", "Local table"
    # No table and no sync — a link-out or live lookup. Nothing uses this yet;
    # it exists so adding the first one does not reshape the registry.
    EXTERNAL = "external", "External lookup"


class Dataset(models.Model):
    """One reference dataset, as the Resources index and the API advertise it.

    Rows are created by data migrations, not by hand or by the sync: the
    registry is code-shaped configuration, and prod has no admin workflow for
    it.
    """

    slug = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    kind = models.CharField(
        max_length=16, choices=DatasetKind.choices, default=DatasetKind.TABLE
    )

    source_name = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    license = models.CharField(max_length=120, blank=True)
    # Shown verbatim in the UI provenance strip. CC BY 4.0 requires it.
    attribution_text = models.TextField(blank=True)
    # Free text ("weekly"), not a schedule the code reads — cron is external.
    refresh_cadence = models.CharField(max_length=60, blank=True)

    enabled = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "title")

    def __str__(self) -> str:
        return self.slug

    def latest_ok_snapshot(self) -> "Snapshot | None":
        return self.snapshots.filter(status=SnapshotStatus.OK).order_by("-id").first()

    def as_of(self):
        """The date the UI shows as "data as of". The source's own timestamp
        when we have one, else when our load finished — never today()."""
        snap = self.latest_ok_snapshot()
        if snap is None:
            return None
        return snap.source_last_modified or snap.finished_at


class SnapshotStatus(models.TextChoices):
    RUNNING = "running", "Running"
    OK = "ok", "OK"
    # Source file byte-identical to the last good load; nothing to do.
    SKIPPED = "skipped", "Skipped"
    # Refused before touching the live table (bad header, shrink gate, lock).
    ABORTED = "aborted", "Aborted"
    FAILED = "failed", "Failed"


class Snapshot(models.Model):
    """One run of ``sync_resource``. Append-only; the history is how we answer
    "when did this row stop being listed" and "when did the load last work"."""

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="snapshots"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=SnapshotStatus.choices, default=SnapshotStatus.RUNNING
    )

    # Provenance of the bytes we loaded.
    source_last_modified = models.DateTimeField(null=True, blank=True)
    file_sha256 = models.CharField(max_length=64, blank=True)
    file_bytes = models.BigIntegerField(null=True, blank=True)

    # What the load did. row_count is rows read from the file; the rest are
    # effects on the live table.
    row_count = models.IntegerField(default=0)
    inserted = models.IntegerField(default=0)
    updated = models.IntegerField(default=0)
    deactivated = models.IntegerField(default=0)
    reactivated = models.IntegerField(default=0)

    message = models.TextField(blank=True)

    class Meta:
        ordering = ("-id",)
        indexes = [
            models.Index(
                fields=("dataset", "status", "-id"), name="resources_snap_lookup"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.dataset_id}:{self.pk} {self.status}"


# Dataset models are defined in their own packages but registered under this
# app label. Import them last so the shared models above are importable from
# them without a cycle.
from .datasets.sos_entities.models import BusinessEntity  # noqa: E402,F401
