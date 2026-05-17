# MCP server — Iowa Legal Corpus

Exposes the same surface as the public REST API (`apps/api/`) over the
[Model Context Protocol](https://modelcontextprotocol.io/), so an LLM
client like Claude Desktop can call into it directly.

## Tools

| Tool | What it does |
|---|---|
| `lookup_citation` | Precise citation → current section + version + official URL. Returns candidates if ambiguous, never a guess. |
| `search_statutes` | Hybrid search (FTS + trigram + vector, RRF-fused) across the Iowa Code. |
| `get_version_history` | All versions for a section, newest first. |
| `get_section_at_date` | Version that was in effect on a given date. |
| `get_cross_references` | Outgoing + incoming refs for a section. |
| `get_definitions` | Statutory definitions of a term, optionally chapter-scoped. |
| `list_recent_amendments` | Sections changed since a given date (new / amended / repealed). |

Every response includes `as_of_date` plus `effective_from` / `effective_to`
on each version, and an `official_url` for the section. The brief calls
this out as non-negotiable: clients must be able to see when the text was
current and link back to legis.iowa.gov.

## Run locally

```bash
cd backend

# stdio — local-only, trusted process. No auth required.
DJANGO_SETTINGS_MODULE=core.settings python -m apps.mcp_server

# Streamable HTTP — for hosted access. Gates every request on X-API-Key.
DJANGO_SETTINGS_MODULE=core.settings python -m apps.mcp_server --http \
    --host 127.0.0.1 --port 8765
```

Postgres has to be reachable — the same `DATABASE_URL` as the Django app.

## Auth

The HTTP transport is wrapped in an ASGI middleware (`apps/mcp_server/auth.py`)
that requires an `X-API-Key` header on every request. The key is verified
through `apps.accounts.models.verify_key`, the same code path the REST API
uses. Issue keys at `/#/account` in the frontend.

The stdio transport has no auth — it's a local subprocess that imports the
Django ORM directly, so the only attacker model is "someone who can already
run code on the box." Don't expose the stdio endpoint over a network.

## Claude Desktop install (hosted HTTP server)

Sign in to the frontend at `/#/login`, create a key on the API keys page,
and copy the JSON snippet from the post-creation dialog. It looks like:

```json
{
  "mcpServers": {
    "iowa-legal-corpus": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://your-host/mcp",
               "--header", "X-API-Key:${IOWA_LEGAL_CORPUS_KEY}"],
      "env": {
        "IOWA_LEGAL_CORPUS_KEY": "<the-raw-key>"
      }
    }
  }
}
```

In Claude Desktop, open **Settings → Developer → Edit Config**, paste the
JSON, save, and restart. The seven tools should appear in the message
composer's tool slider. The config file lives at
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS
or `%APPDATA%\Claude\claude_desktop_config.json` on Windows if you'd rather
edit it directly.

Why `mcp-remote`: Claude Desktop's config file only knows how to launch
local stdio servers. `mcp-remote` is a community npx package that runs as
a stdio subprocess and forwards to our streamable HTTP transport,
attaching the `X-API-Key` header on every request. Why the env-var
indirection: Windows Claude Desktop and Cursor have a quoting bug that
mangles spaces in `args`, so the recommended pattern is to keep the value
in `env` and reference it via `${VAR}` (per
[mcp-remote docs](https://github.com/geelen/mcp-remote)).

For **claude.ai web** (Custom Connectors): the corpus does not yet
implement OAuth, so the Custom Connector flow is not supported. Use
Claude Desktop above for now.

## Testing from a Codespace

The backend `/api/config` endpoint auto-detects the forwarded URL from
`CODESPACE_NAME` + `GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN`, so the
frontend snippet generator emits the correct `https://<codespace>-8765.app.github.dev/mcp`
URL without any extra config. Two prerequisites:

1. The MCP HTTP server must be running on port 8765 (see `Run locally`).
2. Port 8765 must be set to **public** in the Codespace ports panel
   (default is private/GitHub-cookie-auth). The X-API-Key still gates
   everything — public visibility just lets Claude Desktop reach the URL
   without a GitHub session cookie:

```bash
gh codespace ports visibility 8765:public -c "$CODESPACE_NAME"
```

## Smoke test

Once installed in Claude Desktop:

> Look up Iowa Code section 714.16 and tell me the headline.

If the tool returns `found: false` with candidates, the section probably
isn't in the corpus yet. Confirm what's loaded with:

```bash
DJANGO_SETTINGS_MODULE=core.settings python manage.py shell -c \
  "from apps.corpus.models import Node; print(Node.objects.count())"
```

## Notes

- Tool implementations live in `apps/mcp_server/tools.py` as plain
  functions so they can be unit-tested without booting the server.
- New tool? Add it to `tools.py`, register it in `server.build_server()`,
  and document it in the table above.
