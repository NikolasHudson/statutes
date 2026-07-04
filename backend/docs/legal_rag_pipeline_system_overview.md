# Legal-RAG Pipeline — System Overview (Reviewer Handoff)

Written 2026-06-10 for an external reviewing agent. This describes the system **as it
exists in the working tree** (branch `feat/shared-rag-pipeline`; PR3–PR7 are largely
uncommitted). Companion docs: `legal_rag_pipeline_design.md` (architecture rationale),
`legal_rag_pipeline_progress.md` (PR-by-PR log, eval numbers, known limitations, and
the planned PR8).

## 1. What this system is

A legal research assistant over a corpus of **Iowa statutes (Iowa Code), Iowa court
rules, and full Iowa caselaw**, with two user surfaces sharing one retrieval/answer
pipeline:

- **Chat** (`apps/api/chat.py`) — an OpenAI tool-loop assistant in the product UI.
- **MCP server** (`apps/mcp_server/`) — the same tools exposed over MCP (live at
  corpus.nick.law/mcp, X-API-Key auth, stateless JSON).

The differentiating goal is **legal-grade safety**, not just retrieval quality:
never surface an overruled case as good law, verify citations/quotes in drafted
answers, abstain when no good-law authority exists, and neutralize false premises in
user questions. Stack: Django + Postgres 18 (pgvector, FTS, pg_trgm), Voyage
embeddings, Voyage reranker, OpenAI for all generative/NLI features
(`OPENAI_API_KEY`; there is no Anthropic key — Anthropic paths no-op).

## 2. Data model (`apps/corpus/models.py`)

Documents form a tree: **Source → Node (tree via `parent`) → NodeVersion →
NodeChunk**.

- **Source** — a collection per jurisdiction ("Iowa Code", "Iowa Caselaw"), unique
  `(jurisdiction, slug)`.
- **NodeType** — one hierarchy level per source (Title/Chapter/Section for statutes;
  **Decision → Opinion** for caselaw).
- **Node** — the citable unit. Key fields: `path` (unique per source), `heading`,
  `source_metadata` (JSONField, GIN-indexed with `jsonb_path_ops`), `is_repealed`.
  - Caselaw **decision** `source_metadata`: `cl_cluster_id`, `case_name[_short|_full]`,
    `court_id`, `date_filed` (functional index for recency), `precedential_status`,
    `citations` (list of reporter cites, e.g. `"848 N.W.2d 40"`), `citation_count`,
    and the **`treatment` cache** (see §5).
  - Caselaw **opinion** `source_metadata`: `cl_opinion_id`, `type` (lead/concurrence/
    dissent), `author_str`, `download_url`, `sha1`.
- **NodeVersion** — append-only temporal text. `body_text` (canonical plain text),
  `body_segments` (display-only rich JSON), `effective_from`/`effective_to`
  (`NULL` `effective_to` = the one open/current version — DB-constrained),
  `content_hash` + `embedding_source_hash` (embed-freshness tracking),
  `search_vector` (tsvector, trigger-maintained, heading weight A / body weight B),
  `embedding` `VectorField(1024)`. Indexes: GIN FTS, trigram GIN on `body_text`,
  HNSW on `embedding`.
- **NodeChunk** (caselaw only; statutes embed whole-version) — passage-level
  retrieval artifact, NOT citable. `version` FK, `ordinal`, `body_text` (the raw span,
  provably `== version.body_text[char_start:char_end]`), `char_start`/`char_end`,
  `context_header` (case name/cite/court/year prefix added only at embed time),
  `embedding` `VectorField(1024)`, HNSW index. Chunking: ~800 tokens target,
  120-token overlap, paragraph-aligned (`services/chunking.py`), real voyage
  tokenizer. **~496K chunks** embedded for the full Iowa caselaw corpus.
- **CrossReference** — citation edges from `from_version` (NodeVersion) to `to_node`
  (Node, nullable for external). `source` enum scopes idempotency:
  - `statute` — Iowa Code prose links;
  - `caselaw_link` — inline links parsed from CourtListener `html_with_citations`
    (**693,497 edges, no depth**);
  - `caselaw_graph` — CourtListener OpinionsCited bulk citation map
    (**475,375 in-corpus Iowa edges**, `weight` = citation **depth**, min 1 / max 70 /
    avg 1.79). This is the substrate for treatment analysis.
- **ReporterCitation** — resolver from `(reporter, volume, page)` → decision Node.
  118,783 rows, keyed by `cl_citation_id`; the triple is deliberately non-unique
  (~1.9% ambiguous → treated as unresolved, never guessed).
