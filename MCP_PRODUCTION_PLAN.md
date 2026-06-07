# MCP Server Production-Readiness Plan — Iowa Legal Corpus

**Target:** make `backend/apps/mcp_server/` live on DigitalOcean App Platform, enterprise-grade.
**Scope as built:** FastMCP (`mcp[cli]==1.27.2`), 10 tools, X-API-Key ASGI middleware, stdio + streamable HTTP, no MCP component in `.do/app.yaml`, no Redis.
**Verification posture:** Where the dossier's verifier corrected the raw research, I use the verified value. Two facts the research got *wrong* that I rely on below: (1) the current stable MCP spec is **2025-11-25**, not 2025-06-18, and the installed SDK already targets it (`LATEST_PROTOCOL_VERSION='2025-11-25'`); (2) `mcp[cli]==1.27.2` is the **current** SDK, not a stale pin. The largest unresolved item — whether DO's first-party MCP support uses **subdomain routing** rather than the path-based `/mcp` ingress this plan builds on — is **elevated to a P0 blocking decision** (§2a, §6), because it can invalidate the ingress mechanism in §2d.

---

## 1. Current-state assessment

### What exists today (working)
- **A real MCP server, not a stub.** `build_server()` registers **10** tools via `@mcp.tool`, each an `async def` that dispatches sync Django ORM through `sync_to_async(..., thread_sensitive=True)`. No HTTP hop to the REST API — direct ORM. This is a genuinely good design: low latency, testable tool bodies in `tools.py`, and a least-privilege surface (all 10 tools are **read-only** ORM/service queries — no shell, no raw-SQL string building, no write path).
- **HTTP transport is wired correctly for a single process.** `main(--http)` builds `api_key_middleware(server.streamable_http_app())` and runs `uvicorn.run(app, ...)`. The verifier confirmed `streamable_http_app()` returns a Starlette app whose **lifespan** calls `StreamableHTTPSessionManager.run()` (load-bearing), and that `api_key_middleware` is **safe** because it passes the `lifespan` scope straight through (`auth.py:52-54`). So the session manager actually starts.
- **Auth mirrors REST.** `api_key_middleware` requires `X-API-Key`, calls `accounts.verify_key` (sha256 prefix lookup + `revoked_at__isnull=True`), 401s on miss, and stashes the resolved row on `scope["mcp_api_key"]` — the deliberate seam for "rate limiting, audit logging — both deferred for now" (`auth.py:9-11,81`).
- **Durable audit infrastructure already exists** elsewhere: `accounts.AuditEvent` (append-only, indexed, with `record_event()` + structured `security` logger). The MCP path just doesn't use it yet. **Caveat (see §4):** `record_event()` is **request-centric** — it calls `client_ip(request)` and `_user_agent(request)`. The MCP ASGI path has **no Django `request`**, only an ASGI `scope`, so "reuse `record_event()`" requires a scope-adapter, not a drop-in call.

### The honest gaps (specific to this code)
1. **No MCP component in the spec.** `.do/app.yaml` has `statutes`, `docling`, `chat-frontend`, `trace-purge`, `iowa-db`. There is **no MCP service and no `/mcp` ingress route**. `DEPLOY.md:380` explicitly defers it ("MCP server: add as a second App Platform service on its own route"). Going live is genuinely undone.
2. **Single uvicorn process, no worker management.** `uvicorn.run(app)` — one process, no gunicorn, no `--workers`. The Django service runs `gunicorn -w 3` (Dockerfile CMD); the MCP path has nothing equivalent.
3. **Stateful + SSE by default.** `streamable_http_app()` defaults to `stateless_http=False`, `json_response=False`. Per-session state lives in **in-process dicts keyed by `Mcp-Session-Id`** (verifier confirmed against the SDK: a request landing on a different worker/instance gets **404 "Session not found"** and the client must re-initialize). With App Platform's **no sticky sessions**, this means it **cannot scale past `instance_count=1`** as-is. Note the trade discussed in §2b: stateful mode also binds sessions to the authenticating credential (`_session_owners`, 404 on mismatch) — a defense-in-depth property we knowingly give up by going stateless.
4. **No module-level ASGI `app`.** The app is built *only inside* `main()`. There is no `apps.mcp_server.<module>:app` for gunicorn/uvicorn to import — a refactor blocker for multi-worker serving.
5. **No rate limiting, no feature-gating, no audit, no `last_used_at` on the MCP path.** All deferred in comments. REST has `check_rate_limit` / `require_feature` / `FEATURES_BY_TIER` / `TIER_DAILY_QUOTA` (`api/auth.py`); MCP has none of it.
6. **Cross-instance quota/lockout is broken even on REST.** `settings.py` uses `RedisCache` only if `REDIS_URL` is set, else **LocMemCache** (per-process). Prod spec sets **no `REDIS_URL`** → quota is per-process (≈3× with 3 gunicorn workers, resets on deploy) and django-axes degrades to the DB handler. Two LocMem hazards that any ported quota inherits and the §3 plan must account for: (a) counters scatter across **every worker process** (so `--workers 2` already means 2× quota); (b) `LocMemCache` defaults to **`MAX_ENTRIES=300` with culling**, so under load rate-limit counters can be **evicted before the 86,400s TTL**, silently resetting quotas mid-day — `check_rate_limit`'s `cache.incr` is not safe to host on a hot MCP path without a real shared store.
7. **Auth is below the spec baseline for hosted clients.** Flat `X-API-Key` is not OAuth 2.1; the 2025-11-25 spec models a remote MCP server as an OAuth Resource Server. Verified consequence: **claude.ai web Custom Connectors cannot use it** (no UI for a static header/key); only **Claude Desktop via the `mcp-remote` npx shim** works.
8. **README/tool-count drift.** README documents **7** tools ("the seven tools should appear"); the server registers **10** (`get_definitions` is in README; `validate_citations`, `verify_quote`, `audit_brief` are **not**). Also the README's `mcp-remote` config uses `X-API-Key:${...}`, **not** `Authorization: Bearer` — both are accepted by `mcp-remote --header`, but the doc must be precise about which one this server reads (the middleware reads `X-API-Key`).
9. **DoS surface on expensive tools, compounded by a paid external call.** `search_statutes_tool` in `server.py` **hardcodes `rerank=True`** and defaults `use_vector=True` — so *every* agent search is the most expensive path (vector + Voyage cross-encoder over HTTP). It over-fetches a 50-doc pool and ships up to 50 × 8000-char docs to Voyage per call; `audit_brief`/`validate_citations`/`verify_quote` accept **unbounded text**. No per-key throttle, no input caps, no wall-clock ceiling. Because reranking is an **outbound paid Voyage call on every search**, this is simultaneously a DoS vector *and* a direct cost/abuse surface (each agent search = billable egress). (Mitigant: the reranker degrades to Noop/RRF order without `VOYAGE_API_KEY`.)

