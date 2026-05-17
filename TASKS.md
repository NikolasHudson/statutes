# Iowa Legal Corpus — Task List

Roadmap derived from `Iowa_Legal_Corpus_MCP_Project_Brief.docx`. Status reflects what's been built so far.

---

## Done — Foundation

- [x] Django 5 project scaffold at `backend/` with `core/` settings + URLs
- [x] Postgres 16 + pgvector via `docker-compose.yml`
- [x] Email-login custom `User` (no username), `UserManager`, `Tier` choices
- [x] `APIKey` model (8-char prefix + SHA-256 hash)
- [x] Corpus models — `Jurisdiction`, `Source`, `NodeType`, `Node`, `NodeVersion`, `CitationFormat`, `CrossReference`
- [x] Append-only versioning shape with `effective_from` / `effective_to`
- [x] FTS `search_vector` (GIN-indexed) and 1024-dim `embedding` field on `NodeVersion`
- [x] `pg_trgm` and `vector` extensions installed via migration
- [x] Service-layer placeholder (`apps/corpus/services.py`)
- [x] Django admin registered for all corpus + accounts models
- [x] Django Ninja API skeleton (`/api/health`, `/api/docs`)
- [x] CORS configured for Vite dev server (`localhost:5173`)
- [x] Root `.gitignore`, `backend/README.md`, `.env.example`

---

## Phase 1 — Iowa Code ingestion (Tier 1 MVP)

The brief's "immediate next steps" — get one source loaded end-to-end before adding more.

- [x] Get the existing converted Iowa Code JSON from the attorney; commit a sample to `backend/data/samples/` *(probe JSON: 11 chapters, 756 sections)*
- [x] Create `apps/ingestion_iowa_code/` app
  - [x] Raw fetch step (read provided JSON), persist raw input to immutable storage *(`RawIngestion` model + `persist_raw_input()`, sha256-keyed dedupe in `data/raw/`)*
  - [x] Parser: raw → structured node tree, golden-file tested
  - [x] Diff step against current `Node`/`NodeVersion` state → structured changeset
  - [x] Validators: cross-references resolve (warn), every node has heading, no unannounced repeals (>10% threshold), content hashes change only when text changes
  - [x] Service-layer writer: transactional, closes prior `NodeVersion`s, inserts new ones with `review_status="pending"`
- [x] Admin review workflow: approve/reject bulk actions on `NodeVersionAdmin`; `IngestionRun` admin shows changeset summary *(changeset list view per-run can come later)*
- [x] Seed fixtures (data migration `corpus.0003_seed_iowa_code`): `Jurisdiction(iowa)`, `Source(iowa-code)`, `NodeType` rows for title/chapter/section/subsection/paragraph, three `CitationFormat` templates
- [x] Citation parser (`apps/citations/`): handles "714.16(2)(a)", "Iowa Code § 714.16", "I.C. § 714.16", "I.C. 714", "section 1.4", "Chapter 232", alphanumeric chapters like "12C.3"; resolver looks up `Node` via materialized `path`
- [x] Tests: 42 passing — golden-file parser tests, validator unit tests, citation parser table tests, end-to-end ingest/idempotency/amendment/citation-resolution tests against Postgres
- [ ] *(deferred)* Subsection/paragraph node split — Phase 1 keeps the section as the leaf; bodies hold subsection structure verbatim

## Phase 2 — Search

- [x] Populate `search_vector` on every `NodeVersion` write *(Postgres trigger + cascade trigger on `Node.heading` change; weighted A/B for heading/body; backfill UPDATE in migration)*
- [x] Embedding job: queue on `content_hash != embedding_source_hash`, batch via Voyage AI `voyage-law-2` *(`apps/corpus/services/embeddings.py` + `voyage.py` thin client; deterministic `FakeEmbeddingClient` for dev/tests; `manage.py embed_corpus`)*
- [x] HNSW index on `embedding` column *(`vector_cosine_ops`, pgvector defaults)*
- [x] Three retrievers behind `apps/corpus/services.search`:
  - [x] FTS (Postgres `tsvector` via `websearch_to_tsquery`)
  - [x] Trigram fuzzy (`pg_trgm` on `heading` + `body_text`; heading weighted 2x)
  - [x] Vector semantic (pgvector cosine; similarity = 1 - cosine_distance)
- [x] Reciprocal Rank Fusion combining the three (k=60, per-retriever scores preserved on hits)
- [x] Query expansion: cheap LLM call adds Iowa legal terms-of-art before searching *(Anthropic Haiku, no-op fallback if `ANTHROPIC_API_KEY` unset; vector retriever still uses original query)*
- [x] Eval harness: 30 representative attorney queries with expected top-K; track precision@5 across changes *(`manage.py eval_search`; tag breakdown for keyword vs paraphrase vs natural-language)*
- [ ] Decide voyage-law-2 vs cohere embed-v3 legal on the eval set *(needs real API keys — eval harness ready)*

## Phase 3 — API + MCP

- [x] Django Ninja routes (mirror MCP tool surface):
  - [x] `GET /api/lookup/{citation}` — precise, never fuzzy
  - [x] `POST /api/search` — hybrid, top-N candidates
  - [x] `GET /api/sections/{id}/history`
  - [x] `GET /api/sections/{id}/at/{date}`
  - [x] `GET /api/sections/{id}/cross-references`
  - [x] `GET /api/definitions/{term}?chapter=...`
  - [x] `GET /api/recent-amendments?since=...`
