"""Seed Iowa Code jurisdiction, source, node types and citation formats.

Idempotent: re-running the migration leaves the rows alone.
"""

from django.db import migrations


IOWA = {"slug": "iowa", "name": "Iowa", "abbreviation": "IA"}

IOWA_CODE_SOURCE = {
    "slug": "iowa-code",
    "name": "Iowa Code",
    "citation_abbreviation": "Iowa Code",
    "official_url_template": (
        "https://www.legis.iowa.gov/docs/ico/section/{year}/{path}.pdf"
    ),
}

NODE_TYPES = [
    {
        "key": "title",
        "label_singular": "Title",
        "label_plural": "Titles",
        "abbreviation": "T",
        "level": 1,
        "citation_segment_template": "Title {ordinal}",
    },
    {
        "key": "chapter",
        "label_singular": "Chapter",
        "label_plural": "Chapters",
        "abbreviation": "Ch.",
        "level": 2,
        "citation_segment_template": "ch. {ordinal}",
    },
    {
        "key": "section",
        "label_singular": "Section",
        "label_plural": "Sections",
        "abbreviation": "§",
        "level": 3,
        "citation_segment_template": "§{ordinal}",
    },
    {
        "key": "subsection",
        "label_singular": "Subsection",
        "label_plural": "Subsections",
        "abbreviation": "subsec.",
        "level": 4,
        "citation_segment_template": "({ordinal})",
    },
    {
        "key": "paragraph",
        "label_singular": "Paragraph",
        "label_plural": "Paragraphs",
        "abbreviation": "para.",
        "level": 5,
        "citation_segment_template": "({ordinal})",
    },
]

CITATION_FORMATS = [
    {"key": "long", "template": "Iowa Code § {path} ({year})"},
    {"key": "short", "template": "I.C. § {path}"},
    {"key": "ultra_short", "template": "§{path}"},
]


def seed(apps, schema_editor):
    Jurisdiction = apps.get_model("corpus", "Jurisdiction")
    Source = apps.get_model("corpus", "Source")
    NodeType = apps.get_model("corpus", "NodeType")
    CitationFormat = apps.get_model("corpus", "CitationFormat")

    jurisdiction, _ = Jurisdiction.objects.get_or_create(
        slug=IOWA["slug"],
        defaults={"name": IOWA["name"], "abbreviation": IOWA["abbreviation"]},
    )

    source, _ = Source.objects.get_or_create(
        jurisdiction=jurisdiction,
        slug=IOWA_CODE_SOURCE["slug"],
        defaults={
            "name": IOWA_CODE_SOURCE["name"],
            "citation_abbreviation": IOWA_CODE_SOURCE["citation_abbreviation"],
            "official_url_template": IOWA_CODE_SOURCE["official_url_template"],
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
    Jurisdiction = apps.get_model("corpus", "Jurisdiction")
    Source = apps.get_model("corpus", "Source")
    Source.objects.filter(
        jurisdiction__slug=IOWA["slug"], slug=IOWA_CODE_SOURCE["slug"]
    ).delete()
    Jurisdiction.objects.filter(slug=IOWA["slug"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
