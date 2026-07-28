"""Release the OAuth models from apps.mcp_server's state. No SQL.

The other half of ``oauth_server/0001_initial``: that migration adopted the
three models (state only, tables untouched), and this one drops them from this
app's state so Django does not believe two apps own the same tables.

``database_operations=[]`` again — the tables stay exactly where they are and
keep their ``mcp_server_*`` names. This app keeps only the MCP transport:
server.py, tools.py, gating.py, asgi.py, and the auth middleware that now
consumes tokens from apps.oauth_server.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # Must run AFTER oauth_server has adopted the models, so the state is
        # never in a window where neither app declares them.
        ("oauth_server", "0001_initial"),
        ("mcp_server", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # FKs first, then the models they point at.
                migrations.RemoveField(model_name="oauthtoken", name="authorization_code"),
                migrations.RemoveField(model_name="oauthtoken", name="client"),
                migrations.RemoveField(model_name="oauthtoken", name="user"),
                migrations.RemoveField(model_name="oauthauthorizationcode", name="client"),
                migrations.RemoveField(model_name="oauthauthorizationcode", name="user"),
                migrations.DeleteModel(name="OAuthToken"),
                migrations.DeleteModel(name="OAuthAuthorizationCode"),
                migrations.DeleteModel(name="OAuthClient"),
            ],
            database_operations=[],
        ),
    ]
