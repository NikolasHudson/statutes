# Iowa Legal Corpus — System Briefing for Analysis

**Purpose of this document:** a self-contained description of (1) how the system is
built today, (2) the changes we propose, and (3) the end goal — written so an analyst
with repo access but no prior context can review it. File references use
`path:line` form. Date of writing: 2026-05-31.

---

## 0. What the product is

A legal-research tool for Iowa attorneys. It ingests primary legal sources, stores them
as a versioned, searchable corpus, and answers natural-language legal questions through
an LLM that is constrained to cite only retrieved source text. It exposes the corpus
three ways: a REST API (Django Ninja), an MCP server (for Claude Desktop etc.), and a
Next.js chat frontend.

**Current focus:** the **Iowa Court Rules** source only (`iowa-court-rules`). Iowa Code
is already ingested and live but is not the active work. Other sources (Admin Code, case
law) are future tiers.

**Non-negotiable product requirement:** answers must be *precise* and must not fabricate.
Every cited rule number, quoted passage, effective date, and URL must trace to retrieved
source text. Wrong legal answers are the primary risk to manage.

---

## 1. How it is built today

### 1.1 Stack
- **Backend:** Django 5, Postgres 16 + `pgvector`, Django Ninja API. `backend/`
- **Search:** Postgres full-text (`tsvector`), `pg_trgm` trigram, `pgvector` cosine;
  Voyage AI for embeddings (`voyage-law-2`) and reranking (`rerank-2`).
- **Answer LLM:** OpenAI (default `gpt-5-mini`) via a server-side tool-calling loop.
- **Frontend:** Next.js + assistant-ui. `chat-frontend/`
- **Deploy:** DigitalOcean App Platform (`/.do/app.yaml`, `DEPLOY.md`).

