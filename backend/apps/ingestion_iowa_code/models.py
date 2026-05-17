"""Persistence for raw Iowa Code inputs and ingestion runs.

The corpus app owns the canonical Node/NodeVersion tables. This app owns the
audit trail of *what raw bytes we ingested and when* — so we can re-parse
historical inputs without re-fetching, and so a reviewer can trace any
NodeVersion back to the exact source it came from.
"""

from __future__ import annotations

from django.db import models


class RawIngestion(models.Model):
    """Immutable record of one raw input blob.

    Dedupes by content_hash — re-uploading the same JSON is a no-op."""

    SOURCE_KIND_CHOICES = [
        ("probe_json", "Probe JSON"),
        ("legis_rtf", "legis.iowa.gov RTF"),
        ("legis_html", "legis.iowa.gov HTML"),
        ("attorney_json", "Attorney-supplied JSON"),
    ]

    source_kind = models.CharField(max_length=32, choices=SOURCE_KIND_CHOICES)
    code_year = models.PositiveIntegerField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    fetched_from = models.CharField(max_length=500, blank=True)
    content_hash = models.CharField(max_length=64, unique=True, db_index=True)
    byte_size = models.PositiveBigIntegerField()
    storage_path = models.CharField(max_length=500)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-fetched_at",)

    def __str__(self):
        return f"{self.source_kind} {self.code_year} ({self.content_hash[:8]})"


class IngestionRun(models.Model):
    """One end-to-end run: raw → parse → diff → write.

    Holds the changeset summary so the admin review workflow has something
    to display without recomputing the diff."""

    STATUS_CHOICES = [
        ("pending", "Pending review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("failed", "Failed"),
    ]

    raw = models.ForeignKey(
        RawIngestion, on_delete=models.PROTECT, related_name="runs"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    nodes_added = models.PositiveIntegerField(default=0)
    nodes_amended = models.PositiveIntegerField(default=0)
    nodes_repealed = models.PositiveIntegerField(default=0)
    nodes_unchanged = models.PositiveIntegerField(default=0)
    validation_errors = models.JSONField(default=list, blank=True)
    log = models.TextField(blank=True)

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return f"Run #{self.pk} ({self.status})"
