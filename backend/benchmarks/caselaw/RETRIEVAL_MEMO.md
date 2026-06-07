# Decision Memo: Caselaw Retrieval Pipeline

**Author:** Lead retrieval engineer (multi-agent review) · **Date:** 2026-06-07 · **Baseline commit:** 3f83057
**Eval:** `eval_caselaw.py`, n=20 landmark Iowa cases, scope=`iowa-caselaw`, voyage-law-2 @1024-dim, `hnsw.ef_search=200`

---

## 1. Current state

### How the pipeline works, end to end

1. **Embed (offline).** `voyage.py` is a thin env-driven wire client (`VOYAGE_EMBED_MODEL`, default `voyage-law-2`, hard 1024-dim). Caselaw is chunked by `chunking.py` (paragraph→sentence→hard-split, target 800 / overlap 120 tokens) with a case-caption header (`State v. Smith, 987 N.W.2d 123 (Iowa 2019) — Lead Opinion`) prepended into the embedded text and budgeted out of the token target. `embeddings.py` embeds chunks as `INPUT_TYPE_DOCUMENT`, idempotent on `content_hash != embedding_source_hash`. Full corpus = ~496K `NodeChunk` rows.
2. **Retrieve.** `vector_search()` (search.py:448) embeds the query as `INPUT_TYPE_QUERY`, runs two HNSW sub-queries — whole-`NodeVersion` (statutes/rules) and passage-`NodeChunk` (caselaw, over-fetched `CHUNK_OVERFETCH=5×limit` then rolled up best-chunk-per-version) — and unions them. Four lexical/structured retrievers join it: `fts` (`ts_rank_cd`), `trigram` (heading-only), `citation` (exact reporter cite → score 1.0), `case_name`.
3. **Fuse.** `reciprocal_rank_fusion()` (search.py:587) sums `1.0/(k+rank)` with **k=60 and no per-retriever weight** — confirmed in code (line 605); `raw_score` is captured but used only for debug (line 606). Exact-cite hits are prepended above the fused list.
4. **Rerank + serve.** Voyage `rerank-2.5` is applied in **exactly one place** — `chat.py:_enriched_search` (pool 20 → top 6, reranked on heading+full body). `ef_search=200` is set once per connection in `signals.py`.

### Honest verdict on quality

The dense retriever is genuinely good and rerank is excellent — but **the two best levers are mostly off the production path**, and the one fusion mechanism that is on the path actively destroys quality.

| config | MRR | hit@1 | hit@5 | hit@10 |
|---|---|---|---|---|
| vector | 0.733 | 0.55 | 0.90 | 1.00 |
| fts | 0.146 | 0.10 | 0.20 | 0.25 |
| **hybrid** | **0.479** | **0.20** | 0.85 | 0.95 |
| vector_rr | 0.804 | 0.70 | 0.90 | 1.00 |
| **hybrid_rr** | **0.842** | **0.75** | 0.95 | 1.00 |

**Headline problem #1 — hybrid is WORSE than vector via equal-weight RRF (MRR 0.479 < 0.733; hit@1 0.20 < 0.55).** Mechanism, confirmed in `reciprocal_rank_fusion`: at rank 1 every retriever contributes an identical `1/(60+1)=0.0164`, and `k=60` makes the per-rank decay so flat that a rank-1 dense hit (0.0164) barely beats a rank-3 hit (0.0159) — a 3% gap. So on a conceptual holding query (where `fts` MRR is 0.146 and trigram is near-noise), two weak retrievers agreeing on a *wrong* case (~0.0328 combined) outvote vector's single correct #1. Magnitude is discarded entirely (line 605 ignores `raw_score`): a cosine-0.72 true match and a cosine-0.31 distractor at adjacent ranks fuse to nearly the same mass. **Fusion gives the two noise retrievers ⅔ of the vote on exactly the queries where only the dense retriever has signal.**

**Headline problem #2 — the public search UI never uses embeddings or rerank.** `/api/browse/search` calls `hybrid_search(use_vector=False)` (browse.py:985), and rerank lives only in chat. So the ~496K-chunk index (~$34–44 to produce) is dead weight for the main surface: every public caselaw query is served by FTS (+ single-token trigram + cite/name) — **MRR 0.146 / hit@5 0.20 vs the 0.733 / 0.90 the embeddings already enable.** The public UI runs at roughly one-fifth of achievable answer quality, and because the eval drives `hybrid_search` directly, **the eval does not measure what users actually get.**