---

## 2. Go-live on App Platform — concrete plan

### 2a. Co-deploy as its own service component (recommended)
Add MCP as a **second `service`** in the existing app. Rationale: App Platform can't expose two external ports on one component (verified), and a separate component lets you size and scale the MCP server independently of Django while sharing the same managed Postgres and secrets. Do **not** fold it into the Django gunicorn process — WSGI gunicorn can't serve an ASGI streamable-HTTP app, and you want independent failure domains.

**RESOLVED — go path-based at `corpus.nick.law/mcp` (decided 2026-06-07).** The earlier worry was that DO's first-party remote-MCP announcement (HTTP streaming, **subdomain routing**, OAuth 2.1) might *mandate* a subdomain. Verified against DO docs: App Platform supports **both** path-prefix and subdomain (`authority`-match) routing to a component — subdomain routing is a *capability*, **not a requirement**, and applies to DO's own managed MCP product (e.g. `apps.mcp.digitalocean.com/mcp`), not to a self-hosted FastMCP service. So §2d's path-prefix `/mcp` ingress is valid and is the chosen mechanism: it reuses the exact pattern already serving `/api` and `/admin` with **zero new DNS and no new domain entry**, and no MCP client distinguishes a path URL from a subdomain URL. A subdomain (`mcp.nick.law`) remains *possible* (we control the zone) but is strictly more work for no benefit now. **One deferred caveat (P2/OAuth only):** path routing puts the RFC 9728 Protected Resource Metadata at the domain root (`corpus.nick.law/.well-known/oauth-protected-resource…`), which the current `/` catch-all sends to **chat-frontend** — so adding OAuth later needs one extra ingress rule pinning `/.well-known/oauth-protected-resource*` to the MCP (or Django) component. One-line rule, not a blocker, possibly moot if DO ships managed OAuth.

**Coupled-deploy correction.** All components share `branch: main` + `deploy_on_push: true`, and **App Platform deploys the app as a unit.** Adding `mcp` with the same settings means an unrelated frontend or Django commit triggers an MCP redeploy, and a bad MCP change can **fail the whole app deploy**. Do **not** claim "roll the MCP server independently" — that is not how shared-repo `deploy_on_push` works here. Either accept coupled deploys (and drop the independent-rollout claim) or, if independent rollout is required, put MCP on a separate branch / manual deploy trigger. The honest framing: independent *failure domains at runtime* (separate process, separate health), **not** independent deploys.

Keep it **public** (it must be reachable by external MCP clients), unlike `docling` which is internal-only.

### 2b. Code changes in `apps/mcp_server` (do these first — they gate the spec)

**(i) Go stateless + JSON, and expose a module-level ASGI `app`.** This is the single most important change: it removes session affinity entirely (App Platform has none), aligns with the protocol's stated stateless direction, and you lose almost nothing functionally — every tool is a synchronous request/response DB lookup with no sampling/elicitation/progress. (Resumability is already off regardless: the SDK builds the session manager with `event_store=None`.)

**Explicitly weigh the security trade.** Stateful mode binds each session to the authenticating credential (`_session_owners`) and 404s on credential mismatch — defense-in-depth against a stolen/guessed session id being reused under a different key. Going stateless **removes** that per-session credential binding. For *this* server it is an acceptable trade because **every request is independently `X-API-Key`-verified by `api_key_middleware`** before dispatch — there is no session to hijack, so the per-request check fully compensates. Record this as a deliberate decision, not silent upside.

