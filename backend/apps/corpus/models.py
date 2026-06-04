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


class CourtLevel(models.IntegerChoices):
    SUPREME = 1, "Supreme"
    APPELLATE = 2, "Appellate"
    TRIAL = 3, "Trial"


class Court(models.Model):
    """Small reference table that makes binding-vs-persuasive authority
    queryable: caselaw decision nodes carry the CourtListener court slug in
    ``Node.source_metadata['court_id']``; joining that to ``Court.court_id``
    yields the court's authority ``level``. Kept OFF the generic Node model so
    no caselaw-specific column leaks into statutes/rules. Lower ``level`` int =
    higher authority (a Supreme decision binds an Appellate one)."""

    court_id = models.CharField(max_length=50, primary_key=True)  # CL slug, e.g. "iowa"
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=100, blank=True)
    jurisdiction = models.ForeignKey(
        Jurisdiction, on_delete=models.PROTECT, related_name="courts"
    )
    level = models.PositiveSmallIntegerField(
        choices=CourtLevel.choices,
        help_text="Authority rank; a lower number binds higher-numbered courts.",
    )

    class Meta:
        ordering = ("jurisdiction__name", "level")

    def __str__(self):
        return f"{self.name} (L{self.level})"


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
        indexes = [
            # Make source_metadata containment filters indexed — e.g. caselaw
            # retrieval scoped to ``source_metadata__court_id='iowa'`` or
            # ``__precedential_status='Published'`` (binding-vs-persuasive).
            # jsonb_path_ops: smaller/faster than the default and sufficient
            # because every filter we run is ``@>`` containment, never key
            # existence (``?``).
            GinIndex(
                fields=("source_metadata",),
                name="node_source_metadata_gin",
                opclasses=["jsonb_path_ops"],
            ),
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
    # Display-only rich structure (paragraphs + runs with citation links),
    # derived from the source HTML. NULL = render from body_text. Never feeds
    # FTS / content_hash / embeddings — those stay on the plain body_text.
    body_segments = models.JSONField(null=True, blank=True)
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
        constraints = [
            # At most one *open* (current) version per node may carry a given
            # content_hash. This makes re-ingestion idempotent at the DB level:
            # re-writing an unchanged provision/opinion raises IntegrityError
            # instead of creating a duplicate open version that would pollute
            # ``effective_to IS NULL`` lookups (and double-embed downstream).
            # Scoped to open versions so the append-only timeline can still
            # legitimately revert to a prior, now-closed text (hash reused on a
            # closed row is fine).
            models.UniqueConstraint(
                fields=("node", "content_hash"),
                condition=models.Q(effective_to__isnull=True),
                name="uniq_open_nodeversion_per_node_hash",
            ),
            # A node has at most one *current* version. Both writers close the
            # open version before inserting the replacement, so this never trips
            # in normal operation — it is a DB backstop against a latent bug
            # leaving two open rows (which would make ``effective_to IS NULL``
            # lookups and edition resolution ambiguous).
            models.UniqueConstraint(
                fields=("node",),
                condition=models.Q(effective_to__isnull=True),
                name="uniq_open_nodeversion_per_node",
            ),
        ]

    def __str__(self):
        return f"{self.node} @ {self.effective_from}"


class Edition(models.Model):
    """A published edition of a Source — e.g. "Iowa Code 2026".

    An Edition is a *named as-of date* over the append-only NodeVersion
    timeline: the text of a node "in edition E" is the version effective on
    ``E.as_of_date`` (resolved via ``get_section_at``). Loading a prior edition
    therefore needs no column on NodeVersion — edition membership is derived by
    date. ``as_of_date`` is unique per source so editions form a strict order.
    """

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="editions")
    year = models.PositiveIntegerField()
    label = models.CharField(max_length=200)
    as_of_date = models.DateField(
        help_text="Point-in-time date this edition's text is resolved at.",
    )
    published_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("source", "-year")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "year"), name="uniq_edition_per_source_year"
            ),
            models.UniqueConstraint(
                fields=("source", "as_of_date"), name="uniq_edition_asof_per_source"
            ),
        ]

    def __str__(self):
        return f"{self.label} (as of {self.as_of_date})"


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


