# Design: Shared Legal-RAG Answer Pipeline (Iowa statutes + caselaw)

## 1. Current-state architecture

Today there are **two parallel retrieval/answer paths that share only the low-level retrievers**. The MCP path is the "clean" one: `apps/mcp_server/server.py` registers thin async wrappers over `apps/mcp_server/tools.py`, whose `search_statutes_tool()` calls `apps.corpus.services.search.hybrid_search()` (5 retrievers + weighted RRF + exact-citation prepend), then optionally cross-encoder reranks via `apps.corpus.services.rerank.default_reranker()` and serializes hits with `_node_dict()`/`_snippet()`. The chat path is layered *on top of MCP*: `apps/api/chat.py` imports `search_statutes_tool`, `lookup_citation_tool`, etc. directly from `apps.mcp_server.tools`, wraps `search_statutes_tool` in `_enriched_search()` (re-reranks with a *different* doc-char budget and excerpt logic), runs an OpenAI tool-calling loop (`run_chat_turn` / `run_chat_turn_stream`), and finishes with a deterministic verification gate (`_verify_answer` → `_apply_verification` / `_finalize_stream`).

**The precise shared seam today** is the function `search_statutes_tool` at `apps/mcp_server/tools.py:241`, imported at `apps/api/chat.py:40-48`. This is the backwards dependency: `apps.api` (the human-facing surface) depends on `apps.mcp_server` (the agent-facing surface). Both reach `hybrid_search` and `default_reranker`, but with **duplicated, drifting rerank logic** — `tools.py:276-287` (pool `SEARCH_RERANK_POOL=50`, `SEARCH_RERANK_DOC_CHARS=8000`, key by `node_version_id`) vs `chat.py:139-156` (pool `CHAT_CANDIDATE_POOL=50`, `SEARCH_BODY_MAX_CHARS_TOP=9000`/`2000`, key by `node["id"]`, plus `effective_from` enrichment). There is **no dedup of decision clusters**, **no treatment/currency flag** anywhere in retrieval (the `CrossReferenceSource.CASELAW_GRAPH` pass and `CrossReference.weight` are declared in `models.py:303-341` but never populated), and verification is **advisory-only** and **statute-shaped** (citation-resolves + quote-verbatim), which cannot catch the dominant caselaw failure: an overruled case cited as good law.

---

## 2. Gap analysis: us vs industry standard

