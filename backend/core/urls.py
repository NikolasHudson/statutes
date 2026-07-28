from django.contrib import admin
from django.urls import include, path

from apps.api.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    # OAuth 2.0 authorization server: /.well-known/oauth-* discovery documents
    # (which RFC 8414/9728 require at the domain root) plus /oauth/{register,
    # authorize,token,revoke}. Serves both the MCP transport and /api/edms.
    # See apps/oauth_server/urls.py.
    path("", include("apps.oauth_server.urls")),
]
