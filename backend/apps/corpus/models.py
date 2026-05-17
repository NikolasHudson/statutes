from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import VectorField


class Jurisdiction(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=20)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Source(models.Model):
    jurisdiction = models.ForeignKey(
        Jurisdiction, on_delete=models.PROTECT, related_name="sources"
    )
    slug = models.SlugField()
    name = models.CharField(max_length=200)
    citation_abbreviation = models.CharField(max_length=50)
    official_url_template = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("jurisdiction__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("jurisdiction", "slug"),
                name="uniq_source_per_jurisdiction",
            ),
        ]

    def __str__(self):
        return f"{self.jurisdiction.abbreviation} — {self.name}"


class NodeType(models.Model):
    """Describes one level in a Source's hierarchy. Hierarchy is data, not code."""

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="node_types")
    key = models.CharField(max_length=50)
    label_singular = models.CharField(max_length=50)
    label_plural = models.CharField(max_length=50, blank=True)
    abbreviation = models.CharField(max_length=20, blank=True)
    level = models.PositiveSmallIntegerField()
    citation_segment_template = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("source", "level")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "key"), name="uniq_nodetype_per_source"
            ),
        ]

    def __str__(self):
        return f"{self.source.citation_abbreviation} · {self.label_singular}"


class Node(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="nodes")
    node_type = models.ForeignKey(NodeType, on_delete=models.PROTECT, related_name="nodes")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    ordinal = models.CharField(max_length=50)
    path = models.CharField(max_length=500, db_index=True)
    heading = models.CharField(max_length=500, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    is_repealed = models.BooleanField(default=False)

    class Meta:
        ordering = ("source", "path")
        constraints = [
            models.UniqueConstraint(fields=("source", "path"), name="uniq_node_path_per_source"),
        ]

    def __str__(self):
        return f"{self.path} {self.heading}".strip()


class ReviewStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class NodeVersion(models.Model):
    """Append-only by convention. When a section is amended, close the current
    version (set effective_to) and insert a new row."""

    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="versions")
    body_text = models.TextField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    enacted_by = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)
    embedding_source_hash = models.CharField(max_length=64, blank=True)
    search_vector = SearchVectorField(null=True, blank=True)
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    review_status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("node", "-effective_from")
        indexes = [
            GinIndex(fields=("search_vector",), name="nodeversion_search_gin"),
        ]

    def __str__(self):
        return f"{self.node} @ {self.effective_from}"


class CitationFormat(models.Model):
    """Per-source display templates. Held separately from Source so iteration
    does not require migrations on Source."""

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="citation_formats")
    key = models.CharField(max_length=50)
    template = models.CharField(max_length=500)

    class Meta:
        ordering = ("source", "key")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "key"), name="uniq_citation_format_per_source"
            ),
        ]

    def __str__(self):
        return f"{self.source.citation_abbreviation} · {self.key}"


class CrossReferenceKind(models.TextChoices):
    INTERNAL = "internal", "Internal"
    EXTERNAL = "external", "External"


class CrossReference(models.Model):
    """A reference from one node version to another node (or to external text
    when the target is outside the corpus)."""

    from_version = models.ForeignKey(
        NodeVersion, on_delete=models.CASCADE, related_name="outgoing_references"
    )
    to_node = models.ForeignKey(
        Node,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_references",
    )
    external_text = models.TextField(blank=True)
    kind = models.CharField(
        max_length=16, choices=CrossReferenceKind.choices, default=CrossReferenceKind.INTERNAL
    )

    class Meta:
        ordering = ("from_version",)

    def __str__(self):
        target = self.to_node or self.external_text[:60]
        return f"{self.from_version} → {target}"
