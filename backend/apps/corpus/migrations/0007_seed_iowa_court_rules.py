"""Seed the Iowa Court Rules source, node types and citation formats.

Reuses the existing Iowa jurisdiction (seeded in 0003). Idempotent:
re-running leaves the rows alone.
"""

from django.db import migrations

IOWA_SLUG = "iowa"

COURT_RULES_SOURCE = {
    "slug": "iowa-court-rules",
    "name": "Iowa Court Rules",
    "citation_abbreviation": "Iowa Ct. R.",
    # Chapter-level PDF; rules are addressed within the chapter PDF.
    "official_url_template": (
        "https://www.legis.iowa.gov/docs/ACO/CR/LINC/"
        "{edition}.chapter.{chapter}.pdf"
    ),
}

NODE_TYPES = [
    {
        "key": "chapter",
        "label_singular": "Chapter",
        "label_plural": "Chapters",
        "abbreviation": "Ch.",
        "level": 1,
        "citation_segment_template": "ch. {ordinal}",
    },
    {
        "key": "rule",
        "label_singular": "Rule",
        "label_plural": "Rules",
        "abbreviation": "r.",
        "level": 2,
        "citation_segment_template": "r. {ordinal}",
    },
]

CITATION_FORMATS = [
    {"key": "long", "template": "Iowa Ct. R. {path} ({year})"},
    {"key": "short", "template": "Iowa R. {path}"},
    {"key": "ultra_short", "template": "r. {path}"},
]


def seed(apps, schema_editor):
    Jurisdiction = apps.get_model("corpus", "Jurisdiction")
    Source = apps.get_model("corpus", "Source")
    NodeType = apps.get_model("corpus", "NodeType")
    CitationFormat = apps.get_model("corpus", "CitationFormat")

    jurisdiction = Jurisdiction.objects.get(slug=IOWA_SLUG)

    source, _ = Source.objects.get_or_create(
        jurisdiction=jurisdiction,
        slug=COURT_RULES_SOURCE["slug"],
        defaults={
            "name": COURT_RULES_SOURCE["name"],
            "citation_abbreviation": COURT_RULES_SOURCE["citation_abbreviation"],
            "official_url_template": COURT_RULES_SOURCE["official_url_template"],
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

    for cf in CITATION_FORMATS:
        CitationFormat.objects.get_or_create(
            source=source,
            key=cf["key"],
            defaults={"template": cf["template"]},
        )


def unseed(apps, schema_editor):
    Source = apps.get_model("corpus", "Source")
    Source.objects.filter(
        jurisdiction__slug=IOWA_SLUG, slug=COURT_RULES_SOURCE["slug"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0006_hnsw_embedding"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