class CrossReferenceSource(models.TextChoices):
    """Which extractor produced an edge. The per-``from_version`` rebuild that
    keeps a backfill idempotent is scoped to one source, so re-running the
    inline-link pass (``caselaw_link``) never deletes the citation-graph pass's
    edges (``caselaw_graph``) on the same opinion, and vice-versa."""

    STATUTE = "statute", "Statute prose"  # backfill_cross_references (Iowa Code)
    CASELAW_LINK = "caselaw_link", "Caselaw inline link"  # #1: html_with_citations
    CASELAW_GRAPH = "caselaw_graph", "Caselaw citation graph"  # #2: OpinionsCited


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
    source = models.CharField(
        max_length=20,
        choices=CrossReferenceSource.choices,
        default=CrossReferenceSource.STATUTE,
        help_text="Extractor that produced this edge; scopes idempotent rebuilds.",
    )
    # Citation depth/strength carried by the #2 graph pass (CourtListener
    # ``depth`` = how many times the citing opinion cites the cited one). Null
    # for text-derived edges (#1) which have no such count.
    weight = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("from_version",)
        constraints = [
            # Idempotency for internal edges: at most one (from_version,
            # to_node) per source. The backfill rebuilds a version's edges by
            # delete-then-insert; the constraint is the DB backstop so a
            # concurrent/duplicate run can't double-insert.
            models.UniqueConstraint(
                fields=("from_version", "to_node", "source"),
                condition=models.Q(to_node__isnull=False),
                name="uniq_crossref_internal_per_source",
            ),
            # Idempotency for external edges (unresolved citations): at most one
            # (from_version, external_text) per source.
            models.UniqueConstraint(
                fields=("from_version", "external_text", "source"),
                condition=models.Q(to_node__isnull=True),
                name="uniq_crossref_external_per_source",
            ),
        ]

    def __str__(self):
        target = self.to_node or self.external_text[:60]
        return f"{self.from_version} → {target}"


class ReporterCitation(models.Model):
    """Reporter-citation → cited decision Node resolver, populated from
    ``citations.jsonl``. Lets a free-text reporter cite (e.g. "759 N.W.2d 3")
    or an inline ``/c/<reporter>/<vol>/<page>/`` opinion link resolve to the
    case it names.

    Named ``ReporterCitation`` (not ``Citation``) to avoid colliding with
    ``apps.citations.parser.Citation``, the *statute* citation dataclass.

    The ``(reporter, volume, page)`` triple is NOT unique — parallel reporters
    and multi-case "table" decisions collide (≈1.9% of triples map to >1
    cluster, worst 42) — so the lookup index is non-unique and row identity is
    ``cl_citation_id`` (the only globally-unique field). Resolution treats an
    ambiguous triple as unresolved rather than guessing. Kept OFF the generic
    Node model."""

    cl_citation_id = models.BigIntegerField(unique=True)  # idempotency key
    cl_cluster_id = models.BigIntegerField()
    reporter = models.CharField(max_length=100)
    volume = models.CharField(max_length=20)  # CharField: upstream is a string
    page = models.CharField(max_length=30)  # CharField: comma-grouped values exist
    type = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="CourtListener citation-type enum."
    )
    to_node = models.ForeignKey(
        Node,
        on_delete=models.SET_NULL,  # a reporter→cluster fact outlives the Node;
        related_name="reporter_citations",  # a later load re-resolves to_node
        null=True,
        blank=True,  # null when the cited cluster is outside the loaded slice
    )

    class Meta:
        indexes = [
            # NON-unique: the triple maps to multiple cases for some keys.
            models.Index(
                fields=("reporter", "volume", "page"), name="reportercite_rvp_lookup"
            ),
        ]

    def __str__(self):
        return f"{self.volume} {self.reporter} {self.page}"
