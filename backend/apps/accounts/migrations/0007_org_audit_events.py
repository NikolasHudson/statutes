"""Audit event-type choices gain the org membership/invitation events.

Choices are validated in Python, not by a DB constraint, so this is a state-only
column alter — no data change.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_auditevent_event_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='auditevent',
            name='event_type',
            field=models.CharField(choices=[('login_success', 'Login success'), ('login_failure', 'Login failure'), ('login_locked_out', 'Login blocked (locked out)'), ('logout', 'Logout'), ('register', 'Registration'), ('register_blocked', 'Registration blocked (throttled)'), ('password_change', 'Password change'), ('profile_change', 'Profile / email change'), ('settings_change', 'Settings / preferences change'), ('tos_accepted', 'Terms of Service accepted'), ('onboarding_completed', 'Onboarding completed'), ('api_key_create', 'API key created'), ('api_key_revoke', 'API key revoked'), ('admin_user_change', 'Admin changed a user account'), ('org_member_add', 'Org member added'), ('org_member_remove', 'Org member removed'), ('org_role_change', 'Org member role changed'), ('org_invite_create', 'Org invitation sent'), ('org_invite_revoke', 'Org invitation revoked'), ('org_invite_accept', 'Org invitation accepted'), ('org_update', 'Organization updated')], db_index=True, max_length=32),
        ),
    ]
