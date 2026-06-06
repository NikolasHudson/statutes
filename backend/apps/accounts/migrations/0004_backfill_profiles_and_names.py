"""Backfill for the profile/preferences feature.

Two data fixes for users that existed before 0003:
  * give every user a UserProfile row (new users get one from the post_save
    signal; pre-existing ones need it created here),
  * split the legacy single ``full_name`` into ``first_name`` / ``last_name``
    (first token = first name, remainder = last name) when those are still
    blank, so the structured fields aren't empty for current accounts.

Both use the historical model state via ``apps.get_model`` and are written to
be safely re-runnable. The reverse is a no-op: dropping the rows/values is the
job of 0003's schema reversal, not this data step.
"""

from __future__ import annotations

from django.db import migrations


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")

    for user in User.objects.all().iterator():
        # Split full_name → first/last only when the structured fields are still
        # empty, so we never clobber a name a user has already set explicitly.
        if not user.first_name and not user.last_name and user.full_name:
            parts = user.full_name.split()
            user.first_name = parts[0] if parts else ""
            user.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            user.save(update_fields=["first_name", "last_name"])

        UserProfile.objects.get_or_create(user=user)


def noop_reverse(apps, schema_editor):
    # Reversing the schema (0003) removes the columns/table; nothing to undo here.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_userprofile_user_first_name_user_last_name_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
