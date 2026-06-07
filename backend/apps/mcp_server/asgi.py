"""ASGI entrypoint for the hosted MCP streamable-HTTP server.

Importing this module bootstraps Django and builds the FastMCP streamable-HTTP
app (stateless + JSON) wrapped in X-API-Key auth and an auth-exempt
``GET /healthz``. Serve it with a process manager, e.g. the App Platform
``run_command``::

    gunicorn apps.mcp_server.asgi:app \\
        -k uvicorn.workers.UvicornWorker \\
        --workers 2 --bind 0.0.0.0:8080 \\
        --timeout 120 --graceful-timeout 120 \\
        --access-logfile - --error-logfile -

Mirrors ``core/asgi.py`` / ``core/wsgi.py``: the ``app`` object is constructed
at import time so the server process has it ready. Building it here (not in
``main()``) is what lets gunicorn import a module-level ASGI callable and run
multiple worker processes — only safe because the app is stateless.
"""

from .server import build_http_app

app = build_http_app()