In `server.py`, set the flags on the constructor and expose `app` at module scope so gunicorn can import it:

```python
def build_server():
    ...
    mcp = FastMCP(
        "iowa-legal-corpus",
        stateless_http=True,     # any instance serves any request; no 404-on-wrong-worker
        json_response=True,      # single application/json body, no open SSE stream
    )
    # ... register the 10 tools ...
    return mcp

def build_http_app():
    """Module-level ASGI factory for gunicorn/uvicorn."""
    _bootstrap_django()
    server = build_server()
    from .auth import api_key_middleware
    return api_key_middleware(server.streamable_http_app())
```

Add `backend/apps/mcp_server/asgi.py`:
```python
from .server import build_http_app
app = build_http_app()
```
Keep `main()` for `python -m apps.mcp_server` (stdio for local Claude Desktop) and for `--http` dev runs. Importable target for gunicorn: `apps.mcp_server.asgi:app` (Django setup runs at import).

**(ii) Add a lightweight non-streaming health endpoint — with an exact-match guard.** Do **not** point the health check at `/mcp` (POST-only JSON-RPC; a GET probe there isn't a clean liveness signal). Wrap the ASGI app so a request short-circuits to `200 {"status":"ok"}` **only on `method == "GET"` AND `path == "/healthz"` (exact match)**, *before* the MCP app and *before* `api_key_middleware` (the probe carries no `X-API-Key`). **Do not** use `path.startswith("/health")` or any prefix bypass placed ahead of auth — a loose prefix is an **auth-bypass surface** (path-normalization tricks like `/healthz/../mcp`, or unauthenticated reachability of anything sharing the prefix). Spec it as exact method+path:

```python
async def app(scope, receive, send):
    if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == "/healthz":
        # respond 200 here, before auth and before the MCP app
        ...
    await _authed_mcp_app(scope, receive, send)
```
App Platform's health probe hits the **component directly (pre-ingress)**, so the component must see exactly `GET /healthz`. Ingress `preserve_path_prefix` affects only the public `/mcp` path, not the probe (probes bypass ingress) — but confirm on deploy that the probe path the component receives is `/healthz`, not a prefix-mounted variant.

**(iii) Wire the deferred controls** (covered in §3/§4): per-key rate limit + feature gate + audit + `last_used_at`, all keyed off `scope["mcp_api_key"]` in the middleware.

**(iv) Set transport security explicitly.** The SDK's auto DNS-rebinding protection only kicks in for `127.0.0.1`/`localhost` binds (verifier new-finding). In prod you bind `0.0.0.0` behind the DO edge, so that auto-protection is **off** — set `TransportSecuritySettings` (`allowed_hosts`/`allowed_origins`) to the real public host before calling `streamable_http_app()`, satisfying the spec's Origin-validation MUST. **Why this is P0 despite no browser client yet:** it is *defense-in-depth* for the current server-to-server `mcp-remote` path (no browser Origin is sent), but because the bind is `0.0.0.0` regardless, the Origin-validation MUST applies the moment the service is publicly reachable — we keep it P0 on that basis, not because a browser client exists today.

**(v) `TransportSecuritySettings` ≠ CORS — they are two different things.** Origin validation (above) defends against DNS-rebinding; it is **not** browser CORS. The existing app sets `CORS_ALLOWED_ORIGINS=https://corpus.nick.law` and `CSRF_TRUSTED_ORIGINS` at the **Django** layer — those are **irrelevant** to the MCP Starlette app (a different ASGI app with no Django CORS middleware). State plainly: (a) the MCP app has **no CORS middleware at all**; (b) `mcp-remote`/Claude Desktop are **server-to-server**, so CORS is moot today; (c) any future **browser-based** MCP client (the P2 OAuth/claude.ai-web path) will require a **CORS layer added to the MCP app**, distinct from and in addition to `TransportSecuritySettings`. Do not conflate the two.

### 2c. Run command — gunicorn with uvicorn workers, once stateless

```dockerfile
CMD ["gunicorn", "apps.mcp_server.asgi:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120", \
     "--graceful-timeout", "120", \
     "--access-logfile", "-", "--error-logfile", "-"]
```

**Graceful shutdown / SIGTERM (P1 go-live item — previously missing).** The Django Dockerfile comment explicitly uses JSON exec-form so "gunicorn is PID 1 and gets SIGTERM for graceful drains on redeploy." The MCP run command **must** preserve this:
- It must be **exec-form/argv** (App Platform runs `run_command` **without a shell**, so a string argv is fine) — confirm the MCP gunicorn ends up as **PID 1** and receives SIGTERM on redeploy.
- A reranked `audit_brief` is a **long synchronous ORM + Voyage HTTP call** (many seconds). Stateless+JSON means there is **no SSE stream to drain**, but an in-flight tool call still needs to finish rather than be killed mid-request. Add **`--graceful-timeout`** (above) and confirm in-flight calls drain within App Platform's termination grace period. State the drain behavior explicitly in the runbook.

Why gunicorn `-k uvicorn.workers.UvicornWorker` over bare `uvicorn --workers`: matches the existing Django process model (graceful SIGTERM, PID-1 exec form) and is the dossier's recommended multi-worker command. The hashed lock contains `uvicorn==0.48.0`, `gunicorn==26.0.0`, and `mcp[cli]==1.27.2`, so `-k uvicorn.workers.UvicornWorker` imports cleanly. **This is only correct because we went stateless** — each worker is its own process with its own (now empty) session memory, so round-robin across workers and instances is safe. If you ever need a server-initiated feature (sampling/elicitation) you must revert to stateful, which then forces `instance_count: 1` **and** `--workers 1` (no shared session store exists here).

**Quota multiplication at P0 (reconciled).** Pick one P0 framing and own it. **Recommended: ship `--workers 2` and explicitly own that the per-key quota is already `2×` at go-live** because LocMem counters are per-process (see §1 gap #6 and §3). The alternative — `--workers 1` with no multiplication — is simpler but gives up free in-instance concurrency. Do **not** simultaneously claim `instance_count: 1` is "safe ONLY because stateless" (which implies scale-out intent) while running `--workers 2` and calling quotas "per-process best-effort" — that is three inconsistent statements. The honest P0 statement: *single instance, two worker processes, quota is best-effort and multiplied by `--workers` until Valkey lands (§3).*

**Image strategy.** Reuse the existing `/Dockerfile` (it already installs `mcp[cli]==1.27.2` from the hashed lock and runs as the unprivileged `app` user) and override `run_command` in the spec rather than maintaining a second Dockerfile. **Verify the override actually applies on a `service`:** the established precedent is the `trace-purge` **worker**, which overrides `run_command` on the reused `/Dockerfile` `CMD`. That precedent is a `worker`, **not a `service`**. Historically not every App Platform version cleanly let a `service` with `dockerfile_path` override the Dockerfile `CMD` via `run_command`. **Make this an explicit verification step**, not an assumption — if `run_command` does not override the `service` CMD on the current platform version, fall back to a dedicated `Dockerfile.mcp` with the gunicorn CMD baked in.

**Image-size note (a point *in favor* of reuse).** The Django image deliberately keeps **PyTorch OUT** (per the spec comment, torch lives only in `docling`), and `voyageai` is a thin HTTP client — so the reused MCP image is correctly **small**, and there is **no local-CPU rerank cost** (reranking is an outbound Voyage HTTP call). This both validates reuse *and* feeds the sizing argument in §2d and the cost/DoS argument in §1 gap #9 / §4.

### 2d. The `.do/app.yaml` change (path-prefix routing — decided; see §2a)

```yaml
services:
- name: mcp
  dockerfile_path: /Dockerfile          # reuse the Django image (has mcp[cli], no torch → small)
  source_dir: /
  github:
    repo: NikolasHudson/statutes
    branch: main
    deploy_on_push: true                # NOTE: couples MCP redeploy to every main commit (see §2a)
  run_command: gunicorn apps.mcp_server.asgi:app -k uvicorn.workers.UvicornWorker --workers 2 --bind 0.0.0.0:8080 --timeout 120 --graceful-timeout 120 --access-logfile - --error-logfile -
  http_port: 8080
  instance_count: 1
  instance_size_slug: apps-s-1vcpu-1gb   # SHARED ($12/mo), matching the Django API; see sizing note
  health_check:
    http_path: /healthz                  # NEVER /mcp — that's POST JSON-RPC; exact-match bypass in app
    timeout_seconds: 5
    failure_threshold: 3
```

Add the ingress rule **above** `/` (first-match-wins, top-down):
```yaml
ingress:
  rules:
  - match: { path: { prefix: /mcp } }
    component: { name: mcp, preserve_path_prefix: true }   # FastMCP mounts at /mcp; keep the prefix
  - match: { path: { prefix: /api } }
    component: { name: statutes, preserve_path_prefix: true }
  - match: { path: { prefix: /admin } }
    component: { name: statutes, preserve_path_prefix: true }
  - match: { path: { prefix: / } }
    component: { name: chat-frontend, preserve_path_prefix: true }
```
`preserve_path_prefix: true` is required because `streamable_http_path` defaults to `/mcp` and FastMCP's Starlette app expects to see `/mcp`. Public URL becomes `https://corpus.nick.law/mcp`.

**Sizing rationale (downsized from the prior plan).** The prior plan asserted dedicated `apps-d-1vcpu-1gb` ($34/mo) on a hand-wave ("rerank+ORM bursts / noisy-neighbor") — but **rerank is offloaded to Voyage over HTTP, not local CPU**, and the image has no torch, so the local CPU profile is **light** (ORM + an outbound HTTP call). The primary Django API itself runs on **shared `apps-s-1vcpu-1gb`**. Recommend **starting on shared `apps-s-1vcpu-1gb` ($12/mo)** to match the API, and only moving to dedicated **if observed CPU/latency warrants** — defaulting to dedicated over-provisions by ~$22/mo with no concurrency number to justify it. If you do want dedicated, justify it with a measured concurrent-request target, not a guess.

**Secrets/env:** MCP shares the app-level secrets it needs (`SECRET_KEY`, `DATABASE_URL`, `VOYAGE_API_KEY`, `DATABASE_SSLMODE=require`, `ALLOWED_HOSTS`) by inheriting app-level `envs` — same image, same Django settings. **`VOYAGE_API_KEY` is load-bearing and a cost surface:** inheriting it means the MCP service makes a **paid Voyage rerank call on every `search_statutes`** (rerank is hardcoded `True` in `server.py`) — tie this to the §4 input-cap/tiering work, not just list it. **Do not re-paste secrets**; honor the documented foot-gun (apply from the **live** spec carrying `EV[...]`, never from this human-readable file — a valueless `type: SECRET` wipes the value). When you add `REDIS_URL` (§3), declare it once at app level so Django, MCP, and the worker all see it.

### 2e. SSE / streaming-timeout risk at the DO edge — and why JSON sidesteps it
App Platform fronts apps with **Cloudflare**, which enforces a **~100s edge timeout** (DO staff figure; Cloudflare's own current default is documented as **120s**). The verifier's correction: it is **not documented** that this resets per-byte — treat it as "a silent gap longer than the limit → 524." **By choosing `json_response=True` we avoid the entire SSE/edge-cache problem:** responses are single `application/json` bodies (POST), which "work even with caching enabled" per DO's edge docs, so we do **not** need `disable_edge_cache: true` and do **not** need a custom-domain edge-cache exception. The only remaining edge constraint is that **any single tool call must return within ~100s** — relevant only to `audit_brief`/reranked `search` on a huge brief, which §4's input caps + wall-clock ceiling keep well under the limit. Flipping to `json_response` changes only the transport/content-type — it does **not** change **protocol-version negotiation** (§4). (If you ever revert to SSE, you'd need `disable_edge_cache: true` at the **top level** — app-wide, no per-route toggle — plus the custom domain, which you already have.)

---

## 3. Auth & access

### Now: keep X-API-Key (works today for Claude Desktop via `mcp-remote`)
Verified reality: the Claude API `mcp-connector`, ChatGPT Developer Mode, and `mcp-remote` all accept a developer-supplied header; **claude.ai web/Desktop Custom Connectors do not** expose a static-key/header field (open feature request `anthropics/claude-ai-mcp#112`). So for the current single-maintainer/attorney audience, **keep `X-API-Key`** and document the `mcp-remote` config precisely — the server reads the **`X-API-Key`** header (not `Authorization: Bearer`), and the README's 7→10 drift must be fixed (§1 gap #8). Treat `mcp-remote` as **transitional** and call out the **`Authorization:${AUTH_HEADER}` space-quoting workaround** (Windows Desktop/Cursor mis-split args on spaces). Operational caveat for onboarding docs: a Dec-2025 Claude Desktop release regressed Custom-Connector OAuth (`#5`) — the `mcp-remote` header path is the durable fallback.

### What OAuth 2.1 unlocks, and the effort
Implementing the full **2025-11-25 auth path** (server as OAuth Resource Server: `/.well-known/oauth-protected-resource` PRM per RFC 9728; RFC 8707 audience validation on every token; PKCE S256; CIMD or DCR for client registration; 401 + `WWW-Authenticate` — now **optional** with `.well-known` fallback in 2025-11-25) unlocks **claude.ai web/mobile Custom Connectors** and ChatGPT connectors with per-user identity. This is a **Large** effort: you have **no Authorization Server** today (OpenAI is the LLM provider; there's no IdP). You'd either stand up/co-host an AS or adopt a hosted one. **Do not pass the inbound MCP token through to OpenAI** — the spec forbids token passthrough; mint a separate server-side credential. Recommendation: **defer OAuth to P1/P2**, and if you need Claude integration sooner without the claude.ai UI, use the **Claude Messages API `mcp-connector`** (your server keeps X-API-Key; the caller passes it as `authorization_token` per server — no DCR/PRM needed on your side). **Reconcile with §2a/§6:** if DO ships **managed OAuth** as part of its first-party MCP support, this Large effort may collapse substantially — confirm before building.

### Mirror the REST tier model onto MCP (and the Valkey prerequisite)
Port `require_feature` / `check_rate_limit` into `api_key_middleware`, keyed off `scope["mcp_api_key"]`, evaluated **before dispatch** (return JSON-RPC-shaped 429/403). Map tools → existing feature names (`lookup`→`lookup_citation`; `search`→`search_statutes`; `validate`→`validate_citations`/`verify_quote`/`audit_brief`; `history`/`at_date`/`cross_refs`/`definitions`/`amendments`→the corresponding tools). Also update `last_used_at` (lazy, once/min, exactly as REST does).

**Tie tiering to the actual tool behavior.** `search_statutes` in `server.py` **hardcodes `rerank=True`** and defaults `use_vector=True`, so every agent search is the **most expensive** path (vector + paid Voyage rerank). "Cap the rerank pool by tier" is not enough — for cheaper tiers the gate should **force a cheaper path** (e.g. **FREE tier → `rerank=False`**, and/or `use_vector=False` to match the browse path noted in memory). Name the hardcode when implementing: the clamp must be able to override the `rerank=True` literal per tier, not just shrink the pool.

**Valkey is a hard prerequisite for correct cross-instance quota/lockout — and split the effort.** Today `CACHES` falls back to LocMem without `REDIS_URL`, so any quota is per-process, multiplies by `workers × instances`, **resets on deploy**, and can be **evicted before its TTL** under `MAX_ENTRIES=300` culling (§1 gap #6). On App Platform, Valkey **cannot be a $7 dev DB** (those are Postgres-only) — it must be an **attached managed Valkey cluster** (`databases:` engine `VALKEY`, ~$15/mo single-node dev, ~$60/mo HA), with its connection string injected as a `SECRET RUN_TIME` env (`REDIS_URL`). **Effort split (corrected):** *attaching* Valkey + the `databases:` entry + one env is **S** (trivial infra); the **M** is the **dependent work** — porting `check_rate_limit`/django-axes onto a shared store, verifying cross-instance correctness, and testing the eviction/TTL behavior that LocMem silently broke. Until Valkey lands, pin **`instance_count: 1`** and document that quotas are per-process best-effort **and already `×--workers`** at go-live.

---

## 4. Enterprise hardening

**Security controls**
- **Input validation / DoS limits on expensive tools.** Cap `text` length in `validate_citations`/`verify_quote`/`audit_brief`; cap `query` length and **clamp `limit`** in `search_statutes` before it reaches `hybrid_search`/Voyage; cap the rerank pool by tier **and** allow forcing `rerank=False`/`use_vector=False` per tier (against the `rerank=True` hardcode, §3); add a **wall-clock ceiling** on the reranked path and **fail closed to RRF order** (the Noop reranker already does this) on timeout. This stops one caller pinning the cross-encoder, **bounds the per-call Voyage spend**, and keeps every call under the ~100s edge timeout (§2e).
- **Tool-call audit logging → `AuditEvent` (with an explicit ASGI-scope adapter).** Wrap the single `sync_to_async` dispatch with one decorator so all 10 tools are covered uniformly. Log per call: timestamp, resolved key/user/tier, tool name, **argument SHAPE not raw text** (lengths/counts — `audit_brief` text is privileged attorney work product), result summary, latency, decision (allowed/429/403). **Two concrete corrections to "reuse `record_event()`":**
  - **Adding the enum member needs no migration.** `AuditEvent.Event` is a `TextChoices` and `event_type = CharField(max_length=32)`; `MCP_TOOL_CALL` is 12 chars (fits) and adding a `TextChoices` member is a **DB-less code change** — no migration required. Do not imply otherwise.
  - **`record_event()` is request-centric and the MCP path has no Django `request`.** It calls `client_ip(request)` / `_user_agent(request)`; MCP has only the ASGI `scope`. Build an explicit **scope-adapter sub-task**: extract client IP, user-agent, and the resolved actor from `scope` (the actor is an `APIKey`, **not** a Django `User`, so resolve actor identity from `scope["mcp_api_key"]`), then either feed a synthetic request-like object to `record_event()` or add a parallel `record_event_from_scope()` code path. Do not present this as a drop-in reuse.
  This closes OWASP **MCP08** (Lack of Audit & Telemetry) and feeds the existing SOC2 workstream.
- **Tool-description integrity (line-jumping / tool-poisoning discipline).** Descriptions enter the model's context at `tools/list` and *are* behavior. These descriptions are unusually long/imperative (`validate_citations`: "Do not call lookup_citation in a loop; call this instead"). Add a test that **hashes each tool's name + JSON schema + description** and fails CI on unintended change (rug-pull discipline), and keep them **ASCII-only / strip control + zero-width chars** so no ANSI/Unicode payload can ride along.
- **Supply-chain pinning.** `mcp[cli]==1.27.2` is the **current** SDK, pinned **with hashes** under `--require-hashes` — already strong. Add it to Dependabot + SBOM. **`mcp-remote` caveat:** it is a community shim and **CVE-2025-6514** (CVSS 9.6 OS-command-injection RCE) hit `mcp-remote ≤ 0.1.15`. Document that **this deployment does not ship `mcp-remote`** (it runs client-side); if onboarding docs recommend it, require **`>= 0.1.16`** and HTTPS-only.
- **Least-privilege invariant.** All 10 tools are read-only ORM/service calls — no shell, no raw SQL, no write/arbitrary-path. Document this as an explicit invariant and add a guard/test so no future tool introduces a write/shell without review (neutralizes OWASP MCP04/MCP05; bounds MCP10).

**Observability** — emit OpenTelemetry using the **official MCP semantic conventions**. Verifier warning: these `mcp.*`/`gen_ai.*` attributes are **"Development"** stability — gate behind `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` and **pin a semconv version** (version churn risk). **Check first** whether the installed FastMCP exposes **native telemetry** before hand-rolling. One wrapper at the shared dispatch: span `tools/call <tool>`, attrs `mcp.method.name='tools/call'`, `gen_ai.tool.name`, `gen_ai.operation.name='execute_tool'`, `mcp.protocol.version`, `network.transport='tcp'`; a duration histogram + calls/errors counters; **never** raw inputs/outputs. (Effort is **M** but carries a spike for the FastMCP-native check + semconv pinning — not a clean M.)

**Data governance / retention** — outputs are public statute/case text (low PII). **Inputs are the hotspot**: pasted brief text in `audit_brief`/`validate_citations`/`verify_quote` can be client-confidential/privileged. Guarantee **no raw-input logging** (shape only), document a retention stance, and confirm the **OpenAI 30-day/ZDR** posture for any LLM path (repo uses `OPENAI_API_KEY`).

**Versioning the tool surface & protocol negotiation** — advertise the negotiated protocol version (2025-11-25 family) in README. **Specify the server's negotiation/fallback behavior explicitly** (go-live spec, not just Inspector): clients MUST send `MCP-Protocol-Version` on post-init requests; the server SHOULD assume **`2025-03-26`** when the header is absent and **return 400 on an unsupported version**. Flipping to `json_response` does **not** change this negotiation. For your own tools adopt **additive-only** evolution (never rename/retype a param in place — cached client tool defs break **silently**); ship `<tool>_v2` alongside the old and deprecate with a migration window.

**Testing** — `tests/test_tools.py` already has a name-presence contract test (`test_all_tools_registered` asserts the exact 10-name set) — keep it; **add a full schema/description snapshot gate** (params + descriptions, not just names). Add an **MCP Inspector** smoke step against the deployed `https://corpus.nick.law/mcp` as explicit **pass/fail** checks: (1) initialize handshake; (2) capability advertisement; (3) a `tools/call` returning `application/json`; (4) **`MCP-Protocol-Version` present → accepted, absent → server assumes `2025-03-26`, unsupported → 400** (verify the 400 path, don't just "handle" the header); (5) Origin 403 with a disallowed Origin. Add a **stateless+JSON end-to-end test** since flipping to JSON changes the content-type and drops session-id round-tripping that older tests may assume.

---

## 5. Prioritized roadmap

**P0 — blocks go-live**
- **Ingress shape — DECIDED: path-prefix `corpus.nick.law/mcp`** (App Platform supports both path and subdomain routing; path reuses the proven `/api`+`/admin` pattern, zero new DNS). No longer a blocker; §2d is valid as written.
- **Stateless + JSON + module-level `app`** (`build_http_app()`/`asgi.py`) — **M** — required to serve via gunicorn workers and to be safe behind App-Platform's no-affinity LB; record the per-session credential-binding trade given up.
- **`/healthz` non-streaming endpoint, exact `GET /healthz` match, auth-bypassed** — **S** — must not be a path-prefix bypass (auth-bypass surface).
- **Add `mcp` service + ingress rule to `.do/app.yaml`** — **S** — reuse Django image; **verify `run_command` overrides the `service` CMD** (worker precedent ≠ service) or add `Dockerfile.mcp`; **shared `apps-s-1vcpu-1gb`** (not dedicated); `instance_count: 1`. Own that `deploy_on_push` couples MCP to every main commit (no independent rollout).
- **gunicorn `-k uvicorn.workers.UvicornWorker` run command, exec-form, `--graceful-timeout`** — **S** — production process model; PID-1 SIGTERM drain for in-flight reranked calls; valid only post-stateless. Decide `--workers` and own the quota multiplication it implies.
- **Explicit `TransportSecuritySettings` for the public host** — **S** — `0.0.0.0` bind disables the SDK's auto Origin protection; P0 because the bind is public regardless, even with no browser client yet.
- **Fix README tool-count drift (7→10) + precise `X-API-Key` `mcp-remote` config** — **S** — correctness for the only working client today.

**P1 — before external/enterprise customers**
- **Attach managed Valkey + `REDIS_URL`** — **S (infra)** — `databases:` entry + one env (trivial); fixes REST too.
- **Port rate limit + feature gate + `last_used_at` onto MCP middleware (verify cross-instance correctness + eviction)** — **M** — the real cost is correctness/eviction testing, not the infra; tie tiering to the `rerank=True` hardcode.
- **Tool-call audit logging to `AuditEvent` (+ `MCP_TOOL_CALL` TextChoices member, no migration; ASGI-scope actor/IP/UA adapter, shape-only)** — **M** — OWASP MCP08 / SOC2.
- **Input caps + wall-clock/cost ceiling on `search`/`audit_brief` (+ per-tier `rerank`/`use_vector` override)** — **M** — DoS + Voyage cost control + keeps calls under the edge timeout.
- **OTel instrumentation (official MCP semconv, pin version + `OTEL_SEMCONV_STABILITY_OPT_IN`; check FastMCP-native first)** — **M (with spike)** — per-tool metrics/tracing/alerting; version-churn risk.
- **Protocol-version negotiation behavior (absent → `2025-03-26`, unsupported → 400) + Inspector pass/fail smoke + schema/description snapshot test** — **S** — go-live correctness, catches silent tool-surface drift.
- **Tool-description ASCII-only + hash-pin test** — **S** — line-jumping/rug-pull discipline.

**P2 — nice-to-have**
- **OAuth 2.1 Resource Server (PRM/RFC 9728, RFC 8707 audience, PKCE, CIMD/DCR)** — **L** — unlocks claude.ai web/mobile + ChatGPT connectors; needs an AS you don't have yet (may collapse if DO ships managed OAuth — §2a/§6). Browser clients here also require **adding a CORS layer to the MCP app** (§2b-v).
- **Per-tenant dynamic tool filtering** — **M** — out-of-scope tools never reach the model.
- **Output shaping / pagination + fetch-by-id** — **M** — for caselaw bodies vs client output caps.
- **Autoscale MCP `instance_count > 1`** — **S** — safe once stateless + Valkey land.

---

## 6. Open questions / things to confirm
- **DO's first-party "Remote MCP Server Deployment" capability — RESOLVED for routing (§2a).** Verified: App Platform supports both path and subdomain (`authority`) routing; subdomain is optional, so path-based `corpus.nick.law/mcp` is valid and chosen. Still worth tracking: DO's managed MCP product may offer **managed OAuth**, which could collapse the P2 OAuth effort — confirm before building §3's OAuth path.
- **Does `run_command` override the Dockerfile `CMD` on a `service` (not just a `worker`) on the current App Platform version?** The `trace-purge` precedent is a *worker*. If `service` override is unreliable, ship `Dockerfile.mcp`. Verify on first deploy.
- **Exact DO edge streaming/idle timeout.** ~100s (DO-staff-attributed-to-Cloudflare); Cloudflare's documented default is **120s**; "resets per-byte / idle-not-wall-clock" is **not** documented. With `json_response=True` this is only a **per-call wall-clock budget** — confirm `audit_brief` on a large brief returns under it via a deploy test or DO support.
- **Health-probe path the component receives.** Confirm the App Platform probe hits the component pre-ingress at exactly `GET /healthz` (probes should bypass the `/mcp` prefix mount, but verify).
- **Whether the installed FastMCP exposes native OpenTelemetry.** If so, prefer it over a bespoke decorator (check before P1 OTel work).
- **Does any tool path send input off-box (OpenAI/Voyage)?** Confirm ZDR/30-day posture for inputs that may contain privileged brief text (governance §4).
- **OAuth AS decision.** If P2 OAuth is pursued: co-host an AS, adopt a hosted IdP, or rely on **DO's managed OAuth** — unresolved and architecturally significant; coupled to the first bullet.

**Key file paths:** `/home/dev/statutes/backend/apps/mcp_server/server.py` (build_server, `main`, needs module-level `app`; `search_statutes` hardcodes `rerank=True`), `/home/dev/statutes/backend/apps/mcp_server/auth.py` (the rate-limit/audit/feature-gate seam at `scope["mcp_api_key"]`), `/home/dev/statutes/backend/apps/mcp_server/tools.py` (input-cap + rerank-ceiling targets), `/home/dev/statutes/backend/apps/mcp_server/README.md` (7→10 drift, `X-API-Key` config), `/home/dev/statutes/.do/app.yaml` (add `mcp` service + ingress; confirm path vs subdomain first), `/home/dev/statutes/Dockerfile` (reusable image; verify `service` `run_command` override), `/home/dev/statutes/backend/apps/api/auth.py` (REST tier model to mirror), `/home/dev/statutes/backend/apps/accounts/audit.py` (`record_event` is request-centric → needs scope-adapter; `AuditEvent.Event` TextChoices add = no migration), `/home/dev/statutes/backend/core/settings.py` (REDIS_URL→CACHES LocMem fallback + Django-layer CORS/CSRF that does NOT cover the MCP app), `/home/dev/statutes/DEPLOY.md:380` (the deferred MCP note this plan closes).
---

## 7. Client-compatibility verification (re-run) — addendum

The `client-compat-ops` adversarial verifier died on a transient `API Error: Overloaded` during the workflow and was re-run standalone. **All 5 client-compatibility claims were independently CONFIRMED** against primary sources (Anthropic support docs, `geelen/mcp-remote` README, `anthropics/claude-ai-mcp#5`, modelcontextprotocol.io, OpenAI developer docs). Three material findings from the re-run are not captured above and refine §3/§5:

- **No network allowlisting for claude.ai web/mobile.** Custom Connectors are brokered from **Anthropic's cloud** and "must be reachable from Anthropic's IP ranges." A remote MCP server therefore **cannot be IP-allowlisted to the firm's office/VPN** and still work on claude.ai web/mobile. Tenant/identity isolation must be enforced **inside the server via the OAuth token**, not by network ACLs. (`mcp-remote` on Desktop is the only path that originates from the user's own machine — so header-auth + network controls remain viable *only* for the Desktop/`mcp-remote` route.)
- **Team/Enterprise onboarding dependency.** Only org **Owners** can add a custom connector for Team/Enterprise plans; members then authenticate individually. Per-lawyer self-serve rollout is only possible on Free/Pro/Max; a firm-wide deployment requires the Workspace Owner to add it first — a real admin/onboarding gate to document.
- **Free plan = exactly one custom connector.** A lawyer on the Free plan can attach the statutes server but nothing else; multi-connector use requires Pro/Max/Team/Enterprise.

Minor confirmations: the ChatGPT **~5000-token cap is per individual tool** (name+description+input schema combined, not aggregate) — relevant given this server's unusually long tool descriptions (§4 tool-description discipline); current MCP spec revision is **2025-11-25** (matches §1).