- **Court** — CL court slug → level (1 Supreme / 2 Appellate / 3 Trial) for
  authority ranking.
- **Edition** — named as-of date over the version timeline (year-diff browse).

Embeddings: **voyage-law-2, 1024-dim** (env `VOYAGE_EMBED_MODEL`), input_type
document/query distinction respected. HNSW search params set per-connection:
`ef_search=200` (required for recall on the ~500K-chunk index),
`iterative_scan=strict_order`, `max_scan_tuples=20000`.

## 3. Retrieval stack

### 3.1 Search primitives (`apps/corpus/services/search.py`)

Five retrievers, each returning `[(node_version_id, score), ...]`, fused with
**Reciprocal Rank Fusion** (`k=60`) under weights `vector 1.0 / case_name 0.5 /
fts 0.3 / trigram 0.2`; per-retriever cap 50.

- `vector_search(query, ..., with_chunks=False)` — queries **two** HNSW indexes and
  merges: whole-version embeddings (statutes/rules) + chunk embeddings (caselaw,
  over-fetched 5×, rolled up best-chunk-per-version). `with_chunks=True` additionally
  returns `{version_id: winning_chunk_id}`; the default 2-tuple return is kept
  byte-identical for legacy callers.
- `fts_search` — `websearch_to_tsquery` + `ts_rank_cd`.
- `trigram_search` — pg_trgm on `Node.heading` only (threshold 0.1).
- `citation_search` — regex-extracts reporter cites ("763 N.W.2d 862") from the
  query, exact jsonb containment match on `source_metadata.citations`; hits are
  **prepended** to fused results (known-item lane).
- `case_name_search` — party-name tokens (heading-frequency band 1–250) intersected
  with residual-concept FTS.

`SearchHit`: `node_version_id, node_id, path, heading, body_text, score,
component_scores (per-retriever raw), chunk_id`.

`hybrid_search(query, limit=20, ...)` is the public entry; supports
`source_slug` / `metadata_contains` filters and per-retriever toggles.

### 3.2 Shared pipeline (`apps/corpus/services/retrieval.py: retrieve_context`)

One function both surfaces call. Stages, in order (every stage past rerank is
individually togglable; **rank-1 provably stays at `passages[0]`** through all of
them):

1. **Query rewrite** (flag `RAG_QUERY_REWRITE`, default OFF; `query_rewrite.py`) —
   gpt-4o-mini turns lay phrasing into terms-of-art; **guaranteed passthrough** on
   any failure/no-key/over-length; `ctx.query` keeps the ORIGINAL, the rewrite is
   recorded in `diagnostics["query_rewritten"]`.
2. **Hybrid retrieve** — pool of **100** candidates.
3. **Rerank with citation-lane bypass** — Voyage `rerank-2.5` (NoopReranker without a
   key — preserves RRF order). Candidate text = `heading + body[:8000]`. Exact-cite
   hits (those with `"citation"` in `component_scores`) bypass the reranker and stay
   at the front.
4. **Decision-cluster dedup** — `cluster_id` = decision node id for caselaw
   (collapses lead/concurrence/dissent of one decision), node id for statutes; keeps
   best-ranked per cluster.
5. **MMR diversity select** — built, **default OFF** (`mmr_lambda=None`); the A/B
   showed it demotes the on-point case for pinpoint legal queries.
6. **Chunk-aware assembly** — caselaw excerpts centered on the winning `NodeChunk`
   span ± 600-char neighbor window (offsets validated against the version body;
   falls back to chunk text on drift); statutes keep the body prefix. Excerpt
   budgets assigned by relevance rank (top 2 hits get 9000 chars, rest 2000;
   snippet always 280).
7. **U-curve order** — strongest passages at both ends (positional-attention
   mitigation), index 0 preserved.

Output dataclasses:

- `RetrievedPassage`: `node_version_id, node_id, cluster_id, path, heading,
  citation, source_slug, chunk_id, char_start, char_end, excerpt, snippet,
  effective_from, is_repealed, score, component_scores, treatment (TreatmentFlag),
  node_dict`.
- `TreatmentFlag`: `status (good|caution|negative|unknown), severity (0–5), label,
  by_citation, excerpt (verbatim evidence sentence), source
  (graph_phrase|llm|history|none), confidence`.
- `RetrievedContext`: `query, passages, as_of_date, abstain, abstain_reason,
  diagnostics` (pool size, cite_protected, deduped_out, u_order, etc.).

Call sites: chat `_search_with_context` (pool 100, display 6, rerank ON,
enrich_bodies ON) and MCP `search_statutes_tool` (pool 100, display ≤20, rerank OFF
by default, snippet-only).

