"""URL routes for the MCP OAuth authorization server (served by Django).

Mounted at the ROOT of core/urls.py — the ``/.well-known/*`` documents must
live at the domain root per RFC 8414 / RFC 9728. The ``/mcp``-suffixed
variants cover clients that derive the well-known URL by path-insertion from
the resource URI ``https://<host>/mcp`` (RFC 9728 §3.1; older MCP clients do
the same for AS metadata).

Deploy note: on App Platform the ``/`` catch-all routes to chat-frontend, so
going live needs ingress rules pinning ``/.well-known/oauth-*`` and ``/oauth``
to the Django component (flagged in MCP_PRODUCTION_PLAN.md §2a).
"""

from django.urls import path

from . import oauth

app_name = "mcp_oauth"

urlpatterns = [
    path(
        ".well-known/oauth-authorization-server",
        oauth.authorization_server_metadata,
        name="as-metadata",
    ),
    path(
        ".well-known/oauth-authorization-server/mcp",
        oauth.authorization_server_metadata,
        name="as-metadata-mcp",
    ),
    path(
        ".well-known/oauth-protected-resource",
        oauth.protected_resource_metadata,
        name="prm",
    ),
    path(
        ".well-known/oauth-protected-resource/mcp",
        oauth.protected_resource_metadata,
        name="prm-mcp",
    ),
    path("oauth/register", oauth.register, name="register"),
    path("oauth/authorize", oauth.authorize, name="authorize"),
    path("oauth/token", oauth.token, name="token"),
    path("oauth/revoke", oauth.revoke, name="revoke"),
]
