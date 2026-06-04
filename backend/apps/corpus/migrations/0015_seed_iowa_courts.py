"""Seed the Iowa courts reference table.

Only the two courts that appear in the loaded caselaw slice are seeded — the
CourtListener slug ``iowa`` (Supreme Court of Iowa) and ``iowactapp`` (Court of
Appeals of Iowa), matching ``ingestion_caselaw.validators._KNOWN_COURTS``. The
slug is the apex court's ``iowa`` (NOT ``iowasupct``); seeding the wrong slug
would silently fail to join ``Node.source_metadata['court_id']``.

Reuses the Iowa jurisdiction (seeded in 0003). Idempotent via get_or_create;
extend ``COURTS`` if district/territorial courts are added later.
"""

from django.db import migrations

IOWA_SLUG = "iowa"

# level: lower binds higher (1 Supreme binds 2 Appellate).
COURTS = [
    {
        "court_id": "iowa",
        "name": "Supreme Court of Iowa",
        "short_name": "Iowa",
        "level": 1,
    },
    {
        "court_id": "iowactapp",
        "name": "Court of Appeals of Iowa",
        "short_name": "Iowa Ct. App.",
        "level": 2,
    },
]


def seed(apps, schema_editor):
    Jurisdiction = apps.get_model("corpus", "Jurisdiction")
    Court = apps.get_model("corpus", "Court")

    jurisdiction = Jurisdiction.objects.get(slug=IOWA_SLUG)

    for c in COURTS:
        Court.objects.get_or_create(
            court_id=c["court_id"],
            defaults={
                "name": c["name"],
                "short_name": c["short_name"],
                "level": c["level"],
                "jurisdiction": jurisdiction,
            },
        )


def unseed(apps, schema_editor):
    Court = apps.get_model("corpus", "Court")
    Court.objects.filter(court_id__in=[c["court_id"] for c in COURTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0014_node_node_source_metadata_gin"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