## 4. Treatment (good-law citator) — the core safety substrate

### 4.1 Deterministic v1 (`apps/corpus/services/treatment.py`)

Phrase-scan classifier over the **incoming citation graph**: for a target decision,
scan citing opinions' sentences for negative stems **in the same sentence as the
target's reporter cite, within 70 chars**.

- Stems → (severity, label): `overruled/abrogated/superseded/repudiated` = 5;
  `disapproved / no-longer-good-law / declined-to-follow` = 4. Status mapping:
  5→negative, 3–4→caution, 0→good.
- Text normalization (the PR7 recall fix): `_normalize_body` repairs PDF soft-hyphen
  wraps + collapses mid-sentence `\n\n`; then **abbreviation-aware,
  capitalization-aware sentence splitting** ("v.", "Co.", "App.", "N.W." never end a
  sentence; entity suffixes end one only before a capitalized new sentence). Split
  into `normalized_sentences()` (once per body) + `classify_in_sentences()` (per
  target) after an O(n²) perf bug was fixed.
- False-positive guards (each has tests): negation/hypothetical lookback ("did not
  overrule", "asked to overrule"); "on other grounds"/"in part" → downgrade to
  caution; agent/patient flip ("overruled **by** [target]"); gerund-after-cite
  ("[target] (overruling X)"); trial-ruling nouns ("overruled the
  objection/motion"); "overruled by statute" → relabel `superseded-by-statute`;
  **intervening-cite guard** (another reporter cite between stem and target →
  reject); "supersedeas" excluded.

### 4.2 Batch annotation (`management/commands/annotate_treatment.py`)

Inverted scan: SQL-regex prefilter selects citing opinions containing any stem
(provable superset of the classifier stems, so re-runs can't drop real flags) →
classify each against the targets it cites (edges from `caselaw_graph`) → aggregate
**max severity per target** → idempotent clear-then-write to the decision's
`source_metadata["treatment"]` (shape = the TreatmentFlag fields). ~7 min full run.

**Current corpus state: 893 decisions flagged (540 negative / 353 caution).**
Verified live: *Madden v. City of Iowa City*, 848 N.W.2d 40 (2014) — overruled by
*Bankers Trust*, 8 N.W.3d 135 (2024) — carries `negative/overruled`.

### 4.3 LLM v2 refinement (`treatment_llm.py`, `--llm` flag) — built, NOT run at scale

gpt-4o reads the citing **paragraph** + target identity, returns a
vocabulary-constrained label (severity derived in code, never trusted from the
model), `target_is_subject`, evidence span, confidence. Policy: confident negative →
refine; confident rejection → **drop**; uncertain (< 0.55) → keep v1.
**Known-unsafe finding:** a depth-gated dry-run dropped 19/40 (47%) of the deepest
candidates and gpt-4o rejected *Madden* itself (a real overrule) — survived only
because confidence 0.0 < threshold. The planned PR8 converts this to a
**confirm-only / never-drop** pass with a frontier model (see progress doc).

## 5. Answer-time safety stack

### 5.1 Premise check, pre-answer (`apps/corpus/services/premise.py`, PR6/PR7)

Intercepts user questions that *assert* what a case holds (anti-anchoring).
`extract_premises` (deterministic): sentence names a case (caption `X v. Y` or
reporter cite) AND attributes a holding (assertion verb within 130 chars after the
name, or "Under/Per [Case]" framing), hedge- and treatment-cue-guarded; cap
`MAX_PREMISES=3`. `check_premises` retrieves the named case top-K with an
**anchor-overlap guard** (never verifies against a topical competitor), then checks
**two orthogonal axes**:

- **Currency** (deterministic, flag `RAG_CURRENCY_CHECK` default **ON**): reads the
  TreatmentFlag already on the retrieved passage; negative/caution ⇒ finding.
- **Fidelity** (LLM NLI via `semantic_support`, flag `RAG_PREMISE_CHECK` default
  OFF): does the opinion actually hold what the user asserted
  (contradicted/partial ⇒ finding).

Bad findings inject a pre-answer system caution (`render_premise_caution`) with a
**correct-then-answer** branch: for a dead case the model must LEAD with the
overruling, then answer under current law. The design point: fidelity and currency
are orthogonal — a faithful reading of an overruled case passes every NLI check and
is still wrong (the *Madden/Bankers Trust* failure that motivated PR7).

### 5.2 Verify + abstain gate, post-answer (`apps/corpus/services/answer.py`, PR4/PR5)

`verify_answer(content, *, source_slug, context=None, claim_checker=None,
premise_problems=None)` → report dict:
`ok, citations_total/verified, quotes_total/verified, citation_problems,
quote_problems, stale_used, misgrounded, premise_problems`.

- **Citation/quote verification** — deterministic: every cite in the drafted answer
  must resolve in the corpus; quoted phrases must match grounding text.
- **Stale-use detection** — cross-references answer-cited cases against the turn's
  retrieved TreatmentFlags. Distinguishes **silent reliance** on a negative case
  (the dangerous failure) from an **acknowledged** mention ("X was overruled by Y"):
  acknowledged only when a treatment cue or the treating case's name sits in the
  **same sentence** (abbreviation-aware boundary; anchors mined from `citation` AND
  `heading` — for caselaw the case name lives in `citation`). `context=None` keeps
  the report byte-identical to the pre-PR4 gate.
- **Claim-level NLI** (flag `RAG_CLAIM_NLI`, default OFF) — pairs the answer's
  caselaw claims with retrieved opinion text via `semantic_support`; `contradicted`
  ⇒ `misgrounded` (advisory only).
- `should_abstain(context)` — true only when nothing was retrieved or **every**
  passage is negative; `unknown` (all statutes + unflagged cases) is presumed good.
- `abstain_decision(report, context, searched)` — **blocking only when
  `RAG_ABSTAIN_BLOCKING=True`** (default OFF ⇒ advisory-only): blocks on silent
  reliance at severity ≥ `RAG_STALE_BLOCK_SEVERITY` (default 5) or
  searched-but-no-good-law. `render_advisory` appends the human-readable warning
  block; currency problems render first (load-bearing).

`semantic_support.py` is the shared NLI primitive (gpt-4o, verdicts
supported/partial/contradicted/no_claim/unverified, verbatim evidence spans,
graceful degradation to `unverified` on any failure).

### 5.3 Chat loop wiring (`apps/api/chat.py`)

System prompt (grounding rules + good-law rule + abstain rule) → pinned document if
any → **premise guard** (injects caution) → OpenAI tool loop (≤10 rounds, 7 tools:
`search_statutes`, `lookup_citation`, `get_version_history`, `get_section_at_date`,
`get_cross_references`, `get_definitions`, `list_recent_amendments`). Every
`search_statutes` call's `RetrievedContext` is captured; `_merge_turn_context`
dedups passages by `cluster_id` across calls (returns `None` for search-less turns,
so lookup-only/pinned answers are never blocked for an empty search set). Finalizers
run verify → abstain → advisory/block on both paths; the **streaming** path can't
un-send text, so a block degrades to a loud trailing notice (documented divergence).

### 5.4 MCP serialization (`apps/mcp_server/tools.py`)

Thin adapter over corpus-owned `corpus_tools.py` (no `api→mcp_server` import —
PR1 deleted it). `search_statutes_tool` payload per hit: `node, snippet, score,
component_scores, char_start, char_end, chunk_id, treatment{status, severity,
label, by_citation, excerpt, source, confidence}`; top level adds
`abstain`/`abstain_reason`. All keys additive vs. the pre-pipeline shape.

## 6. Feature flags (all env-read in `core/settings.py`)

| Flag | Default | Gates |
|---|---|---|
| `RAG_CURRENCY_CHECK` | **True** | Premise currency axis (deterministic, no LLM) |
| `RAG_PREMISE_CHECK` | False | Premise fidelity NLI (LLM) |
| `RAG_CLAIM_NLI` | False | Answer claim-vs-opinion NLI (LLM) |
| `RAG_QUERY_REWRITE` | False | Pre-retrieval query rewrite (LLM) |
| `RAG_ABSTAIN_BLOCKING` | False | Hard block (vs advisory) on silent-stale / no-good-law |
| `RAG_STALE_BLOCK_SEVERITY` | 5 | Min severity for the stale block |

Provider keys: `OPENAI_API_KEY` (all LLM features; absent ⇒ every LLM layer no-ops,
deterministic paths always run), `VOYAGE_API_KEY` (embeddings + reranker; absent ⇒
deterministic fake embedder + Noop reranker for tests/dev).

## 7. Evaluation & test state

- **Tests:** 539 green / 1 known-red across `apps.corpus` + `apps.api` +
  `apps.mcp_server` (the red is a pre-existing `lookup_citation` fuzzy-suggest WIP,
  not pipeline-related). Zero regressions through PR1–PR7; every PR went through an
  adversarial multi-agent review that caught real pre-ship bugs (documented in the
  progress log).
- **Eval harness:** `eval_caselaw` + LLM judge (`retrieval_judge.py`), query sets of
  verified Iowa cases; an `rc` config routes the judged top-K through the real
  `retrieve_context` pipeline. PR2 A/B (n=20, gpt-4o judge): pipeline beats the old
  production path on 7/8 metrics (MRR 0.79 vs 0.75, hit@1 0.75 vs 0.70,
  answerable-with-chunk-excerpts 1.00) — but **n=20 is inside Wilson noise (±0.18)**;
  treat as directional. The harness has gated real decisions (MMR reverted; `--llm`
  drop mode benched).
- **Latency:** rc p50 ~3.8s vs ~3.1s for the old path; not load-tested.

## 8. Known limitations & open risks (honest list — review against these)

1. **Treatment v1 precision:** ~1/3 false positives in a 14-sample of `negative`
   flags (trial-ruling noun before the stem, party contentions, "without
   overruling", possessive rulings, agent confusion). Tolerable while advisory,
   but PR7's correct-then-answer is **confident enforcement** — the
   miscalibration is the top open safety gap. Planned fix: PR8 tiered enforcement
   (confident behavior only for LLM-confirmed flags) + confirm-only frontier-model
   refinement; see progress doc.
2. **Treatment recall holes:** name-only overrulings with no cite-adjacent mention
   are invisible to the phrase-scan; **statute supersession** (repealed/amended §)
   has no treatment-style currency flag (treatment is caselaw-only). Partially
   closed 2026-06-10: `should_abstain` now counts `is_repealed` passages as dead
   law, and `verify_answer` already flagged *cited* repealed §§ via
   `validate_citations`; the remaining gap is the **premise axis** (a user premise
   about a repealed § gets no currency caution — `extract_premises` is
   caselaw-only) and amendment-without-repeal history.
3. **Attribution:** `by_citation` is the *reporting* case, not necessarily the
   overruler (*Madden*'s flag says "Clemen", the parenthetical's host, not
   "Bankers Trust").
4. **Duplicate decision clusters:** at least one case (*Madden*) has two decision
   nodes; the treatment flag must land where retrieval surfaces it.
5. **Treatment cache is a JSON blob** on `source_metadata`, not a first-class table:
   no per-edge provenance, no human override surviving re-annotation, full-rebuild
   only. PR8 plans a `Treatment` table.
6. **Eval power:** n=20, one jurisdiction, favorable landmark slice, no held-out
   set, no gold treatment labels, no CI regression thresholds.
7. **Streaming block** degrades to a trailing notice (true suppression needs answer
   buffering).
8. **Name matching in stale-use** is exact-caption/reporter-cite; a shortened prose
   cite ("State v. Worden" for the full caption) is a residual false negative.
9. **Ops:** no load testing; MCP P1 hardening open (rate limiting, audit logging,
   OAuth). (The latent O(n²) in `answer.py`'s `_is_sentence_boundary` was fixed
   2026-06-10 with the same bounded lookback as `treatment.py`.)
10. **Most of PR3–PR7 is uncommitted** working-tree code on the dev droplet.

## 9. File map (quick reference)

| Area | Path |
|---|---|
| Models | `backend/apps/corpus/models.py` |
| Search primitives | `backend/apps/corpus/services/search.py` |
| Shared pipeline | `backend/apps/corpus/services/retrieval.py` |
| Reranker | `backend/apps/corpus/services/rerank.py` |
| Embeddings client | `backend/apps/corpus/services/voyage.py` |
| Chunking | `backend/apps/corpus/services/chunking.py` |
| Treatment v1 | `backend/apps/corpus/services/treatment.py` |
| Treatment v2 (LLM) | `backend/apps/corpus/services/treatment_llm.py` |
| Annotation command | `backend/apps/corpus/management/commands/annotate_treatment.py` |
| Citation graph ingest | `backend/apps/ingestion_caselaw/management/commands/build_caselaw_citation_graph.py` |
| Answer gate | `backend/apps/corpus/services/answer.py` |
| Premise check | `backend/apps/corpus/services/premise.py` |
| NLI primitive | `backend/apps/corpus/services/semantic_support.py` |
| Query rewrite | `backend/apps/corpus/services/query_rewrite.py` |
| Corpus tools | `backend/apps/corpus/services/corpus_tools.py` |
| Chat surface | `backend/apps/api/chat.py` |
| MCP surface | `backend/apps/mcp_server/tools.py` |
| Flags | `backend/core/settings.py` |
| Tests | `backend/apps/corpus/tests/test_{retrieval,treatment,treatment_llm,answer,premise,query_rewrite}.py` |