### 1.2 Data model — `backend/apps/corpus/models.py`
Hierarchy is **data, not code** (so a new source doesn't need new tables):
- `Jurisdiction` → `Source` → `NodeType` (one row per hierarchy level) → `Node`.
- `Node` is a structural unit (a chapter, a rule, a section). It has a materialized
  `path` (e.g. `32:1.10`), a `heading`, and `source_metadata` (JSON).
- `NodeVersion` is **append-only** content for a Node: `body_text`, `effective_from`/
  `effective_to`, `content_hash`, `search_vector` (FTS), `embedding` (1024-dim vector),
  and `review_status` (pending/approved/rejected). Amendments close the current version
  (`effective_to`) and insert a new one.
- `CrossReference`, `CitationFormat` round out the model.

**Key fact for analysis:** today the unit of embedding, search, and versioning is the
**whole rule** — one `NodeVersion` per rule, holding rule prose *and* official commentary
concatenated together (see 1.3). There is no sub-rule / chunk granularity.

### 1.3 Ingestion pipeline (Court Rules path)
Five stages, each a separate module. The first is a standalone script; the rest live in
`backend/apps/ingestion_iowa_rules/`.

```
PDF → probe.py → probe.json → parser.py → differ.py → validators.py → writer.py → DB
                                                                          ↓
                                                              review_status="pending"
                                                              (human approval gate)
```

1. **Extraction — `Iowa Court Rules/probe.py`** (standalone, uses `pdfplumber`).
   Reads one PDF per chapter (70 chapters), strips repeating page headers via regex, and
   reconstructs structure heuristically: distinguishes table-of-contents lines from body
   lines, peels ALL-CAPS division banners, and **splits rule prose from official
   commentary at a literal `"Comment"` line** (`probe.py:581`). Emits `probe.json`
   (70 chapters, 1,205 rules) as a stable intermediate artifact. Text is flattened — **no
   page coordinates / bounding boxes are retained.**
2. **Parse — `parser.py`** (pure, golden-file testable). `probe.json` → typed node tree.
   Concatenates prose + commentary into one `body_text` under a `\n\nComment\n\n` banner
   (`parser.py:91`). Computes `content_hash` over normalized combined text.
3. **Diff — `differ.py`** (pure). Compares parsed tree to current DB state →
   added / amended / unchanged / repealed. Uses `content_hash` equality to detect changes.
4. **Validate — `validators.py`** (pure). Aborts on: missing heading, duplicate path,
   a repeal wave >10% of in-scope rules, or content-hash drift (unchanged rule whose hash
   moved, or "amended" rule whose hash didn't). Warns on content chapters that parsed
   0 rules.
5. **Write — `writer.py`** (only module that mutates the corpus, single transaction).
   Creates/updates Nodes, closes prior versions, inserts new `NodeVersion`s as
   **`pending`**. Nothing is visible to search/answers until a human approves it in the
   Django admin.

**Audit trail:** `RawIngestion` (immutable hash-keyed copy of every raw input) and
`IngestionRun` (per-run changeset summary) — shared with the Iowa Code app.

### 1.4 Retrieval — `backend/apps/corpus/services/`
- `search.py` — three retrievers over **current, approved** `NodeVersion`s:
  `fts_search` (tsvector), `trigram_search` (pg_trgm on heading only), `vector_search`
  (pgvector cosine). Fused with **Reciprocal Rank Fusion** (`RRF_K=60`). Source-scoped.
- `rerank.py` — optional Voyage cross-encoder (`rerank-2`) reorders candidates by
  relevance to the query. **Falls back to a no-op (RRF order) when `VOYAGE_API_KEY` is
  unset.**
- `embeddings.py` — embeds `heading + body_text` per NodeVersion; re-embeds when
  `content_hash != embedding_source_hash`. **No-op without a Voyage key; `embedding IS
  NULL` rows are skipped by `vector_search`.**
- `query_expansion.py`, `lookups.py` (precise citation resolution, quote verification,
  definitions, history).

### 1.5 Answer layer — `backend/apps/api/chat.py`
A server-side OpenAI **tool-calling loop** (`run_chat_turn` / `run_chat_turn_stream`):
- Exposes 7 read tools to the model: `lookup_citation`, `search_statutes` (enriched with
  rerank + per-hit body excerpts up to ~9k chars for top hits), `get_version_history`,
  `get_section_at_date`, `get_cross_references`, `get_definitions`,
  `list_recent_amendments` (`chat.py:192`).
- A long **system prompt** (`chat.py:340`) enforces grounding *by instruction*: never
  state a number/date/amount not in a tool result; don't claim a rule governs a
  sub-question its text doesn't address; keep black-letter vs Comment distinct;
  mandatory-vs-permissive ethics checks; per-sub-question coverage for multi-issue asks.
- Quota gates (per-user daily, global monthly) protect spend. Every turn's tool trace is
  persisted for audit (`trace_capture.py`).

**Important gap (see §2.B):** the codebase also has **deterministic verification tools** —
`verify_quote_tool` (does a quoted passage actually appear in its cited rule?) and
`validate_citations_tool` (does a citation resolve / is it still good law?) in
`apps/mcp_server/tools.py:419,346`. **These are NOT wired into the chat loop.** Grounding
of chat answers is therefore prompt-only (probabilistic), with no hard post-generation
check.

### 1.6 Frontend — `chat-frontend/`
Next.js + assistant-ui chat. Streams answers from `/api/chat/stream`, renders the tool
trace as source cards. There is **no PDF viewer** and no source-highlighting today.

### 1.7 Current corpus state (Court Rules)
- 70 chapters, 1,193 rule `NodeVersion`s ingested and **approved** (live for FTS/trigram).
- **22 reserved** chapters (placeholders, no content).
- **5 content chapters parse to 0 rules** (ch 3 Forms, 48 Canons, 61–63 Roman-numeral
  standards) — different document structures the `Rule N.M` extractor doesn't handle;
  flagged as warnings, their rules are **absent from the corpus**.
- Per `TASKS.md`, embeddings for the 1,193 versions were **deferred pending a real Voyage
  key** — so semantic retrieval + rerank may currently be inactive for Court Rules in any
  environment without that key.

---

## 2. Proposed changes

Two tracks. Track A is a processing rework (already scoped in
`COURT_RULES_DOCLING_PLAN.md`). Track B is a set of precision fixes, some independent of A.

### Track A — Docling + chunking + PDF highlighting
Four decisions (all confirmed):
1. **Docling replaces pdfplumber** as the extractor. Docling produces structured content
   **plus provenance** (page number + bounding boxes), enabling (a) structural — not
   regex — separation of black-letter from commentary, (b) text-fidelity verification
   against the PDF, and (c) the coordinates needed for highlighting. Also a path to the
   5 currently-unparsed chapters.
2. **New `Chunk` model** (FK → `NodeVersion`): each rule's body and comment fan out into
   chunk rows, each with its own embedding + provenance (page + bbox). Versioning and
   citation semantics stay on `NodeVersion`.
3. **Highlight in the original PDF**: the frontend renders the source PDF and highlights
   the matched rule/comment span using stored provenance.
4. **Embed chunks; the rule is the result**: retrieval ranks chunks, then groups/dedupes
   to the parent rule and surfaces the best-matching chunk as the highlight span.

Workstreams: (A) docling probe → `probe.json` v2 with provenance; (B) `Chunk` model +
migration; (C) chunking service + writer hook; (D) embeddings over chunks; (E) chunk-level
retrieval that returns rules; (F) frontend PDF viewer with highlight overlay. Full detail
in `COURT_RULES_DOCLING_PLAN.md`.

### Track B — Precision fixes (ranked by leverage)
1. **Deterministic verification gate in chat** *(independent of Track A; highest leverage)*
   — run `validate_citations` + `verify_quotes` over the model's drafted answer and
   auto-flag/strip any citation or quote that doesn't resolve or doesn't appear in its
   cited rule, *before* it reaches the user. Converts grounding from "model promises" to
   "system checks." Tools already exist (§1.5).
2. **Confirm API keys in prod + embed the 1,193 rule versions** — without `VOYAGE_API_KEY`
   the system silently degrades to keyword-only retrieval with no rerank.
3. **Docling extraction** (Track A) — fixes the precision ceiling at the source.
4. **Chunking + comment/black-letter split** (Track A) — fixes embedding dilution where a
   short rule's vector is dominated by a long attached comment.
5. **Relevance floor + explicit abstain path** — today search always returns something and
   a final-round nudge forces a best-effort answer; add a threshold below which the honest
   output is "no governing rule found."
6. **Eval harness as a deploy gate** — `manage.py eval_search` and the `probe_chat`
   command + `chat_eval_court_rules.json` exist; turn them into a golden
   question→expected-citation regression gate that blocks on precision drop.

---

## 3. End goal

A legal-research assistant for Iowa Court Rules that is **precise enough for an attorney to
rely on**, specifically:

- **Faithful corpus.** Every rule (including the 5 currently-unparsed chapter types) is
  extracted with verified fidelity to the official PDF; black-letter text and official
  commentary are cleanly separated and independently addressable.
- **Precise retrieval.** A natural-language question returns the *governing* rule, not a
  keyword-adjacent one — driven by chunk-level semantic retrieval + cross-encoder rerank,
  with an honest "not found" when nothing is on point.
- **Verifiable answers.** Every citation and quoted passage in an answer is
  deterministically checked against the corpus before display; unverifiable claims are
  flagged or removed, not shown as fact.
- **Source transparency.** The user can click a cited rule and see it **highlighted in the
  official PDF**, with the correct "as of" date and official URL — so the answer is not
  just plausible but auditable back to the primary source.
- **Regression-proof.** A golden eval gate prevents precision from silently regressing as
  the corpus and pipeline evolve.

---

## 4. Open decisions (input wanted from the analysis)

1. **Iowa Code coexistence — undecided.** Iowa Code is live on the whole-NodeVersion
   retrieval path. As Court Rules move to chunks, do we (a) keep Code rule-level and let
   retrieval fuse both kinds of hit, (b) hard-scope all new work to Court Rules, or
   (c) design chunks generically and backfill Code later? Determines whether `search.py`
   fuses chunk-hits and nv-hits or branches by source.
2. **Chunking strategy** — granularity (paragraph vs numbered comment paragraph vs token
   window), overlap, and whether to embed the rule heading into every chunk.
3. **PDF serving** — backend stream (page-scoped; chapters run 6–23 MB) vs proxy
   legis.iowa.gov vs object storage; affects highlight-overlay feasibility (cross-origin).
4. **Verification gate placement** — model-callable tool the model *must* invoke vs a
   non-bypassable post-generation pass over the streamed answer.
5. **Embedding model** — `voyage-law-2` vs `cohere embed-v3 legal`; re-run the eval on
   chunks, since chunking changes the inputs.

---

## 5. File index for the analyst

| Area | Path |
|------|------|
| Data model | `backend/apps/corpus/models.py` |
| PDF extractor (to be replaced) | `Iowa Court Rules/probe.py`; output `Iowa Court Rules/probe.json` |
| Court Rules ingestion | `backend/apps/ingestion_iowa_rules/{parser,differ,validators,writer}.py` |
| Retrieval | `backend/apps/corpus/services/{search,rerank,embeddings,query_expansion,lookups}.py` |
| Tools (incl. unused verifiers) | `backend/apps/mcp_server/tools.py` |
| Answer loop | `backend/apps/api/chat.py` |
| Frontend | `chat-frontend/` |
| Roadmap / status | `TASKS.md` |
| Processing-rework plan | `COURT_RULES_DOCLING_PLAN.md` |
| Source snapshot notes | `Iowa Court Rules/README.md` |

**Suggested analysis questions:** Is the docling/chunk/highlight architecture the right
shape, or is there a simpler path to the same precision? Where are the remaining
silent-failure modes between PDF and answer? Is the verification-gate design sufficient to
guarantee no fabricated citation/quote reaches the user? What's the minimal eval that would
actually catch a precision regression?
