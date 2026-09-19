"""The registry row for the first dataset.

Dataset rows are configuration, so they arrive as code: prod has no admin
screen for them, and a row created by hand on one environment and not another
is exactly the kind of drift the Resources index would surface to users.
"""

from django.db import migrations

IOWA_BUSINESS_ENTITIES = {
    "slug": "iowa-business-entities",
    "title": "Iowa business entities",
    "description": (
        "Every business entity currently on the Iowa Secretary of State's "
        "active list — legal name, entity type, effective date, registered "
        "agent and principal office. Active filings only: the source carries "
        "no dissolved entities, no filing history and no officers."
    ),
    "kind": "table",
    "source_name": "Iowa Secretary of State, via the Iowa Data Hub",
    "source_url": "https://catalog.data.gov/dataset/active-iowa-business-entities",
    "license": "CC BY 4.0",
    "attribution_text": (
        "Source: Iowa Secretary of State via Iowa Data Hub, licensed CC BY 4.0."
    ),
    "refresh_cadence": "weekly",
    "enabled": True,
    "sort_order": 10,
}


def seed(apps, schema_editor):
    Dataset = apps.get_model("resources", "Dataset")
    Dataset.objects.update_or_create(
        slug=IOWA_BUSINESS_ENTITIES["slug"],
        defaults={k: v for k, v in IOWA_BUSINESS_ENTITIES.items() if k != "slug"},
    )


def unseed(apps, schema_editor):
    Dataset = apps.get_model("resources", "Dataset")
    Dataset.objects.filter(slug=IOWA_BUSINESS_ENTITIES["slug"]).delete()


class Migration(migrations.Migration):
    dependencies = [("resources", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
