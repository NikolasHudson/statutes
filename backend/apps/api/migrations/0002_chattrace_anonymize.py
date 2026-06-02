"""Strip sender attribution from existing chat traces.

Traces are kept for search-quality review only, never to see who asked. New
rows are written with ``user=None`` (see ``apps.api.trace_capture``); this
migration de-attributes every row that predates that change so the chats we
already have can't be linked to a sender either. Forward-only: the FK is set
null, which cannot be reversed (the original sender is intentionally lost).
"""

from __future__ import annotations

from django.db import migrations


def anonymize_existing(apps, schema_editor):
    ChatTrace = apps.get_model("api", "ChatTrace")
    ChatTrace.objects.exclude(user=None).update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(anonymize_existing, migrations.RunPython.noop),
    ]
