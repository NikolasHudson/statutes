"""LlmUsage gains the org dimension (billing attaches to orgs).

Nullable: background traffic (cron/shell) has no user, hence no billing org.
Reporting-only — budget enforcement stays per-user.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0005_llmusage"),
        ("tenancy", "0002_billing"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmusage",
            name="org",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="llm_usage",
                to="tenancy.organization",
            ),
        ),
    ]
