# Legal-RAG Pipeline — Progress & Resume Log

Living status tracker for the shared legal-RAG answer pipeline. The full
architecture + rationale lives in [`legal_rag_pipeline_design.md`](./legal_rag_pipeline_design.md);
this file is the "where are we / what's next" log so any session can resume.

Branch: `feat/shared-rag-pipeline`

## Goal

Replace the two drift-prone retrieval/answer paths (chat re-implements rerank on
top of an `apps.api → apps.mcp_server` import) with **one shared context service**
that both chat and MCP call down into, and close the legal-grade gaps measured by
the eval/judge: stale/overruled-law surfacing, decision-cluster duplication,
opinion-head excerpts that miss the holding, and no abstain path.

## What we proved before building (session 798ba6b6, 2026-06-07)

- Eval set #3 (`caselaw_eval_queries_categories2.json`, 20 verified cases): vector
  MRR 0.675, hit@5 0.80, recovered 100%. Retrieval is the strong link.
- LLM judge (`retrieval_judge.py` + `--judge`): answerable 70% (85% incl. partial);
  controlling-case present 75%; ground-truth in top-5 80%.
- The dangerous tail is legal-grade, not random: **stale/overruled law surfaced as
  good law** (Godfrey→Burnett, Gacke→Garrison), context-quality misses (opinion-head
  excerpt), seminal-case burial. Judge caught a bad ground-truth label (#20 Gallagher).
- DB facts verified: `caselaw_link` 693,497 edges; `ReporterCitation` 118,783 all
  resolved; `CASELAW_GRAPH` 0 rows / `CrossReference.weight` NULL (treatment graph
  genuinely unbuilt).
- **Green test baseline:** `apps.corpus` + `apps.api` = 328 green; `apps.mcp_server`
  = 32/33 (the 1 red — `lookup_citation_tool("714.99")` fuzzy-suggest — is
  pre-existing uncommitted WIP in `tools.py`, NOT a regression from this work).

## Phased plan & status

- [x] **PR1 — Behavior-preserving extraction (NO quality change).** ✅ DONE (uncommitted)
  - New `apps/corpus/services/retrieval.py` — `retrieve_context()` (shared
    retrieve→rerank→assemble) + `RetrievedContext`/`RetrievedPassage`/`TreatmentFlag`
    dataclasses (forward-compat; PR2–4 populate the empty fields).
  - New `apps/corpus/services/corpus_tools.py` — the direct-lookup/verify/audit tools
    + serializers, corpus-owned (no MCP coupling).
  - `mcp_server/tools.py` → thin MCP adapter (re-exports + repointed
    `search_statutes_tool`); `chat.py._enriched_search` → thin chat adapter.
  - **`apps.api → apps.mcp_server` import deleted.**
  - Resolution of the two rerank divergences: doc-char budget preserved per surface
    (chat none / MCP 8000) via `rerank_doc_chars`; keyed on `node_version_id` for both
    (equivalent — one open version per node, so node_id is unique among hits). One
    **deliberate, documented unification**: the rerank candidate text now uses the raw
    node heading for both surfaces (chat previously reranked caselaw on the annotated
    "Court, Year" display heading). Invisible to tests (NoopReranker ignores candidate
    text) and to `eval_caselaw` (bypasses chat); strictly more correct.
  - Verified: baseline 360 green + 1 known-red → after PR1, identical (361 tests,
    same single pre-existing red `lookup_citation` fuzzy-suggest). **No metric moved.**
  - Adversarial review (3-dimension workflow) cleared it. Two real findings fixed:
    `cluster_id` now source-gated (== node_id for statutes, was wrongly the chapter id;
    latent PR2-dedup trap); chat empty-query `error` key restored. One "regression"
    was a false alarm (reviewer baselined caselaw annotation against HEAD, but it was
    pre-existing uncommitted working-tree code, copied faithfully).
  - NOTE: PR1's edits to `chat.py`/`tools.py` are entangled with the uncommitted
    prior-session foundation (chunking/eval/judge/`search.py`) in the same files, so a
    clean PR1-only commit isn't separable. Commit strategy is the user's call.
- [x] **PR2 — Decision-cluster dedup + MMR + chunk-aware offsets.** ✅ DONE (uncommitted)
  - `search.py`: `SearchHit.chunk_id`; `_vector_search_chunks` returns
    `(vid, score, chunk_id)`; new `_merge_version_chunk_hits`; `vector_search`
    gained a `with_chunks` opt-in that **keeps the default 2-tuple return
    byte-identical** (eval/benchmark/tests unpack 2-tuples); `hybrid_search`
    attaches the dense retriever's winning chunk to each hit.
  - `retrieval.py`: `retrieve_context` rewritten as a pipeline — hybrid
    retrieve (pool **50→100**) → rerank **with exact-citation-lane bypass** →
    **decision-cluster dedup** → MMR select → **chunk-aware assembly** (caselaw
    excerpt/snippet from the matched `NodeChunk` span + neighbor window; statutes
    keep the prefix) → **U-curve order**. Each stage past rerank is individually
    togglable; every stage provably preserves the rank-1 hit at `passages[0]`.
    Excerpt budget is assigned by **relevance rank before** U-order reorders.
    Rerank candidate-text cap **unified to 8000** for both surfaces (so a
    100-opinion caselaw pool stays affordable; only the rerank *input* is capped,
    not what the model reads).
  - Adapters: MCP `search_statutes_tool` + chat `_enriched_search` serialize
    additive `char_start`/`char_end`/`chunk_id`; existing keys unchanged.
  - `eval_caselaw`: new `--use-retrieve-context` **`rc` config** (routes the
    judged top-K through the real pipeline — the only config that exercises PR2),
    `--rc-*` A/B toggles, **distinct-cluster-in-top-k metric**, and a
    chunk-excerpt-aware judge payload.
  - **Tests:** new `apps/corpus/tests/test_retrieval.py` (20 tests: MMR
    position-0 invariant + diversity, U-curve, chunk-excerpt budget/robustness,
    chunk_id threading, dedup collapse, offsets, holding-centered excerpt,
    citation bypass). Full suite **380 / 1-known-red** (was 361/1) — +19/+20
    green, **zero regressions** (the 1 red is the pre-existing `lookup_citation`
    714.99 fuzzy-suggest).
  - **Eval A/B (real corpus, gpt-4o judge, category2 n=20, 2026-06-08):** the new
    PR2 config (dedup+chunk+U-order+cite-bypass, **MMR off**) beats the current
    production path (`hybrid_rr`) on 7/8 metrics — MRR 0.79 vs 0.75, hit@1 0.75
    vs 0.70, hit@10 0.90 vs 0.85, controlling 0.80 vs 0.75, target-shown 0.85 vs
    0.80 (within n=20 Wilson noise, but directionally consistent). Isolations:
    **chunk-excerpt** lifts yes-or-partial answerable 0.90→1.00; **dedup** raises
    distinct-clusters@5 4.65→5.0 with no answer cost; **MMR REGRESSED**
    (hit@10 0.90→0.75, target-shown 0.85→0.75 — diversity demotes the on-point
    case for pinpoint legal queries) → **MMR reverted to default-off**, code +
    `mmr_lambda` param retained for diversity-oriented surfaces. Artifacts:
    `benchmarks/caselaw/pr2/*.json`.
  - **Adversarial review** (4-dimension workflow + per-finding skeptic): no
    confirmed defect touched the critical invariants (byte-identical default
    return, rank-1 position-0, additive serializers all held). Two real fixes
    applied (`_chunk_excerpt` now provably ≤ budget incl. ellipses;
    `vector_search` return annotation); one finding declined with reasoning
    (bare try/except around the chunk fetch would be inconsistent with the
    surrounding un-wrapped essential queries); the rerank-cap change confirmed
    intentional + eval-clean.
  - **Open (carry to PR3+):** U-order ships on but the eval can't measure it
    (set-preserving — same cases shown, only reordered); revisit if a UI surfaces
    passages in list order. Pool-100 + 8000-char-cap rerank latency: p50 rc ~3.8s
    (vs hybrid ~3.1s) — acceptable, watch under load.
  - **Enterprise-readiness (candid): too soon to claim; on current evidence, not
    yet.** Two independent reasons, neither fixable by more tuning of PR2:
    1. *The A/B is underpowered.* n=20, Wilson CIs ≈ ±0.18 on hit@1 — the "7/8
       metrics better than `hybrid_rr`" is every metric moving ~one query, i.e.
       **inside the noise floor**. It's a smoke signal, not a ship gate. A real
       gate needs n in the hundreds across every query shape (citation,
       party-name, procedural, multi-part, adversarial), a held-out set, and
       human-rated relevance wired into CI with regression thresholds — plus
       latency-under-load / multi-tenant / red-team coverage that this eval has
       none of. Scope is also one jurisdiction (Iowa) on a favorable
       landmark-case slice.
    2. *The enterprise-critical safety properties are deliberately deferred.* The
       headline legal risk from the design (overruled law cited as good law) is
       **untouched** by PR2: `stale_warning` is structurally 0 because
       treatment/good-law currency is PR3 and abstention is PR4. Until those land
       the system will still confidently cite a bad case and stretch an adjacent
       rule rather than abstain. Absolute retrieval (hit@1 ~0.75, answerable
       ~0.75) is solid for a **lawyer-in-the-loop research assistant**, below the
       bar for any authoritative/autonomous use.
    What *is* already enterprise-grade is the **discipline**, not the numbers: one
    shared pipeline (no chat/MCP drift to test/monitor twice), green-for-green
    tests, and an eval harness that gated a real decision (MMR reverted on
    evidence). That machinery is the prerequisite for *earning* the claim once
    PR3/PR4 close the safety gaps and the eval set is scaled up.
- [x] **PR2.5 — Ingest the CourtListener citation-map (graph + depth).** ✅ DONE
  (2026-06-08; new — PR3 foundation, split out after researching CL's offerings.)
  - **Ingested:** streamed `citation-map-2026-03-31.csv.bz2` (522 MB, 76,959,991
    national rows) → **475,375 in-corpus Iowa edges** written as
    `CrossReference(source=CASELAW_GRAPH, weight=depth)`. `weight` now 100%
    populated (depth min 1 / max 70 / avg 1.79) — it was 100% NULL before.
    `caselaw_link` (#1) unchanged at 693,497 (source-scoping verified). Skips:
    76.3M citing-not-in-corpus, 205,901 cited-not-in-corpus, 1,836 sibling, 0
    self / 0 bad-depth. ~7 min, streamed (never decompressed to disk).
  - **Semantic spot-check passed:** the most-cited in-corpus cases are the
    expected Iowa landmarks (*In re P.L.* 1,502; *Meier v. Senecaut* 1,234; the
    foundational TPR/juvenile cluster); heaviest edge depth 70 (*State v. Short* →
    *State v. Ochoa*) = the deep-engagement the treatment pass should prioritize.
  - **Command:** `apps/ingestion_caselaw/management/commands/build_caselaw_citation_graph.py`
    (mirrors #1; idempotent delete-all-CASELAW_GRAPH-for-source + rebuild; internal
    edges only; self/sibling skip). 5 golden tests. Adversarially reviewed (one
    real fix: non-positive depth coerced to 1 so a corrupt row can't crash the
    PositiveIntegerField insert).
  - *Why this exists:* PR3's treatment classifier needs the **incoming-citation
    graph with depth** as its substrate (which later opinions cite a target, and
    how heavily — to prioritise the LLM budget and to be sure the negative-
    treatment scan sees every citing case). We have a citation graph today
    (`caselaw_link`, 693K edges) but it was built from inline `<a>` links in
    `html_with_citations`, so it carries **no depth** (`CrossReference.weight` is
    100% NULL) and `CASELAW_GRAPH` is empty. The `Case Law/CASELAW_INGESTION_PLAN.md`
    plan (L110) intended to use CL's `citation-map` for this but the build took
    the inline-link route instead.
  - *Key research finding (changes a design assumption):* CourtListener does **not
    publish citation *treatment*** for state courts — their AI citator (free.law,
    May 2025) is a SCOTUS-only, overruling-only proof-of-concept, not in the API/
    bulk data, no timeline. So "ingest treatment from CL" is **not** an option for
    Iowa; we ingest the **graph + depth** and build the treatment classifier
    ourselves (design §5). CL's citator *does* validate that approach (EyeCite +
    ±6 sentences + LLM; Claude 3.5 Sonnet >90% recall, F1 >80% on overruling) and
    gives a benchmark. Leave a `TreatmentFlag.source="courtlistener"` hook for when
    their citator generalises.
  - *Scope:* download `bulk-data/citation-map-<date>.csv.bz2` (~500 MB compressed,
    `search_opinionscited`: `id, depth, citing_opinion_id, cited_opinion_id`),
    stream-filter via `csv_stream.open_bulk_csv` to in-corpus Iowa edges (join on
    `cl_opinion_id`, which every node carries), and write
    `CrossReference(source=CASELAW_GRAPH, weight=depth)`. New command
    `build_caselaw_citation_graph` mirroring `backfill_caselaw_cross_references`
    (#1); idempotent (delete CASELAW_GRAPH edges, rebuild). Never decompress to
    disk. Resolves §8 Q3.
- [ ] **PR3 — Treatment graph + deterministic v1 good-law flag.**
- [ ] **PR4 — Verify+abstain extraction and stale-use gate.**
- [ ] **PR5 — LLM-assisted treatment v2 + (optional) claim-level NLI + query rewrite.**

## Open questions (from design §8) — answer before the PR that needs them

1. (PR2) ✅ RESOLVED — caselaw-only chunk excerpts; statutes keep the prefix.
2. (PR4) Hard-block `severity>=5` answers vs advisory red flag? + severity threshold.
3. (PR3) Re-pull CL OpinionsCited citations CSV for the loaded Iowa clusters (bulk
   archived to DO Spaces).
4. (PR3) Citing-sentence sourcing: re-scan `body_text` vs re-ingest `html_with_citations`.
5. (PR3) `source_metadata["treatment"]` cache vs dedicated `Treatment` table.
6. (PR1) Add as-of date to retrieval signature now, or defer? Recommend **defer**
   (PR1 stays behavior-preserving).
7. (PR2) ✅ RESOLVED — pool widened 50→100; citation lane bypasses the reranker.
8. Keep the OpenAI tool-loop in `chat.py` (not extracted to `answer.py`)? Recommend yes.

## Resume notes

- 2026-06-07: design doc written; branch cut; baseline green confirmed.
- 2026-06-07: **PR1 coded, verified, and adversarially reviewed** (uncommitted in the
  working tree). Tests green-for-green vs baseline; `api→mcp_server` import removed.
  `cluster_id` already correctly populated for dedup.
- 2026-06-08: **PR2 coded, eval-gated, and adversarially reviewed** (uncommitted).
  §8 Q1/Q7 resolved (caselaw-only excerpts; cite-lane bypass + pool 100). Full suite
  380/1-known-red. Real-corpus A/B drove the one design change from the plan: **MMR is
  default-OFF** (it regressed pinpoint retrieval); dedup + chunk-excerpt + U-order +
  cite-bypass are on and net-positive vs the production `hybrid_rr` path. Eval artifacts
  in `benchmarks/caselaw/pr2/`. PR1 committed as `5ca5243`; PR2 committed as `acc5337`.
- 2026-06-08: **PR2.5 done** — CL `citation-map` ingested (475,375 in-corpus Iowa edges,
  `CrossReference.weight=depth` now populated; `caselaw_link` untouched). Research
  finding: CL publishes the citation **graph+depth** but **not treatment** for state
  courts (their citator is SCOTUS-only PoC), so we build the Iowa treatment classifier
  ourselves. §8 Q3 resolved. Command + 5 tests adversarially reviewed (uncommitted).
  Next action: **PR3** — treatment graph + deterministic v1 good-law flag. Substrate is
  now ready (incoming CASELAW_GRAPH edges + depth). Answer §8 Q4/Q5 first (citing-sentence
  re-scan vs re-ingest? `source_metadata["treatment"]` cache vs `Treatment` table?). The
  `TreatmentFlag` dataclass + per-passage `treatment` field already exist (PR1
  forward-compat), emitting the "unknown" default — PR3's `annotate_treatment` populates
  them by walking each target's incoming CASELAW_GRAPH edges (depth-prioritized).
