"""Seed the Iowa Acts (session laws) source, node types and citation formats.

Mirrors 0022 (Iowa Admin. Code). Three-level hierarchy: session → chapter
(one chapter = one enrolled bill) → section (the leaf). The ``chapter`` /
``section`` NodeType keys are deliberately reused so statute-style browse and
``compare_editions``'s section-leaf filter work unmodified.

``official_url_template`` uses the year-alias PDF path, which 302s to the
canonical ``iactc/{ga}.{session}`` publication for every year verified
(1965→2026). Acts are frozen documents — one forever-open NodeVersion per
section, no update cycle.
"""

from django.db import migrations

IOWA_SLUG = "iowa"

ACTS_SOURCE = {
    "slug": "iowa-acts",
    "name": "Iowa Acts",
    "citation_abbreviation": "Iowa Acts",
    "official_url_template": "",
}

NODE_TYPES = [
    {
        "key": "session",
        "label_singular": "Session",
        "label_plural": "Sessions",
        "abbreviation": "",
        "level": 0,
        "citation_segment_template": "{ordinal}",
    },
    {
        "key": "chapter",
        "label_singular": "Chapter",
        "label_plural": "Chapters",
        "abbreviation": "ch.",
        "level": 1,
        "citation_segment_template": "ch. {ordinal}",
    },
    {
        "key": "section",
        "label_singular": "Section",
        "label_plural": "Sections",
        "abbreviation": "§",
        "level": 2,
        "citation_segment_template": "§{ordinal}",
    },
]

CITATION_FORMATS = [
    {"key": "long", "template": "{year} Iowa Acts, ch. {chapter}, §{section}"},
    {"key": "short", "template": "{year} Iowa Acts, ch. {chapter}"},
    {"key": "ultra_short", "template": "ch. {chapter}, §{section}"},
]


def seed(apps, schema_editor):
    Jurisdiction = apps.get_model("corpus", "Jurisdiction")
    Source = apps.get_model("corpus", "Source")
    NodeType = apps.get_model("corpus", "NodeType")
    CitationFormat = apps.get_model("corpus", "CitationFormat")

    jurisdiction = Jurisdiction.objects.get(slug=IOWA_SLUG)

    source, _ = Source.objects.get_or_create(
        jurisdiction=jurisdiction,
        slug=ACTS_SOURCE["slug"],
        defaults={
            "name": ACTS_SOURCE["name"],
            "citation_abbreviation": ACTS_SOURCE["citation_abbreviation"],
            "official_url_template": ACTS_SOURCE["official_url_template"],
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
        jurisdiction__slug=IOWA_SLUG, slug=ACTS_SOURCE["slug"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0023_alter_crossreference_source"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
