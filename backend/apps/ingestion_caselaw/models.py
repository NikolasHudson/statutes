from __future__ import annotations

from django.db import models


class RawIngestion(models.Model):
    """Immutable record of one raw input blob.

    For caselaw the "blob" is an intermediate JSONL artifact produced by the
    Phase-1 acquire step — one per CourtListener bulk table we slice. Dedupes
    by content_hash: re-producing a byte-identical Iowa slice is a no-op.

    Mirrors ``apps.ingestion_iowa_code.models.RawIngestion`` field-for-field,
    with caselaw ``SOURCE_KIND_CHOICES``. ``code_year`` is reused to store the
    quarterly bulk *export* year (e.g. 2026).
    """

    SOURCE_KIND_CHOICES = [
        ("cl_bulk_clusters", "CourtListener bulk opinion-clusters CSV"),
        ("cl_bulk_opinions", "CourtListener bulk opinions CSV"),
        ("cl_bulk_citations", "CourtListener bulk citations CSV"),
        ("cl_bulk_dockets", "CourtListener bulk dockets CSV"),
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
    """One end-to-end run: acquire (CSV→JSONL) or write (JSONL→corpus).

    Mirrors ``apps.ingestion_iowa_code.models.IngestionRun`` with two caselaw
    additions — ``phase`` (which leg of the pipeline this run records) and
    ``last_cluster_id`` (a progress high-water mark, for logging only; resume
    never gates on it because CourtListener ids are not monotonic with filing
    date). ``raw`` is nullable here because an *acquire* run summarises several
    artifacts at once (their hashes go in ``log``); a *write* run links the one
    artifact it consumed.
    """

    STATUS_CHOICES = [
        ("pending", "Pending review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("failed", "Failed"),
    ]
    PHASE_CHOICES = [
        ("acquire", "Acquire"),
        ("write", "Write"),
    ]

    raw = models.ForeignKey(
        RawIngestion,
        on_delete=models.PROTECT,
        related_name="runs",
        null=True,
        blank=True,
    )
    phase = models.CharField(max_length=16, choices=PHASE_CHOICES, default="acquire")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    nodes_added = models.PositiveIntegerField(default=0)
    nodes_amended = models.PositiveIntegerField(default=0)
    nodes_repealed = models.PositiveIntegerField(default=0)
    nodes_unchanged = models.PositiveIntegerField(default=0)
    last_cluster_id = models.PositiveBigIntegerField(null=True, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    log = models.TextField(blank=True)

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return f"Run #{self.pk} ({self.phase}/{self.status})"
