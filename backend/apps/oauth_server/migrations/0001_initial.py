"""Adopt the OAuth models into apps.oauth_server WITHOUT touching the database.

The authorization server was split out of ``apps.mcp_server`` on 2026-07-28
(MCP was its first consumer, not its owner — ``/api/edms`` now authenticates
with the same tokens). Django's autodetector wants to DROP the three tables
from one app and CREATE them in the other, which would delete every registered
client, live access token, and refresh token in production.

So this is state-only: ``database_operations=[]`` means no SQL runs at all, and
the models keep ``db_table = "mcp_server_*"`` (see models.py) so they continue
to read the tables ``mcp_server/0001_initial`` created. The legacy table names
are the deliberate price of a zero-downtime move — renaming them would need an
``ALTER TABLE`` that lands while the OLD image is still serving traffic, i.e. a
window in which every MCP connector and EDMSpro extension 500s.

Paired with ``mcp_server/0002``, which releases the same models from that app's
state. Order is enforced by the dependencies: mcp_server.0001 (tables exist) →
oauth_server.0001 (this, adopt state) → mcp_server.0002 (release state).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        # The tables these models adopt were created here.
        ("mcp_server", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="OAuthClient",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("client_id", models.CharField(db_index=True, max_length=64, unique=True)),
                        ("client_secret_hash", models.CharField(blank=True, default="", max_length=64)),
                        ("client_name", models.CharField(blank=True, default="", max_length=200)),
                        ("redirect_uris", models.JSONField(default=list)),
                        ("token_endpoint_auth_method", models.CharField(choices=[("none", "None (public client, PKCE only)"), ("client_secret_post", "Client secret (POST body)"), ("client_secret_basic", "Client secret (HTTP Basic)")], default="client_secret_basic", max_length=32)),
                        ("grant_types", models.JSONField(default=list, help_text="Subset of {authorization_code, refresh_token}.")),
                        ("scope", models.CharField(blank=True, default="", max_length=200)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                    ],
                    options={
                        "db_table": "mcp_server_oauthclient",
                        "ordering": ("-created_at",),
                    },
                ),
                migrations.CreateModel(
                    name="OAuthAuthorizationCode",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("code_hash", models.CharField(db_index=True, max_length=64, unique=True)),
                        ("redirect_uri", models.TextField()),
                        ("code_challenge", models.CharField(max_length=128)),
                        ("code_challenge_method", models.CharField(default="S256", max_length=8)),
                        ("scope", models.CharField(blank=True, default="", max_length=200)),
                        ("resource", models.TextField(blank=True, default="")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("expires_at", models.DateTimeField()),
                        ("used_at", models.DateTimeField(blank=True, null=True)),
                        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mcp_oauth_codes", to=settings.AUTH_USER_MODEL)),
                        ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="authorization_codes", to="oauth_server.oauthclient")),
                    ],
                    options={
                        "db_table": "mcp_server_oauthauthorizationcode",
                        "ordering": ("-created_at",),
                    },
                ),
                migrations.CreateModel(
                    name="OAuthToken",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("access_hashed", models.CharField(db_index=True, max_length=64, unique=True)),
                        ("refresh_hashed", models.CharField(db_index=True, max_length=64, unique=True)),
                        ("scope", models.CharField(blank=True, default="", max_length=200)),
                        ("resource", models.TextField(blank=True, default="")),
                        ("access_expires_at", models.DateTimeField()),
                        ("refresh_expires_at", models.DateTimeField()),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("last_used_at", models.DateTimeField(blank=True, null=True)),
                        ("revoked_at", models.DateTimeField(blank=True, null=True)),
                        ("authorization_code", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tokens", to="oauth_server.oauthauthorizationcode")),
                        ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tokens", to="oauth_server.oauthclient")),
                        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mcp_oauth_tokens", to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "db_table": "mcp_server_oauthtoken",
                        "ordering": ("-created_at",),
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
