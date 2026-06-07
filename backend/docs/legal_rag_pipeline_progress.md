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
- [ ] **PR2 — Decision-cluster dedup + MMR + chunk-aware offsets.**
- [ ] **PR3 — Treatment graph + deterministic v1 good-law flag.**
- [ ] **PR4 — Verify+abstain extraction and stale-use gate.**
- [ ] **PR5 — LLM-assisted treatment v2 + (optional) claim-level NLI + query rewrite.**

## Open questions (from design §8) — answer before the PR that needs them

1. (PR2) Chunk excerpts for statutes too, or caselaw-only? Recommend caselaw-only.
2. (PR4) Hard-block `severity>=5` answers vs advisory red flag? + severity threshold.
3. (PR3) Re-pull CL OpinionsCited citations CSV for the loaded Iowa clusters (bulk
   archived to DO Spaces).
4. (PR3) Citing-sentence sourcing: re-scan `body_text` vs re-ingest `html_with_citations`.
5. (PR3) `source_metadata["treatment"]` cache vs dedicated `Treatment` table.
6. (PR1) Add as-of date to retrieval signature now, or defer? Recommend **defer**
   (PR1 stays behavior-preserving).
7. (PR2) Pool 50→100 latency; should the citation lane bypass the reranker? Recommend yes.
8. Keep the OpenAI tool-loop in `chat.py` (not extracted to `answer.py`)? Recommend yes.

## Resume notes

- 2026-06-07: design doc written; branch cut; baseline green confirmed.
- 2026-06-07: **PR1 coded, verified, and adversarially reviewed** (uncommitted in the
  working tree). Tests green-for-green vs baseline; `api→mcp_server` import removed.
  Next action: PR2 — decision-cluster dedup + MMR + chunk-aware offsets (answer §8 Q1/Q7
  first: caselaw-only chunk excerpts? citation lane bypasses reranker?). `cluster_id` is
  already correctly populated for dedup. Commit strategy for the working tree is pending
  the user's decision.
