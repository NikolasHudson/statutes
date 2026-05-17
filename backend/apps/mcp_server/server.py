"""MCP server for the Iowa Legal Corpus.

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
import os
import sys

import django


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

    mcp = FastMCP("iowa-legal-corpus")

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
            "Hybrid search across the Iowa Code (FTS + trigram fuzzy + "
            "vector semantic, RRF-fused). Returns ranked hits with "
            "snippets, official URLs, and an as_of_date stamp. Use this "
            "for natural-language queries; use lookup_citation when you "
            "have a precise citation."
        )
    )
    async def search_statutes(
        query: str, limit: int = 20, use_vector: bool = True
    ) -> dict:
        return await sync_to_async(
            tools.search_statutes_tool, thread_sensitive=True
        )(query, limit=limit, use_vector=use_vector)

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

    _bootstrap_django()
    server = build_server()

    if args.http:
        # FastMCP exposes a streamable_http_app() for ASGI deployment;
        # for a quick local run we use uvicorn directly. Wrap it in the
        # X-API-Key middleware so attorneys' Claude Desktop installs can
        # authenticate against the same key model as the REST API.
        import uvicorn

        from .auth import api_key_middleware

        app = api_key_middleware(server.streamable_http_app())
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
