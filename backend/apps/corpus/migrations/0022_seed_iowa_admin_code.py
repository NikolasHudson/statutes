"""Seed the Iowa Administrative Code source, node types and citation formats.

Reuses the existing Iowa jurisdiction (seeded in 0003). Idempotent:
re-running leaves the rows alone. Three-level hierarchy: agency → chapter →
rule (the leaf). ``official_url_template`` is empty by design — the IAC
publishes per-*chapter* documents, not per-rule, so the chapter PDF URL lives
in each chapter node's ``source_metadata`` instead of a templated per-rule URL.
"""

from django.db import migrations

IOWA_SLUG = "iowa"

ADMIN_CODE_SOURCE = {
    "slug": "iowa-admin-code",
    "name": "Iowa Administrative Code",
    "citation_abbreviation": "Iowa Admin. Code",
    "official_url_template": "",
}

NODE_TYPES = [
    {
        "key": "agency",
        "label_singular": "Agency",
        "label_plural": "Agencies",
        "abbreviation": "",
        "level": 0,
        "citation_segment_template": "{ordinal}",
    },
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
    {"key": "long", "template": "Iowa Admin. Code r. {path} ({year})"},
    {"key": "short", "template": "Iowa Admin. Code r. {path}"},
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
        slug=ADMIN_CODE_SOURCE["slug"],
        defaults={
            "name": ADMIN_CODE_SOURCE["name"],
            "citation_abbreviation": ADMIN_CODE_SOURCE["citation_abbreviation"],
            "official_url_template": ADMIN_CODE_SOURCE["official_url_template"],
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
        jurisdiction__slug=IOWA_SLUG, slug=ADMIN_CODE_SOURCE["slug"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0021_alter_caseresearchnote_kind"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
