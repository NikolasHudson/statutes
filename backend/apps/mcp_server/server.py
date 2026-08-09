"""MCP server for Hudson Corpus.

Built on the official MCP Python SDK's FastMCP convenience wrapper. Runs as
its own process (ASGI / stdio) but imports the Django ORM directly — no
HTTP round-trip from the LLM client through our REST API. That gets us:

    1. Lower latency (one less hop)
    2. The full service-layer surface, including admin-only options if we
       ever expose them, gated separately from the public REST contract
    3. Tests can call into the tool functions without booting an HTTP
       server

Run via stdio (Claude Desktop's default transport):

    DJANGO_SETTINGS_MODULE=core.settings \\
    python -m apps.mcp_server

Run via streamable HTTP (for remote MCP):

    python -m apps.mcp_server --http --host 127.0.0.1 --port 8765

The Claude Desktop install flow lives in apps/mcp_server/README.md.
"""

from __future__ import annotations

import argparse
import hmac
import os
import sys

import django

from core.brand import MCP_SERVER_ID


def _bootstrap_django() -> None:
    """Configure Django before importing anything that touches the ORM.

    This is the same dance manage.py does — we just do it at the top of
    our entrypoint instead of relying on a runner."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()


def build_server():
    """Construct the FastMCP server with all tools registered.

    Imported lazily after django.setup() so the ORM is ready.

    Each tool is registered as an ``async def`` and dispatches the sync
    Django ORM work through ``sync_to_async`` — FastMCP runs handlers
    inside a coroutine, and Django's ORM raises
    ``SynchronousOnlyOperation`` when invoked directly from an async
    context. ``thread_sensitive=True`` keeps each call on a single
    dedicated thread so the DB connection is reused (and so test
    fixtures opened in the main transaction stay visible)."""
    from asgiref.sync import sync_to_async
    from mcp.server.fastmcp import FastMCP

    from . import tools

    # stateless_http + json_response are what make this safe to run behind App
    # Platform's load balancer, which has NO session affinity:
    #   * stateless_http=True  — a fresh transport per request, so no per-session
    #     state lives in one worker/instance's memory. (Stateful mode keys session
    #     state by Mcp-Session-Id in-process; a follow-up POST landing on a
    #     different worker would 404 "Session not found".) Every tool here is a
    #     self-contained request/response DB lookup, so we lose nothing — except
    #     the per-session credential binding stateful mode gives up, which the
    #     per-request X-API-Key check in auth.py fully compensates for.
    #   * json_response=True   — a single application/json body instead of an open
    #     SSE stream, which sidesteps the DO/Cloudflare edge streaming timeout.
    # transport_security is passed explicitly because the SDK only auto-enables
    # DNS-rebinding / Host / Origin validation for localhost binds; in prod we
    # bind 0.0.0.0, so we must supply it ourselves (an MCP-spec SHOULD).
    mcp = FastMCP(
        MCP_SERVER_ID,
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(),
    )

    @mcp.tool(
        description=(
            "Look up an Iowa statute by precise citation. Accepts forms "
            "like '714.16', 'Iowa Code § 714.16', '714.16(2)(a)', or "
            "'Chapter 232'. Returns the current section text plus an "
            "official_url and as_of_date stamp. If the citation does not "
            "resolve unambiguously, returns a list of candidates — never "
            "a silent substitution."
        )
    )
    async def lookup_citation(citation: str) -> dict:
        return await sync_to_async(
            tools.lookup_citation_tool, thread_sensitive=True
        )(citation)

    @mcp.tool(
        description=(
            "Hybrid SEMANTIC search across all Iowa primary law in the corpus — "
            "the Iowa Code, the Iowa Court Rules, AND Iowa CASELAW (appellate "
            "court decisions). Combines full-text + trigram-fuzzy + vector-"
            "semantic retrieval, RRF-fused and cross-encoder reranked. Cases are "
            "matched by topic / holding (semantic), party name, or reporter "
            "citation (e.g. '848 N.W.2d 40'); each case hit also carries a "
            "good-law / treatment flag (e.g. overruled, superseded) so you do not "
            "rely on invalidated precedent. Returns ranked hits with snippets, "
            "official URLs, and an as_of_date stamp. Use this for any natural-"
            "language question of Iowa statutes, rules, or case law; use "
            "lookup_citation when you have a precise statute/rule citation. "
            "(Tool name is 'search_statutes' for backward compatibility, but it "
            "searches statutes, rules, and cases alike.)"
        )
    )
    async def search_statutes(
        query: str, limit: int = 20, use_vector: bool = True
    ) -> dict:
        # rerank=True: external agents act on the top hit, so they get the
        # cross-encoder pass (recall -> precision), not raw RRF order. The chat
        # endpoint calls search_statutes_tool directly with rerank off because it
        # runs its own reranker with body enrichment.
        return await sync_to_async(
            tools.search_statutes_tool, thread_sensitive=True
        )(query, limit=limit, use_vector=use_vector, rerank=True)

    @mcp.tool(
        description=(
            "Return the full version history for a section, ordered "
            "newest first. Each version carries effective_from / "
            "effective_to so the caller can see when the text was in "
            "effect."
        )
    )
    async def get_version_history(section_id: int) -> dict:
        return await sync_to_async(
            tools.get_version_history_tool, thread_sensitive=True
        )(section_id)

    @mcp.tool(
        description=(
            "Return the version of a section that was in effect on the "
            "given date (ISO-8601, YYYY-MM-DD). Useful when an attorney "
            "needs to cite the law as it stood at the time of an event."
        )
    )
    async def get_section_at_date(section_id: int, on_date: str) -> dict:
        return await sync_to_async(
            tools.get_section_at_date_tool, thread_sensitive=True
        )(section_id, on_date)

    @mcp.tool(
        description=(
            "Return all cross-references for a section: outgoing refs "
            "from the current version and incoming refs from other "
            "current sections."
        )
    )
    async def get_cross_references(section_id: int) -> dict:
        return await sync_to_async(
            tools.get_cross_references_tool, thread_sensitive=True
        )(section_id)

    @mcp.tool(
        description=(
            "Find statutory definitions of a term. Optional chapter "
            "filter scopes the search to one chapter (e.g. chapter='232' "
            "for juvenile justice definitions)."
        )
    )
    async def get_definitions(term: str, chapter: str | None = None) -> dict:
        return await sync_to_async(
            tools.get_definitions_tool, thread_sensitive=True
        )(term, chapter=chapter)

    @mcp.tool(
        description=(
            "List sections amended, added, or repealed since the given "
            "date (ISO-8601). Each row tags change_kind as 'new', "
            "'amended', or 'repealed'."
        )
    )
    async def list_recent_amendments(since: str, limit: int = 100) -> dict:
        return await sync_to_async(
            tools.list_recent_amendments_tool, thread_sensitive=True
        )(since, limit=limit)

    @mcp.tool(
        description=(
            "VERIFY / CHECK / AUDIT / VALIDATE / BLUEBOOK every Iowa Code "
            "citation inside a passage of text in ONE call. "
            "Use this whenever the user asks to: verify citations, check "
            "citations, audit citations, validate citations, confirm "
            "citations are accurate, find bad cites, find dead cites, "
            "check whether a brief's cites are still good law, or "
            "bluebook-check a paragraph. "
            "Prefer this over calling lookup_citation N times — this tool "
            "is one round-trip and returns a structured pass/fail per "
            "citation: whether it is currently in force, was repealed, or "
            "never existed in the corpus, plus same-chapter candidates "
            "for misses. Each item has a byte-span into the input so a UI "
            "can highlight problems in place. Input: the paragraph or "
            "brief text. Do not call lookup_citation in a loop for "
            "verification work; call this instead."
        )
    )
    async def validate_citations(text: str) -> dict:
        return await sync_to_async(
            tools.validate_citations_tool, thread_sensitive=True
        )(text)

    @mcp.tool(
        description=(
            "VERIFY / FACT-CHECK quoted statutory language in a passage. "
            "Use whenever the user asks to: check if a quote is accurate, "
            "verify a quotation, confirm the brief actually quotes the "
            "statute correctly, find misquotes, catch paraphrased quotes, "
            "or compare quoted text to what the statute really says. "
            "For each \"...\"-delimited span the tool finds in the input, "
            "it pairs the quote with the nearest citation, then checks "
            "whether the quote appears verbatim in that section's body "
            "text. Returns per-quote status: exact / fuzzy (close but "
            "paraphrased) / not_found / no_citation / section_unresolved, "
            "plus a match_score and the closest_passage from the actual "
            "statute. Pass an explicit citation (second arg) to verify "
            "all quotes against one specific section. Web search cannot "
            "do this — only a parsed corpus can fact-check quoted "
            "language deterministically."
        )
    )
    async def verify_quote(text: str, citation: str | None = None) -> dict:
        return await sync_to_async(
            tools.verify_quote_tool, thread_sensitive=True
        )(text, citation)

    @mcp.tool(
        description=(
            "ONE-CALL FULL BRIEF AUDIT: structural + substantive review "
            "of a passage of legal writing. "
            "Use this for the highest-leverage workflow: paste an entire "
            "brief (yours or opposing counsel's) and get back, in a "
            "single response, every dead citation, every misquote, every "
            "section that has been amended since a given date, and a "
            "summary count of each. Combines validate_citations + "
            "verify_quote + freshness check in one round-trip — strictly "
            "better than calling those tools individually because it "
            "shares parsing work and produces one coherent report. "
            "The optional ``since`` argument (ISO YYYY-MM-DD) flags "
            "post-filing amendments — pass the brief's filing date to "
            "spot statutes that changed after the brief was written. "
            "The response includes a ``tables`` field with pre-rendered "
            "Markdown tables (summary, citations, quotes, amended_since) "
            "— prefer pasting those verbatim over re-formatting the "
            "structured payload. "
            "Use whenever the user says: audit a brief, review a brief, "
            "fact-check a brief, find every problem in this brief, "
            "check this filing, vet opposing counsel's citations."
        )
    )
    async def audit_brief(text: str, since: str | None = None) -> dict:
        return await sync_to_async(
            tools.audit_brief_tool, thread_sensitive=True
        )(text, since)

    return mcp


def _transport_security():
    """Build DNS-rebinding / Host / Origin validation for the HTTP transport.

    The SDK only auto-configures this for localhost binds; a container binds
    0.0.0.0, so we set it explicitly (an MCP-spec SHOULD for any networked
    server). Defaults derive from Django's own ``ALLOWED_HOSTS`` /
    ``CORS_ALLOWED_ORIGINS`` — the hosts already proven correct behind the DO
    edge — and can be overridden per-environment with ``MCP_ALLOWED_HOSTS`` /
    ``MCP_ALLOWED_ORIGINS`` (comma lists).

    Two deliberate behaviors keep this from breaking real traffic:
      * Origin is validated only when *present*, so server-to-server clients
        (mcp-remote, the claude.ai cloud broker, ChatGPT) — which send no Origin
        — always pass; the allowlist matters only once a browser client exists.
      * ``MCP_DNS_REBINDING_PROTECTION=false`` is an escape hatch if the platform
        forwards an unexpected Host header and starts returning 421 on every
        call. Auth still gates every request regardless, so this only relaxes
        the defense-in-depth layer, never the access control.
    """
    import os

    from django.conf import settings as dj
    from mcp.server.transport_security import TransportSecuritySettings

    def _split(raw: str) -> list[str]:
        return [p.strip() for p in raw.split(",") if p.strip()]

    raw_hosts = os.environ.get("MCP_ALLOWED_HOSTS")
    hosts = _split(raw_hosts) if raw_hosts else list(dj.ALLOWED_HOSTS)

    enabled = os.environ.get(
        "MCP_DNS_REBINDING_PROTECTION", "true"
    ).strip().lower() not in ("0", "false", "no", "off")

    # Django's allow-any "*" has no equivalent in the SDK's exact-match host
    # check, so treat its presence as "host validation intentionally off".
    if "*" in hosts:
        enabled = False
        hosts = [h for h in hosts if h != "*"]

    # Accept each host with or without an explicit port: dev is "localhost:8765",
    # but behind the edge it's the bare host on 443. The SDK supports a ":*"
    # port wildcard but not a bare-host fallback, so we add both forms.
    expanded: list[str] = []
    for h in hosts:
        expanded.append(h)
        if ":" not in h:
            expanded.append(f"{h}:*")

    raw_origins = os.environ.get("MCP_ALLOWED_ORIGINS")
    origins = (
        _split(raw_origins)
        if raw_origins
        else list(getattr(dj, "CORS_ALLOWED_ORIGINS", []))
    )

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=enabled,
        allowed_hosts=expanded,
        allowed_origins=origins,
    )


def _with_healthz(app):
    """Wrap an ASGI app so an exact ``GET /healthz`` returns 200 without auth.

    App Platform's HTTP health probe hits the component directly and carries no
    X-API-Key, and FastMCP's ``/mcp`` endpoint is POST-only JSON-RPC — neither is
    a clean liveness signal. We answer the probe here, OUTSIDE api_key_middleware
    and the MCP app. The match is exact (method GET + path ``/healthz``) on
    purpose: a ``startswith`` prefix placed ahead of auth would be an auth-bypass
    surface (e.g. ``/healthz/../mcp`` or anything else sharing the prefix)."""

    async def wrapper(scope, receive, send):
        if (
            scope.get("type") == "http"
            and scope.get("method") == "GET"
            and scope.get("path") == "/healthz"
        ):
            body = b'{"status": "ok"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send(
                {"type": "http.response.body", "body": body, "more_body": False}
            )
            return
        await app(scope, receive, send)

    return wrapper


def _with_origin_lock(app):
    """Wrap an ASGI app so HTTP requests must carry the Cloudflare-stamped
    ``X-Origin-Lock`` header (see core/middleware.py:OriginLockMiddleware —
    same contract, ASGI transport: this component doesn't run the Django
    middleware stack).

    Inert while ``ORIGIN_LOCK_SECRET`` is empty, and the setting is read
    per-request so ``override_settings`` works in tests. Sits INSIDE
    ``_with_healthz`` — the App Platform probe hits the pod directly and never
    transits Cloudflare — and OUTSIDE ``api_key_middleware``, so bypass
    traffic is rejected before it can exercise auth at all."""

    async def wrapper(scope, receive, send):
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return

        from django.conf import settings

        secret = getattr(settings, "ORIGIN_LOCK_SECRET", "") or ""
        if secret:
            supplied = b""
            for raw_name, raw_value in scope.get("headers", []):
                if raw_name.lower() == b"x-origin-lock":
                    supplied = raw_value
                    break
            if not hmac.compare_digest(supplied, secret.encode()):
                body = b'{"error": "forbidden"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await app(scope, receive, send)

    return wrapper


def build_http_app():
    """Construct the production ASGI app: Django-bootstrapped, streamable-HTTP MCP
    wrapped in X-API-Key auth and an auth-exempt health endpoint.

    This is the import target for gunicorn / uvicorn (see
    ``apps/mcp_server/asgi.py``)::

        gunicorn apps.mcp_server.asgi:app -k uvicorn.workers.UvicornWorker

    Stateless + JSON mode (set in ``build_server``) means every worker process
    and every instance can serve any request, so multi-worker / multi-instance
    serving is safe. Layering, outermost first: ``/healthz`` short-circuit →
    ``X-API-Key`` auth → FastMCP streamable-HTTP app (which itself applies the
    transport-security Host/Origin/Content-Type checks)."""
    _bootstrap_django()
    server = build_server()

    from .auth import api_key_middleware

    return _with_healthz(
        _with_origin_lock(api_key_middleware(server.streamable_http_app()))
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apps.mcp_server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve over streamable HTTP instead of stdio.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.http:
        # Build the exact same ASGI app the gunicorn entrypoint serves
        # (apps.mcp_server.asgi:app), so a local --http run exercises auth,
        # /healthz, and transport security identically to prod. uvicorn.run is
        # the dev convenience path; prod uses gunicorn with uvicorn workers
        # (see the run_command in .do/app.yaml).
        import uvicorn

        app = build_http_app()
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        # stdio: a local, trusted subprocess (Claude Desktop's default). No
        # auth/health wrapper — those are HTTP-transport concerns.
        _bootstrap_django()
        server = build_server()
        server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