- [x] API key auth backend that uses `apps.accounts.models.verify_key` *(`X-API-Key` header via `ApiKeyAuth(APIKeyHeader)`; lazy `last_used_at` updates)*
- [x] Tier-based rate limiting and feature gating *(per-key daily quota in Django cache; Free locked to lookup+search; 429 on quota; `X-RateLimit-*` headers)*
- [x] `apps/mcp_server/` — separate ASGI process importing Django models *(FastMCP-based; stdio default, `--http` opt-in; `python -m apps.mcp_server`)*
  - [x] Tools: `lookup_citation`, `search_statutes`, `get_version_history`, `get_section_at_date`, `get_cross_references`, `get_definitions`, `list_recent_amendments`
  - [x] Every response includes official URL + "as of [date]" stamp + version metadata
  - [x] No silent substitution: ambiguous citations return candidates, never a guess
- [x] Document the install flow *(`apps/mcp_server/README.md` with Claude Desktop config snippet); manual Claude Desktop verification still pending*

## Phase 4 — Tier 2 sources

- [ ] `apps/ingestion_iowa_admin/` — Iowa Administrative Code (IAC)
- [x] `apps/ingestion_iowa_rules/` — Iowa Court Rules (Civ. P., Crim. P., Evidence, Professional Conduct, Local Rules)
  - [x] Probe extractor (`Iowa Court Rules/probe.py` → `probe.json`): 70 chapters, 1,205 rules from per-chapter PDFs
  - [x] Seed migration `corpus.0007_seed_iowa_court_rules`: `Source(iowa-court-rules)`, `NodeType` chapter/rule, three `CitationFormat` rows; reuses Iowa jurisdiction
  - [x] Parser / differ / validators / writer mirroring the Iowa Code app; reuses `RawIngestion`/`IngestionRun` audit trail
  - [x] `manage.py ingest_iowa_rules` — ingested **70 chapter nodes (22 reserved) + 1,193 rule NodeVersions**, all `review_status=pending`; idempotent re-run verified (1,193 unchanged, 0 writes)
  - [x] Comment text folded into versioned body under a `Comment` banner; division/history/pdf-url in `source_metadata`
  - [ ] *(deferred)* 5 non-Rule chapters (3, 48, 61–63: Forms/Canons/Roman-numeral) — chapter nodes created, 0 rules, flagged via validator warning; need a structure-specific parser
  - [ ] *(deferred)* App-specific test suite (golden-file parser + idempotency, mirroring the 42 Iowa Code tests)
  - [x] Approved Run #3's 1,193 versions (status=approved; search_vector populated — live for FTS/trigram)
  - [ ] *(deferred)* Embeddings for the 1,193 rule versions (`manage.py embed_corpus` — needs real embedding API key)
- [ ] Version history UI in admin (timeline view per `Node`)
- [ ] Effective-date awareness for pending amendments (badge/flag in API + MCP responses)
- [ ] Post-session "what changed" digest job

## Phase 5 — Tier 3 (Westlaw killers)

- [ ] CourtListener ingestion for case annotations linking to statutes
- [ ] Jury instructions tied to statutory elements
- [ ] Cross-references to model codes / federal analogs
- [ ] Practice-area packages: landlord-tenant, family law, criminal defense

## Phase 6 — Frontend integration

- [ ] Replace `fakeAssistantReply()` in `frontend/src/App.tsx` with real `/api` calls
- [ ] Auth UI: email/password login, signup, password reset
- [ ] API key management page (issue/revoke)
- [ ] Wire Profile → real user record (`tier`, sources, preferences)
- [ ] Render `Citation[]` from API responses (already typed in `frontend/src/types.ts`)
- [x] Read-only corpus browser: public `/api/browse/*` (sources → chapters → entries → content, approved+current only) + `BrowsePage.tsx` reachable via `#/browse` ("Browse" in Shell AppBar) and the demo App sidebar; fixed a pre-existing `Stack` type error in `Shell.tsx` that broke `tsc -b`

---

## Cross-cutting

- [ ] Celery + Redis (or Django-Q2) for scrape pipelines, embedding jobs, scheduled diffs
- [ ] Redis cache, content-hash keyed
- [ ] CI: run `manage.py check`, migrations, tests, lint on every PR
- [ ] Production deploy target (Render / Fly.io / Railway)
- [ ] Audit log model in `apps/accounts/` (who looked up what; required for "what did the tool return on March 14")
- [ ] Subscription billing (Stripe) wired to `Tier`
- [ ] Attorney disclaimers surfaced in API + MCP responses (Iowa Rule 32:1.1, ABA Op. 512)
- [ ] Free-tier query quota enforcement (Profile UI already shows "142/500 monthly queries")

## Open questions (from the brief)

- [ ] Which embedding model wins on Iowa retrieval evals — voyage-law-2 vs cohere embed-v3 legal?
- [ ] Free-tier scope: current statute lookup only, or also limited search?
- [ ] Pending amendments: show with "effective [date]" badge or hide until effective?
- [ ] Per-attorney vs per-firm API keys? Behavior with shared Claude.ai accounts?
- [ ] Case law annotations: CourtListener or build a parallel pipeline?
- [ ] Iowa State Bar Association partnership — path to ISBA endorsement?

## Distribution / GTM (not engineering, but on the critical path)

- [ ] Recruit 3–5 friendly Iowa attorneys for early feedback
- [ ] Iowa State Bar Association partnership conversations
- [ ] County bar outreach (Polk, Linn, Scott, Johnson)
- [ ] CLE provider relationships
- [ ] "AI for solo attorneys" content marketing