| Capability | Industry standard | Us today | Gap |
|---|---|---|---|
| Single shared pipeline | One retrieve→rerank→assemble→verify path consumed by all surfaces | `chat.py` imports `mcp_server.tools` and re-implements rerank/excerpt | **Backwards dep + duplicated rerank**; two drift-prone paths |
| Hybrid retrieval | BM25/FTS + dense, fused | `hybrid_search` already does FTS+trigram+vector+citation+case_name | **OK** (strength: this is good) |
| Weighted fusion | Tune weights so a weak arm can't drag a strong one | `RETRIEVER_WEIGHTS` dense-dominant default already in `search.py:58` | **Mostly closed**; `use_vector=False` browse path still bypasses it |
| Wide-retrieve / narrow-rerank | Retrieve ~100-150, rerank to ~10-20 | Pool 50 → top 6 (chat) / top `limit` (MCP) | Pool a bit narrow; acceptable, tune via eval |
| Citation lane survives rerank | Exact-cite lane bypasses rerank cutoff | Cite hits prepended *before* RRF, but rerank (chat/MCP) re-scores everything incl. cites → can demote | **Gap**: rerank can demote exact-cite hits |
| Decision-cluster dedup | Collapse duplicate clusters; MMR diversity | None — lead+dissent+progeny can fill top-k | **Gap** (eval already collapses; pipeline doesn't) |
| Contextual chunking | Prepend context blurb before embed | `NodeChunk.context_header` already prepended at embed time | **Closed** |
| Passage-level citation w/ offsets | Return verbatim span + char offsets | `NodeChunk.char_start/char_end` exist but **no API returns the matched chunk**; chat excerpts whole-version prefix | **Gap**: assemble at version-prefix, not matched passage |
| Lost-in-the-middle ordering | Best-first/last U-order, lean context | Rank order, 2 big + N small excerpts | **Gap** |
| Jurisdiction/as-of hard filter | Hard pre-filter, not ranking boost | `metadata_contains` supports it; chat/MCP don't pass it; no as-of plumbing past `effective_to IS NULL` | Partial |
| Good-law / treatment flag | Citator (red/yellow/green), block overruled | **None** in answer path; judge has `stale_warning` (eval only) | **Critical gap** |
| Claim-level groundedness | NLI/entailment per claim (misgrounding) | `_verify_answer` = citation-resolves + quote-verbatim only | **Gap** (misgrounding passes) |
| Abstention | Explicit "no on-point authority" path | Synthesis nudge produces best-effort; no abstain output | **Gap** |
| Eval gate | Retrieval + generation metrics, judge | `eval_caselaw` (hit@k/MRR/nDCG + Wilson CI + `OpenAIRetrievalJudge`) | **Closed** (strong; reuse as scorecard) |

---

## 3. Target architecture: the shared service

Two new modules in-corpus (per "keep search in corpus"):

- **`apps/corpus/services/retrieval.py`** — the **shared context layer**: query → retrieve → dedup → treatment/currency annotate → passage assemble. Surface-agnostic. Returns a `RetrievedContext`.
- **`apps/corpus/services/answer.py`** — **synthesis + verify/abstain helpers** usable by both surfaces. Chat owns the OpenAI streaming loop (stays in `chat.py`); MCP returns structured passages. The verify/abstain logic moves here so both call it.

A small **`apps/corpus/services/treatment.py`** holds the good-law flag (section 5).

### Core dataclasses (`apps/corpus/services/retrieval.py`)

```python
@dataclass
class TreatmentFlag:
    status: str            # "good" | "caution" | "negative" | "unknown"
    severity: int          # 0 good .. 5 invalidated (Demir/Canbaz scale)
    label: str             # "overruled" | "superseded" | "distinguished" | ...
    by_citation: str = ""  # the case/statute that did it, if known
    excerpt: str = ""      # verbatim citing-sentence (the evidence)
    source: str = "none"   # "history" | "graph_phrase" | "llm" | "none"
    confidence: float = 0.0

@dataclass
class RetrievedPassage:
    node_version_id: int
    node_id: int
    cluster_id: int            # decision node id (== node_id for statutes)
    path: str
    heading: str
    citation: str              # rendered, surface-ready (reuses tools._render_citation)
    source_slug: str
    chunk_id: int | None       # the winning NodeChunk, if caselaw
    char_start: int | None     # offsets into version.body_text (None for whole-version)
    char_end: int | None
    excerpt: str               # the matched passage text (chunk span or budgeted version prefix)
    effective_from: str | None
    is_repealed: bool
    score: float               # post-rerank relevance
    component_scores: dict[str, float]
    treatment: TreatmentFlag

@dataclass
class RetrievedContext:
    query: str
    passages: list[RetrievedPassage]   # deduped, treatment-annotated, U-ordered
    as_of_date: str
    abstain: bool                       # True when no good-law, on-point passage survived
    abstain_reason: str = ""
    diagnostics: dict = field(default_factory=dict)  # timings, pool sizes, weights
```

### Public function signatures

```python
# apps/corpus/services/retrieval.py
def retrieve_context(
    query: str,
    *,
    source_slug: str | None = None,
    use_vector: bool = True,
    candidate_pool: int = 100,      # wide retrieve
    display_limit: int = 8,         # narrow after rerank+dedup
    rerank: bool = True,
    reranker: Reranker | None = None,
    annotate_treatment: bool = True,
    as_of_date: date | None = None,
    metadata_contains: dict | None = None,
    excerpt_budget_top: int = 9000,
    excerpt_budget_rest: int = 2000,
) -> RetrievedContext: ...

def rewrite_query(query: str, history: list[dict]) -> str: ...  # follow-up → standalone (chat only)
```

```python
# apps/corpus/services/answer.py  (verify/abstain extracted from chat.py)
@dataclass
class VerifyReport:
    ok: bool
    citations_total: int; citations_verified: int
    quotes_total: int; quotes_verified: int
    citation_problems: list[dict]; quote_problems: list[dict]
    stale_used: list[dict]          # NEW: cited cases that carry a negative TreatmentFlag
    source_label: str

def verify_answer(content: str, *, source_slug: str | None,
                  context: RetrievedContext | None = None) -> VerifyReport | None: ...
def render_advisory(report: VerifyReport) -> str: ...
def should_abstain(context: RetrievedContext) -> tuple[bool, str]: ...
```

### Two-layer split & thin adapters

```
            apps/corpus/services/retrieval.py   ← shared context layer (NO surface imports)
            apps/corpus/services/answer.py       ← shared verify/abstain
                    ▲                       ▲
   ┌────────────────┘                       └─────────────────┐
apps/api/chat.py                              apps/mcp_server/tools.py
 _enriched_search  → retrieve_context()        search_statutes_tool → retrieve_context()
 _verify_answer    → answer.verify_answer()    (serialize RetrievedPassage → JSON)
 (OpenAI loop stays here)                       (returns structured passages + flags)
```

- **`_enriched_search` (chat)** becomes: call `retrieve_context(query, source_slug=…, use_vector=…)`, map `RetrievedPassage` → the dict shape the OpenAI tool result already uses (`node`, `body_excerpt`, `effective_from`, plus new `treatment`). No rerank/excerpt code left in `chat.py`.
- **`search_statutes_tool` (MCP)** becomes: call `retrieve_context(...)`, serialize passages (now with `treatment` and `char_start/char_end`). Backward-compatible: existing keys (`node`, `snippet`, `score`, `component_scores`) preserved; new keys are additive.
- **Removing the backwards dep**: `chat.py` stops importing `search_statutes_tool` from `apps.mcp_server.tools`. The remaining direct-lookup tools (`lookup_citation_tool`, `get_cross_references_tool`, etc.) are *already* thin wrappers over `apps.corpus.services.lookups`; move those wrappers into a new `apps/corpus/services/corpus_tools.py` (pure functions, no MCP coupling) and have **both** `chat.py` and `mcp_server/tools.py` import from there. After this, `apps.api` imports only `apps.corpus.*`; `apps.mcp_server` imports only `apps.corpus.*`. The api→mcp_server edge is gone.

---

## 4. Stage-by-stage spec

Each stage notes **what it does / reuses / new / how the judge measures it**. All stages live in `retrieval_context()` except synthesis (chat) and verify/abstain (`answer.py`).

**1. Query understanding (`rewrite_query`)**
- *Does*: for chat follow-ups, rewrite the last user turn into a standalone query using conversation history (multi-query paraphrase, not HyDE — latency). MCP receives standalone queries already, so it skips this.
- *Reuses*: existing `QueryExpander` (`search.py:36`) for term-of-art expansion stays inside `hybrid_search`. The new rewrite is a thin OpenAI call mirroring `OpenAIRetrievalJudge` (JSON mode, same key gating; `None` key → identity passthrough).
- *New*: `rewrite_query`. **Off by default behind a flag** until eval-proven.
- *Measured*: `eval_caselaw` Recall@k / MRR on the holding-description query set with vs without rewrite (Wilson CI gate).

**2. Retrieve (hybrid + citation + name)**
- *Does*: `hybrid_search(query, limit=candidate_pool, use_vector=use_vector, source_slug=…, metadata_contains=…)` — 5 retrievers, weighted RRF, exact-cite prepend.
- *Reuses*: `hybrid_search` unchanged (already production-grade). Pass `candidate_pool=100` (wider than today's 50) so the reranker sees more.
- *New*: `as_of_date` plumbing — when set, this is a **hard filter** added pre-fusion (extend `_approved_filter_clause` to accept an as-of date instead of only `effective_to IS NULL`). Jurisdiction stays a hard filter via `metadata_contains={"court_id": ...}` / `source_slug`.
- *Measured*: per-retriever and fused hit@k/nDCG already emitted by `eval_caselaw`; add a jurisdiction-leak check (no out-of-Iowa hit in top-k).

**3. Dedup (decision-cluster collapse)**
- *Does*: collapse all passages whose `cluster_id` (decision node) is the same to a single best-scoring passage; then MMR (λ≈0.6) over the survivors so near-identical paragraphs from one opinion don't crowd out distinct cases.
- *Reuses*: cluster derivation from `eval_caselaw._cluster_of` logic and `tools._caselaw_decision` (`node.parent` for opinions) — promote both into `retrieval.py`. Statutes: `cluster_id == node_id` (no-op).
- *New*: the collapse + MMR selector (computes diversity from `component_scores`/embeddings; v1 can use a cheap token-overlap diversity).
- *Measured*: judge's `per_case` — fewer "off"/duplicate cases in top-k; "controlling_present" should not drop. Add a "distinct-cluster count in top-5" metric to `eval_caselaw`.

**4. Treatment / currency annotation** (section 5 for sourcing)
- *Does*: attach a `TreatmentFlag` to each passage. Drop or down-rank `severity>=5` (invalidated) passages before display unless the user explicitly asked about that case.
- *Reuses*: `Node.is_repealed`, `NodeVersion.effective_to`, `Court.level` (binding vs persuasive), `CrossReference` graph.
- *New*: `treatment.py` (deterministic v1 / LLM v2).
- *Measured*: judge's `stale_warning` and `controlling_present` — a passing run should have **zero** negative-treatment cases presented as good law. This is the headline metric.

**5. Passage assembly (chunk-level, offsets + ordering)**
- *Does*: for caselaw, set `excerpt` to the **winning chunk's span** (`version.body_text[char_start:char_end]`) plus a small neighbor window, not a whole-version prefix — this fixes "opinion-head excerpt misses the holding." For statutes, keep the current budgeted prefix. Order the final list around the U-curve (best first and last, weakest middle) and keep it lean (`display_limit≈8`).
- *Reuses*: `_excerpt` (chat.py:68) and `_snippet` (tools) — unify into one `truncate_on_boundary`. `NodeChunk.char_start/char_end` already exist; the chunk id flows from a small change to `vector_search` to return the winning chunk id (today `_vector_search_chunks` rolls up to version and discards which chunk won — return `(version_id, score, chunk_id)`).
- *New*: chunk-aware excerpting; U-ordering; offsets on the passage.
- *Measured*: judge `answerable` (yes/partial/no) should rise as excerpts carry the holding, not the caption.

**6. Synthesis (chat) / structured passages (MCP)**
- *Chat*: the OpenAI loop in `run_chat_turn[_stream]` stays in `chat.py`; the only change is the tool result now carries `treatment` and the assembled passage, and the system prompt gains a stale-law rule ("never rely on a source flagged negative; if the only on-point authority is flagged, say so").
- *MCP*: `search_statutes_tool` returns `RetrievedPassage` serialized with `treatment`, `good_law_status`, `as_of_date`, `char_start/char_end` so a downstream agent cannot silently rely on overruled/wrong-jurisdiction law.
- *Measured*: judge `answer` + `answerable` on the same context both surfaces return (run the judge against `RetrievedContext`, identical for chat and MCP).

**7. Verify + abstain (`answer.py`)**
- *Does*: keep the deterministic gate (citation resolves + quote near-verbatim, `SequenceMatcher` 0.6) **and** add (a) **stale-use detection** — cross-reference cited cases in the answer against the `TreatmentFlag`s in the `RetrievedContext`; any negative-treatment case used → flag/red; (b) **abstain** — if `should_abstain(context)` (no `severity<caution`, on-point passage survived) returns True, the answer path emits an explicit "I could not locate good-law Iowa authority on X" instead of stretching an adjacent rule.
- *Reuses*: `_verify_answer` body moves verbatim into `answer.verify_answer`; `validate_citations`/`verify_quotes` (lookups); `_normalize_for_match`, `_is_real_section`, `_MONEY_RE/_URL_RE`. The optional claim-level NLI layer reuses `semantic_support.OpenAIChecker` (already built) for caselaw holdings (v2).
- *New*: `stale_used`, `should_abstain`. Keep advisory-only at first (behavior-preserving), then flip to blocking for `severity>=5` behind a flag.
- *Measured*: extend `eval_caselaw` judge with an adversarial set: questions whose answer is "no Iowa authority" (measure abstain rate) and overruled-precedent questions (measure stale-block rate). Track accurate / incomplete / hallucinated separately so abstention isn't scored as a miss.

---

## 5. Treatment / "good-law" flag

**What exists in the data (verified):**
- `CrossReference` edges with `source=CASELAW_LINK` — ~693K inline-link edges (`backfill_caselaw_cross_references.py`), each `from_version` (citing opinion) → `to_node` (cited case), plus `external_text` display.
- `ReporterCitation` resolver (~118K) for reporter-cite → cluster.
- `Court.level` (Supreme=1 / Appellate=2 / Trial=3) — enables the authority-hierarchy check ("only a higher/coordinate court overrules").
- `Node.is_repealed`, `NodeVersion.effective_to` — statute/decision repeal/supersession (direct history, deterministic).
- `CrossReference.weight` and `CrossReferenceSource.CASELAW_GRAPH` — **declared, never populated**. No command builds the #2 OpinionsCited depth graph; `depth`/`OpinionsCited` is read nowhere in ingestion.

**What must be built:**
- The **citing-sentence text is not captured today** — `extract_citation_links` (`parser.py:427`) lifts only the `<a>` href + anchor display text, not the surrounding sentence. The negative-treatment phrase classifier needs the citing opinion's prose around the link. Source it from the citing `from_version.body_text` (we have offsets to the link in the display HTML; v1 can re-scan `body_text` for the cited case's reporter cite / anchor text and grab the enclosing sentence).
- **CourtListener OpinionsCited depth**: CL's `/api/rest/.../opinions-cited/` and the bulk **`citation-map-<date>.csv.bz2`** file (the `search_opinionscited` table: `id, depth, citing_opinion_id, cited_opinion_id`, ~500 MB compressed, regenerated quarterly) expose a directed graph with a `depth` field (times A cites B). Ingested in **PR2.5** (`build_caselaw_citation_graph`) → `CrossReference(source=CASELAW_GRAPH, weight=depth)`, which both prioritizes the LLM budget (deep engagement = worth classifying) and feeds the transitive risk pass. NOTE: this is a *different* bulk file from the `citations` CSV (~120 MB, `search_citation`: reporter volume/reporter/page) already ingested into `source_metadata.citations[]`.
- **CL treatment is NOT available for us (verified 2026-06-08).** Free Law Project's AI citator (free.law, May 2025) — which classifies overruling/distinguishing — is a SCOTUS-only, overruling-only proof-of-concept, not exposed via API or bulk data, no production timeline, and scoped to the Supreme Court (useless for Iowa state courts). So we **cannot ingest treatment from CL**; we ingest the graph+depth and build the Iowa treatment classifier ourselves. Their citator *does* validate the approach below (EyeCite + ±6 sentences context + LLM; Claude 3.5 Sonnet >90% recall / F1 >80% on overruling) — reserve a `TreatmentFlag.source="courtlistener"` slot for when it generalizes.

**Deterministic v1 (`treatment.py`, no LLM):**
1. **Direct history** (reliable): `is_repealed` / non-null `effective_to` → `superseded`/`repealed` (severity 5). 
2. **Citing-reference phrase scan**: for the target case, walk its **incoming** `CrossReference` edges; for each citing opinion, grab the citing sentence and regex for negative stems near the cite — `overrul`, `abrogat`, `supersed`, `disapprov`, `declin\w* to (follow|extend)`, `no longer good law`, `we reject`, `distinguish`. Gate by the **authority-hierarchy check** (the citing court's `Court.level` ≤ the target's). Map stem → severity (overrule/abrogate=5, criticize/question=4, limit/distinguish=3). Most-negative wins the case-level flag; store the verbatim sentence as `excerpt`.
3. Output `TreatmentFlag(source="graph_phrase" | "history", confidence≈0.6)`. Phrase-only flags are advisory (citators miss ~1/3).

**LLM-assisted v2:**
- For candidates the lexical trigger fires on (gated by `CrossReference.weight`/depth so we spend budget on deep engagements), call `semantic_support.OpenAIChecker`-style classifier (reuse the module; new prompt) feeding the citing **paragraph** + the citing court level; require a verbatim supporting excerpt + confidence + explicit target check; emit one of 5 severity tiers. `source="llm"`. Low-confidence → `status="unknown"` (route to human / don't block).

**Data model changes:**
- No new tables required for v1/v2 — reuse `CrossReference` (`source=CASELAW_GRAPH`, `weight=depth`) and a small `Node.source_metadata` cache: write the computed flag onto the **cited** decision node as `source_metadata["treatment"] = {status, severity, label, by, source, confidence}` so retrieval reads it with one indexed lookup (already GIN-indexed) instead of graph-walking per query. Optional v2: a dedicated `Treatment` table if multi-label history is needed.

**Backfill commands:**
- `apps/ingestion_caselaw/management/commands/build_caselaw_citation_graph.py` — #2 pass: ingest CL OpinionsCited depth → `CrossReference(source=CASELAW_GRAPH, weight=depth)`. Idempotent per `from_version`/source (mirrors the existing `caselaw_link` rebuild).
- `apps/corpus/management/commands/annotate_treatment.py` — runs v1 deterministic scan (+ optional `--llm` v2) over all caselaw decision nodes, writes `source_metadata["treatment"]`. Resumable; `--since` for incremental.

---

## 6. Phased implementation plan

**PR1 — Behavior-preserving extraction (NO quality change).**
- *Scope*: create `apps/corpus/services/retrieval.py` with `retrieve_context()` that reproduces today's chat enrichment exactly (pool 50, top 6, 9000/2000 excerpt budgets, `effective_from`, current weighted RRF). Create `apps/corpus/services/corpus_tools.py` holding the direct-lookup wrappers. Repoint `chat.py._enriched_search` and `mcp_server/tools.search_statutes_tool` at `retrieve_context`; repoint both surfaces' lookup tools at `corpus_tools`. Delete the `apps.api → apps.mcp_server` import.
- *Files*: new `retrieval.py`, `corpus_tools.py`; edit `chat.py`, `mcp_server/tools.py`, `mcp_server/server.py` (registration import).
- *Risk*: low-medium (pure refactor); the trap is the two rerank doc-char budgets and the dict key shape (`node["id"]` vs `node_version_id`). Mitigate with golden-output tests over `test_tools.py` / chat tests.
- *Proves*: `eval_caselaw` (all configs) byte-identical retrieval metrics before/after; existing `test_tools.py`, `test_search.py`, chat tests green. **No metric should move.**

**PR2 — Decision-cluster dedup + MMR + chunk-aware offsets.**
- *Scope*: cluster-collapse + MMR in `retrieve_context`; `_vector_search_chunks` returns winning `chunk_id`; passages carry `char_start/char_end` and matched-chunk excerpts; U-ordering.
- *Files*: `retrieval.py`, `search.py` (chunk id), serializers in `tools.py`.
- *Risk*: medium — chunk-excerpt change alters what the model sees; gate carefully.
- *Proves*: `eval_caselaw` distinct-cluster-count-in-top-5 ↑; judge `answerable` ↑, `per_case` "off" ↓; Recall@k not regressed (Wilson CI).

**PR2.5 — Ingest the CourtListener citation-map (graph + depth).** *(split out of PR3 — the treatment classifier's substrate.)*
- *Scope*: `build_caselaw_citation_graph` (#2 depth pass) — stream CL's `citation-map-<date>.csv.bz2` via `csv_stream.open_bulk_csv` (never decompress to disk), keep in-corpus Iowa edges (join on `cl_opinion_id`), write `CrossReference(source=CASELAW_GRAPH, weight=depth)`. Internal edges only; self/sibling skipped; idempotent (delete-all-CASELAW_GRAPH-for-source then rebuild).
- *Files*: new command in `apps/ingestion_caselaw` (mirrors `backfill_caselaw_cross_references` #1).
- *Risk*: low — additive, source-scoped (never touches `caselaw_link`), recoverable (idempotent rebuild on a prod-clone DB).
- *Proves*: `CrossReference.weight` populated for the Iowa internal graph; edge/depth distribution sane; the #1 inline-link edges untouched.

**PR3 — Treatment graph + deterministic v1 flag.** *(Assumes PR2.5's graph+depth is built.)*
- *Scope*: `treatment.py` v1, `annotate_treatment` backfill (walks **incoming** CASELAW_GRAPH edges, depth-prioritized), `source_metadata["treatment"]` read in `retrieve_context`, `TreatmentFlag` on passages and serialized to MCP.
- *Files*: `treatment.py` + `annotate_treatment` command; `models`/migration only if a `Treatment` table is chosen (default: reuse metadata, no migration).
- *Risk*: medium — false-negative-treatment flags. Ship advisory (flag shown, not blocking).
- *Proves*: judge `stale_warning` agreement (flag present whenever judge names a stale case); zero negative cases in top-k presented as good law on the overruled-precedent eval subset.

**PR4 — Verify+abstain extraction and stale-use gate.**
- *Scope*: move `_verify_answer`/advisory into `answer.py` as `verify_answer`/`render_advisory`; add `stale_used` + `should_abstain`; wire abstain into chat synthesis and the MCP `abstain` field. Behavior-preserving for statutes (same deterministic checks); additive stale check for caselaw. Keep advisory; add a flag to **block** `severity>=5`.
- *Files*: `answer.py`, `chat.py` (call sites), `tools.py`.
- *Risk*: medium — over-abstention. Calibrate threshold on the adversarial eval set.
- *Proves*: extended `eval_caselaw` judge: abstain-rate on no-authority questions, stale-block-rate on overruled questions, with accurate/incomplete/hallucinated tracked separately.

**PR5 — LLM-assisted treatment v2 + (optional) claim-level NLI + query rewrite.**
- *Scope*: `annotate_treatment --llm` (reuse `semantic_support`), claim-level entailment for caselaw holdings, `rewrite_query` behind a flag.
- *Risk*: cost/latency — all gated by env key + flag, eval-gated.
- *Proves*: each behind its own A/B in `eval_caselaw`; ship only Wilson-CI wins.

---

## 7. Production concerns

- **Feature flags / rollout**: settings flags `RAG_TREATMENT_ENABLED`, `RAG_ABSTAIN_BLOCKING`, `RAG_QUERY_REWRITE`, `RAG_CLAIM_NLI` (default off except treatment-advisory). PR1 ships dark (refactor only). Each later capability defaults to advisory/observe before enforce.
- **Latency budget**: current p50s — hybrid ~3.3s, rerank ~0.3s, embed ~0.18s. New work: dedup/MMR/U-order is in-process (<5ms). Treatment annotation is a **precomputed `source_metadata` read** (no per-query graph walk) → ~0ms. Query rewrite and claim-NLI add an OpenAI round-trip each (~0.5-2s) so both stay flag-gated and off the hot interactive path by default. Wider pool (50→100) adds modest rerank cost (~0.1-0.2s). Net interactive p50 target unchanged for chat.
- **Caching**: cache query embedding and `retrieve_context` result by `(normalized_query, source_slug, as_of_date)` in Redis (same `CACHES` the quota counters use) with a short TTL; treatment flags live on `source_metadata` (already persisted). Rerank results keyed by query+candidate-id-set.
- **Observability/tracing**: `RetrievedContext.diagnostics` (timings per stage, pool sizes, weights, dedup counts, treatment-source breakdown) flows into the existing `ToolCallTrace`/`record_chat_trace` and a new `retrieve_context` trace row in MCP. Log the same groundedness/abstain signal from both surfaces so an MCP consumer never gets a less-verified answer than a chat user.
- **Cost**: treatment v2 + claim-NLI are the only recurring LLM costs; gate by `CrossReference.weight` (depth) so we classify deep engagements only. Backfills are one-time (depth graph) / incremental (`--since`).
- **Failure/degradation**: no `VOYAGE_API_KEY` → `default_reranker()` = `NoopReranker`, `default_client()` = `FakeEmbeddingClient` (existing). No `OPENAI_API_KEY` → `rewrite_query` passthrough, treatment v2 / claim-NLI skipped (deterministic v1 still runs), judge `None` (eval skips). **New alert**: surface reranker/Voyage failure (today silently swallowed at `rerank.py:96`) as a `diagnostics["rerank_degraded"]` flag rather than silent RRF fallback.
- **Backward-compat (MCP)**: all new fields (`treatment`, `good_law_status`, `char_start/char_end`, `abstain`) are **additive**; existing keys (`node`, `snippet`, `score`, `component_scores`, `as_of_date`) unchanged. Existing MCP clients keep working; the tool's input signature is unchanged.

---

## 8. Risks & open questions to confirm before coding

1. **Excerpt change risk (PR2)**: switching chat from whole-version-prefix to matched-chunk excerpt changes what the model reads. Confirm we want this for statutes too, or only caselaw (statutes are short; the prefix is fine). Recommend caselaw-only chunk excerpts, statute prefix unchanged.
2. **Blocking vs advisory abstention**: do we hard-block answers that rely on `severity>=5` cases, or keep advisory + red flag? Stanford says block; UX says a calibrated warning may suffice. Confirm policy and the severity threshold.
3. **CourtListener OpinionsCited availability**: ✅ RESOLVED (PR2.5, 2026-06-08). The depth graph is the bulk **`citation-map-<date>.csv.bz2`** (`search_opinionscited`), ~500 MB compressed, on the public S3 bucket `com-courtlistener-storage/bulk-data/`, regenerated quarterly. Re-pulled just this one file (separate from the archived ~58 GB of big files); streamed + Iowa-filtered by `cl_opinion_id` (every node carries it). CL **treatment** labels are NOT available for state courts (their citator is SCOTUS-only PoC) — we ingest graph+depth and build treatment ourselves.
4. **Citing-sentence sourcing**: ✅ RESOLVED (PR3) — re-scan the citing opinion's `body_text` for the sentence containing the target's reporter cite (no re-ingest). `treatment.classify_citing_text` does the enclosing-sentence scan; precise enough with the proximity + agent/negation guards.
5. **`source_metadata["treatment"]` cache vs dedicated table**: ✅ RESOLVED (PR3) — cache on the cited decision's `source_metadata["treatment"]` (no table, no migration); one indexed read in `retrieve_context`. `annotate_treatment` is idempotent (clear-then-write), so a re-ingest just re-runs it.
6. **As-of date in retrieval**: chat/MCP have no as-of date input today. Confirm whether to add it now (extend `_approved_filter_clause` to a date predicate) or defer — affects whether jurisdiction/temporal hard-filtering lands in PR1's signature.
7. **Pool widening**: 50→100 candidates adds rerank latency; confirm the budget, and confirm whether the citation lane should bypass the reranker entirely (recommended, given the eval finding that rerank demotes exact cites).
8. **Where the OpenAI loop lives**: this design keeps the tool-calling loop in `chat.py` (only the context + verify layers are shared). Confirm we don't want to also extract the loop into `answer.py` (more sharing, but MCP doesn't run a loop, so likely unnecessary).

**Key file references**: `apps/corpus/services/search.py` (`hybrid_search:663`, `_vector_search_chunks:566`, `RETRIEVER_WEIGHTS:58`), `apps/corpus/services/rerank.py` (`default_reranker:101`), `apps/corpus/services/retrieval_judge.py` (`OpenAIRetrievalJudge:129`, `stale_warning`), `apps/corpus/services/semantic_support.py` (`OpenAIChecker`, reuse for v2/NLI), `apps/api/chat.py` (`_enriched_search:95`, `_verify_answer:824`, `run_chat_turn:1040`, `SYSTEM_PROMPT:359`), `apps/mcp_server/tools.py` (`search_statutes_tool:241`, `_node_dict:65`, `_annotate_caselaw:115`), `apps/corpus/models.py` (`CrossReference:314`, `CrossReferenceSource:303`, `weight:341`, `Court.level:39`, `NodeChunk.char_start/end:224`), `apps/ingestion_caselaw/management/commands/backfill_caselaw_cross_references.py`, `apps/ingestion_caselaw/parser.py` (`extract_citation_links:427`), `apps/corpus/management/commands/eval_caselaw.py` (`_cluster_of:90`, `_wilson_ci:105`). New modules to create: `apps/corpus/services/retrieval.py`, `apps/corpus/services/answer.py`, `apps/corpus/services/treatment.py`, `apps/corpus/services/corpus_tools.py`; new commands: `apps/ingestion_caselaw/management/commands/build_caselaw_citation_graph.py`, `apps/corpus/management/commands/annotate_treatment.py`.