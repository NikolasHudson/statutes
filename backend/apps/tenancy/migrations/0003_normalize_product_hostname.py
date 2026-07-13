"""Lowercase existing Product.hostname rows.

Data-only. ``Product.save()`` now normalizes the host, but rows written before it
did may carry uppercase or surrounding whitespace, and those can never match a
request: the middleware lowercases ``request.get_host()``. An unmatched host
resolves to the flagship (product=None, full corpus, no scope lock), so a
mis-cased front door fails OPEN — hence normalizing the stored side too.

``hostname`` is unique, so two rows that differ only in case would collide on
update; that is a genuinely ambiguous duplicate front door and is left to raise.
"""

from django.db import migrations


def normalize_hostnames(apps, schema_editor):
    # Historical model: save() (and its normalization) does not exist here, so
    # write through .update().
    Product = apps.get_model("tenancy", "Product")
    for pk, hostname in Product.objects.exclude(hostname=None).values_list(
        "pk", "hostname"
    ):
        normalized = (hostname or "").strip().lower() or None
        if normalized != hostname:
            Product.objects.filter(pk=pk).update(hostname=normalized)


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0002_billing"),
    ]

    operations = [
        # Irreversible only in the sense that the original casing is not
        # recoverable; reversing is a no-op because lowercase rows are valid.
        migrations.RunPython(normalize_hostnames, migrations.RunPython.noop),
    ]
