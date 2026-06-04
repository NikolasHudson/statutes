"""Seed the Iowa Caselaw source and its node types.

Reuses the existing Iowa jurisdiction (seeded in 0003). Idempotent:
re-running leaves the rows alone.

Caselaw is modelled as a 2-level hierarchy under a single source:
``decision`` (the case / CourtListener opinion-cluster, a container) and
``opinion`` (lead/concurrence/dissent, which carries the text + NodeVersion).
See ``Case Law/CASELAW_INGESTION_PLAN.md`` (locked decision 2: one source,
court stored in ``Node.source_metadata``).

CitationFormat is intentionally NOT seeded here: the existing templates are
``{path}``-based, but a case's path is ``cl-cluster-<id>`` (not a citation).
Caselaw citations are built from metadata (case name, reporter, court, year)
and need separate renderer support — deferred to a later step.
"""

from django.db import migrations

IOWA_SLUG = "iowa"

CASELAW_SOURCE = {
    "slug": "iowa-caselaw",
    "name": "Iowa Caselaw",
    # citation_abbreviation is NOT NULL / no blank; the per-case reporter
    # citation is derived from metadata, this is just the source label.
    "citation_abbreviation": "Iowa",
    # CourtListener canonical opinion URL; placeholders are filled from
    # Node.source_metadata (cl_cluster_id, slug) by the URL renderer.
    "official_url_template": (
        "https://www.courtlistener.com/opinion/{cl_cluster_id}/{slug}/"
    ),
}

NODE_TYPES = [
    {
        "key": "decision",
        "label_singular": "Decision",
        "label_plural": "Decisions",
        "abbreviation": "",
        "level": 1,
        # Citation is built from case metadata, not an ordinal segment.
        "citation_segment_template": "",
    },
    {
        "key": "opinion",
        "label_singular": "Opinion",
        "label_plural": "Opinions",
        "abbreviation": "",
        "level": 2,
        "citation_segment_template": "",
    },
]


def seed(apps, schema_editor):
    Jurisdiction = apps.get_model("corpus", "Jurisdiction")
    Source = apps.get_model("corpus", "Source")
    NodeType = apps.get_model("corpus", "NodeType")

    jurisdiction = Jurisdiction.objects.get(slug=IOWA_SLUG)

    source, _ = Source.objects.get_or_create(
        jurisdiction=jurisdiction,
        slug=CASELAW_SOURCE["slug"],
        defaults={
            "name": CASELAW_SOURCE["name"],
            "citation_abbreviation": CASELAW_SOURCE["citation_abbreviation"],
            "official_url_template": CASELAW_SOURCE["official_url_template"],
        },
    )

    for nt in NODE_TYPES:
        NodeType.objects.get_or_create(
            source=source,
            key=nt["key"],
            defaults={
                "label_singular": nt["label_singular"],
                "label_plural": nt["label_plural"],
                "abbreviation": nt["abbreviation"],
                "level": nt["level"],
                "citation_segment_template": nt["citation_segment_template"],
            },
        )


def unseed(apps, schema_editor):
    Source = apps.get_model("corpus", "Source")
    Source.objects.filter(
        jurisdiction__slug=IOWA_SLUG, slug=CASELAW_SOURCE["slug"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0010_nodeversion_open_version_uniq"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