Secondary but real: the embedder is a generation behind (voyage-law-2 is below voyage-3-large on the legal-specific MLEB benchmark by +6.08 NDCG@10); 800/120 chunking and HNSW build params (m=16/ef_construction=64) were never swept; filtered-ANN under-return is acknowledged but unmitigated; and at n=20 every headline number has a ±0.17 Wilson CI — the rerank "lift" (0.55→0.75 hit@1) is **not statistically distinguishable**.

---

## 2. Ranked recommendations

Ordered by impact-per-effort. Every row ties to an audited weakness AND a research source, and every row is testable on `eval_caselaw`.

### Quick wins — ship this week

| # | Change | Expected impact | Effort | Conf. | Audit weakness it fixes | Research source |
|---|---|---|---|---|---|---|
| 1 | **Wire vector + rerank into `/api/browse/search`** for caselaw scope (mirror chat: `use_vector=True`, rerank pool→top-k). Edge-cache by `(query,scope,page)`. | Public caselaw MRR ~0.146 → ~0.80+ | **S** | RETRIEVAL: "use_vector=False"; RERANK: "biggest lever in one entrypoint" | TDS "Rerankers Aren't Magic"; Weaviate hybrid-fusion |
| 2 | **Add per-retriever weights to `reciprocal_rank_fusion`** (`weight[name]·1/(k+r)`): vector=1.0, fts=0.3, trigram=0.2, case_name=0.5. | hybrid MRR 0.479 → toward vector 0.733 | **S** | equal-weight RRF demotes the dense rank-1 hit (line 605) | Bruch/Gai/Ingber arXiv:2210.11934; Azure weighted-RRF; OpenSearch |
| 3 | **Raise rerank candidate pool 20 → 50** (`CHAT_CANDIDATE_POOL`; sweep 50/75), keep top-6 display. | recovers hits buried past rank 20 | **S** | pool=20 below the 50–75 floor | ZeroEntropy 2026; Voyage rerank-2.5 (retrieve ≤100) |
| 4 | **Enable pgvector iterative scan** in `signals.py`: `hnsw.iterative_scan = strict_order`, `hnsw.max_scan_tuples = 20000`. | filtered (court/status) recall → ~100% | **S** | filtered-ANN under-return (search.py:551) | pgvector 0.8 README; AWS Aurora pgvector 0.8 |
| 5 | **Add Wilson 95% CIs + per-stratum reporting** to `eval_caselaw`. | makes every delta falsifiable | **S** | n=20 → no CIs/significance | Wilson interval; Voorhees TREC resampling |

### Bigger bets

| # | Change | Expected impact | Effort | Conf. |
|---|---|---|---|---|
| 6 | **Migrate voyage-law-2 → voyage-3-large @1024-dim** (no schema change; reset `embedding_source_hash`, re-run sharded `embed_chunks`). | +6.08 NDCG@10 on legal MLEB | **M** (~$65) | high |
| 7 | **Convex-combination fusion** (min-max normalize per retriever, weighted sum) replacing rank-only RRF; supersedes #2. | preserves dense score-magnitude gap | **M** | medium |
| 8 | **Grow eval to ~100 queries**, stratified, graded multi-relevant qrels (target=2, sibling=1), 20% holdout; keep the 20 as a "mini" tier. | detects 5–10pt deltas | **M** | high |
| 9 | **A/B voyage-context-3 vs voyage-3-large+header**; isolate the manual header (re-embed `context_header=''`). | possibly drop the hand-rolled header | **M** | medium |
| 10 | **Sweep chunk target {400,512,640,800} × overlap {0,60,120}; REINDEX HNSW at ef_construction=128.** | 800 is above the legal precision band | **M** | medium |
| 11 | **Add embed-time token guard** (>16K silent truncation; guard the whole-NodeVersion path too). | eliminates silent truncation | **S–M** | high |

---

## 3. Embedding model decision

