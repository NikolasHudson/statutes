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

- [ ] **PR1 — Behavior-preserving extraction (NO quality change).** ← IN PROGRESS
  - New `apps/corpus/services/retrieval.py` (`retrieve_context()` reproducing today's
    chat enrichment exactly: pool 50, top 6, 9000/2000 excerpt budgets, `effective_from`,
    current weighted RRF) + `apps/corpus/services/corpus_tools.py` (direct-lookup
    wrappers, no MCP coupling).
  - Repoint `chat.py._enriched_search` and `mcp_server/tools.search_statutes_tool` at
    `retrieve_context`; repoint both surfaces' lookup tools at `corpus_tools`.
  - **Delete the `apps.api → apps.mcp_server` import.**
  - Trap: two rerank doc-char budgets and the dict key shape (`node["id"]` vs
    `node_version_id`). Mitigate with golden-output tests.
  - Proves: `eval_caselaw` byte-identical metrics before/after; `test_tools.py`,
    `test_search.py`, chat tests green. **No metric should move.**
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

- 2026-06-07: design doc written; branch cut; baseline green confirmed; **PR1 not
  yet coded**. Next action: extract `retrieve_context` + `corpus_tools`, repoint both
  surfaces, prove no metric moved.