**Migrate to `voyage-3-large` at `output_dimension=1024`.** On MLEB (arXiv:2510.19365, Oct 2025) — the only public legal-specific retrieval benchmark covering US caselaw *and* statutes — voyage-3-large = **85.71 NDCG@10** vs voyage-law-2 = **79.63** (**+6.08**); it also beats voyage-3.5 (84.07) and OpenAI-3-large (78.91, *below* the current model). Both are Matryoshka models supporting 256/512/**1024**/2048, so pinning 1024 reuses `VectorField(dimensions=1024)` and both HNSW indexes verbatim — only stored vectors change. Cost: 496K chunks ≈ 363M tokens → **~$65 one-time**, via the existing env-driven, idempotent, 4-shard `embed_chunks`. Deploy model + re-embed **atomically** (query and document vectors must come from the same model). Budget pick: **voyage-3.5 @1024** = +4.44 for ~$22. Defer voyage-context-3 (not on the legal benchmark) and Kanon 2 (new vendor, +0.32).

---

## 4. Architecture decision: should search become `apps/search`?

**No — not now. Keep retrieval in `apps/corpus/`, enforce the boundary with an import-linter contract.** The corpus/search seam runs *through the models module, not between modules*:

- `NodeChunk` is a retrieval artifact but lives in `corpus/models.py` and FKs `corpus.NodeVersion`; `NodeVersion.embedding`/`search_vector` are retrieval columns on a corpus model. A real split needs a `SeparateDatabaseAndState` move — messier than today, zero DB benefit.
- `search.py` couples to corpus via **hardcoded raw-SQL table literals** (`corpus_nodeversion`, `corpus_node`, …). Moving the file relocates the coupling without loosening it.
- `signals.py` back-imports `HNSW_EF_SEARCH` from `services.search` (search→corpus today). Extraction flips this to corpus→search, **creating the import cycle the split was meant to avoid**.
- `hybrid_search` is *already* source-agnostic (parameterized by `source_slug`/`metadata_contains`); no second corpus or consumer exists that a boundary would unlock.

**Proposed boundary instead:** keep `apps/corpus/services/`, add a layered import-linter contract — a public façade (`hybrid_search`, `SearchHit`) as the only entry for `apps/api` / `apps/mcp_server` / `chat.py`; the wire clients (`voyage.py`, `rerank.py`, `query_expansion.py`) stay a leaf layer banned from importing `apps.corpus.models`. **Revisit when** a second non-corpus consumer or a second independent corpus appears.

---

## 5. Experiment plan

**Make the harness trustworthy first, then run A/Bs in dependency order. Bar: hybrid must never score below pure vector on conceptual queries.**

### Phase 0 — instrument the eval (rec #5, #8)
1. Add **Wilson 95% CIs + paired permutation/sign test** to `_aggregate`/`_report`. Fix the `ef_search` int-vs-string snapshot inconsistency.
2. Add a **`recall@100/@500` curve before rerank** so a pool-truncation failure is a distinct, fixable cause, not hidden in MRR.
3. Grow to **~100 queries stratified A/B/C/D (~25 each)** with **graded multi-relevant qrels**; hand-verify every target against the DB; keep the 20 as a "mini" tier; hold out 20%.
4. Score the **distractor field** the harness currently ignores → report a "distractor-outranked rate."

### Phase 1 — fusion (rec #2, #7), on current voyage-law-2
5. Baseline re-run with new CIs.
6. **A/B weighted RRF** (vector=1.0, fts=0.3, trigram=0.2, case_name=0.5). Target: hybrid MRR 0.479 → ≥ vector 0.733.
7. **A/B convex-combination fusion** vs weighted RRF; sweep the vector-vs-lexical weight; adopt the held-out winner.
8. **A/B rerank pool 20 vs 50 vs 75** (top-6 fixed).

### Phase 2 — embedder + chunking (rec #6, #9, #10), on the winning fusion
9. **A/B voyage-3-large vs voyage-law-2** @1024-dim.
10. **Isolate the header** (`context_header=''` vs current).
11. **A/B voyage-context-3** vs winner of #9 (adopt only if it wins here).
12. **Sweep** `target_tokens ∈ {400,512,640,800}` × `overlap ∈ {0,60,120}`; **REINDEX at ef_construction=128**.

### Phase 3 — serving + infra (rec #1, #4, #11)
13. **Filtered-recall test** before/after `iterative_scan=strict_order`; then try `CHUNK_OVERFETCH=2`.
14. **Wire winning config into `/api/browse/search`** (+ rate-limit, since browse is `auth=None`).
15. **Embed-time token guard** + over-16K metric; backfill-scan the 496K corpus.

**Each recommendation ships only after its A/B shows a Wilson-CI-separated win over the prior baseline on the held-out + stratified set — never on the 20-query mini tier alone.**
