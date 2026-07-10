# Phase 3 baselines — locked 2026-07-09 (commit 7217c94)

The eval gate for every Phase 3 ranking change (first up: authority-weighted
ranking, plan `cached-riding-beaver.md` Phase 3 item 1). Any adjustment must be
compared against THESE numbers, re-run with the IDENTICAL invocation below.
Ship bar (per RETRIEVAL_MEMO): a Wilson-CI-separated win on the target metric
with **no regression outside the CI noise floor on the other three sets** —
the fact-pattern/pinpoint sets are the counter-gate for authority weighting
(those queries legitimately want the applying case, not the seminal one).

## Environment

- voyage-law-2 (1024-dim) + rerank-2.5, hnsw.ef_search=200, deep=100
- rc config = the production `/api/research/search` natural path exactly:
  `retrieve_context(use_vector=True, rerank=True, candidate_pool=100,
  display_limit=50, dedup_clusters=True, u_order=False, MMR off)`.
  NOTE: earlier snapshots (pre-Phase-3) ran rc with u_order ON and display 10;
  rc numbers are NOT comparable across that boundary — raw configs are.

## Reproduction

```bash
python manage.py eval_caselaw --rerank --rerank-pool 50 --use-retrieve-context \
  --rc-no-u-order --k 1,3,5,10,50 \
  --queries apps/corpus/data/<SET>.json \
  --out benchmarks/caselaw/<RUN>.json
python manage.py eval_search --k 10
```

Sets: `caselaw_eval_queries.json` (holdings), `caselaw_eval_queries_categories.json`,
`caselaw_eval_queries_categories2.json`, `caselaw_eval_queries_authority.json` (NEW).
Snapshots: `phase3_baseline_{holdings,categories,categories2,authority}.json`
(+ `_console.txt` alongside, and `phase3_baseline_eval_search_k10.txt`).

## Headline — production path (rc) per set

| set | n | MRR | hit@1 | hit@5 | hit@10 | hit@50 | recovered |
|---|---|---|---|---|---|---|---|
| holdings | 20 | 0.772 | 0.65 | 0.90 | 0.90 | 1.00 | 100% |
| categories | 20 | 0.711 | 0.65 | 0.90 | 0.90 | 0.95 | 95% |
| categories2 | 20 | 0.801 | 0.75 | 0.85 | 0.90 | 1.00 | 100% |
| **authority (NEW)** | 23 | **0.324** | **0.22** | **0.43** | 0.52 | 0.74 | 74% |

All configs, authority set:

| config | MRR | hit@1 | hit@5 | hit@10 | hit@50 | recovered |
|---|---|---|---|---|---|---|
| vector | 0.417 | 0.26 | 0.57 | 0.65 | 0.83 | 91% |
| fts | 0.171 | 0.04 | 0.35 | 0.39 | 0.61 | 74% |
| hybrid | 0.419 | 0.30 | 0.52 | 0.70 | 0.87 | 91% |
| vector_rr | 0.334 | 0.22 | 0.43 | 0.52 | 0.83 | 83% |
| hybrid_rr | 0.376 | 0.26 | 0.48 | 0.57 | 0.87 | 87% |
| rc (prod) | 0.324 | 0.22 | 0.43 | 0.52 | 0.74 | 74% |

(Raw-config numbers on the other three sets are in the snapshots; holdings
vector MRR 0.733 / hybrid 0.644 reproduce the Phase-1 gate byte-identically,
and eval_search holds at 29/30 hit@10.)

## What the authority baseline shows

1. **The reranker actively HURTS canonical-authority queries** — the only set
   where rerank is net-negative: vector MRR 0.417 → vector_rr 0.334; hybrid
   0.419 → hybrid_rr 0.376. The cross-encoder scores passage↔query fit, so a
   progeny case QUOTING the canonical rule outscores the canonical statement
   itself. Sharpest demotions (vector rank → rc rank): Gust 1→20, Bruegger
   1→22, Heemstra 2→25, Thompson v. Kaczinski 2→27.
2. **It is an ordering problem, not recall**: 74–87% of canonical targets are
   inside the visible top-50 pool. A post-rerank authority blend (cited_by /
   court level / precedential status) has the raw material on the page.
3. **Two genuine recall misses** (vector >100): Frederici (custody
   modification) and Formaro (sentencing discretion) — their doctrinal language
   is boilerplate quoted verbatim in hundreds of progeny, so the seminal
   opinion is not lexically/semantically distinctive. Authority blending can
   only fix these if the candidate pool ever contains them (Formaro also has a
   duplicate-cluster artifact, see the query-set header).
4. rc ≈ hybrid_rr minus a few recovered targets (rc caps display at 50);
   consistent with rc being hybrid+rerank+dedup.

## Latency baselines

- rc path inside the eval (batch, warm embedder): p50 ≈ 2.4–2.8s, p90 ≈ 3.6–4.8s
  per set (in each snapshot's `latency_ms.rc`).
- Dev SearchLog (n=45 natural queries, 2026-07-09): p50=1691ms, p90=4754ms,
  max=5858ms; boolean p50=347ms; citation p50=544ms. Phase 3 latency work
  (item 3) should be judged against prod SearchLog p90 once enough rows exist.

## Next (from the plan, in order)

1. ~~Authority-weighted ranking~~ SHIPPED same day — see below.
2. Rate-limit/quota `/api/research/search` (pre-beta blocker).
3. Latency tuning from SearchLog p90 (pool 100→60, doc chars 8000→4000, or
   rerank-to-display-depth) — all eval-gated against these same snapshots.

---

# Phase 3 item 1 RESULT — authority blend shipped 2026-07-09 (same day)

`retrieve_context(authority_weight=0.25)` wired into the `/api/research/search`
natural path (`NATURAL_AUTHORITY_WEIGHT`, research.py). Formula (retrieval.py
`_authority_reorder`, post-rerank / post-dedup / pre-display-slice):

    blended = rerank_relevance + 0.25 * min(log1p(cited_by)/log1p(1500), 1)

caselaw hits permute among caselaw-occupied positions only; citation-pinned
hits stay pinned; NEGATIVE-treatment decisions get no boost; skipped when
rerank is off. Adds one indexed citation-graph aggregate (~40–70ms).

## How 0.25/absolute-norm was chosen

1. Flat POOL-normalized sweep (`phase3_authority_w{0.1..0.5}.json`): authority
   set monotone ↑ (MRR 0.324→0.566 at w=0.5) but the w=0.3 counter-gate
   (`phase3_{set}_w0.3.json`) FAILED categories2 0.801→0.612: pool-relative
   norm gives a 44-cite case the same full boost as a 1,205-cite case whenever
   the pool is low-cited, flipping fact-pattern queries whose right answer is
   a recent lightly-cited case.
2. Offline formula grid over dumped per-query pools (83 queries × (relevance,
   cited_by) — rel-score probe showed authority targets trail leaders by
   0.12–0.28 rel while categories2 targets LEAD by 0.08–0.14): absolute
   log1p norm at w≈0.25 dominates; relevance-gated decay bands can't separate
   the regimes (killing deep-demotion recovery kills the point).
3. Real-harness verification (`phase3_{set}_absw0.25.json`):

| set | rc baseline | rc absw0.25 | verdict |
|---|---|---|---|
| authority | 0.324 / h@5 0.43 | **0.487 / h@5 0.61** (h@10 .52→.74, recov 74→83%) | target ↑↑ |
| holdings | 0.772 / h@5 0.90 | 0.785 / **h@5 1.00, h@10 1.00** | ↑ |
| categories | 0.711 / h@1 0.65 | 0.757 / h@1 0.70 | ↑ |
| categories2 | 0.801 / h@1 0.75 | 0.784 / h@1 0.75 (h@5 .85→.80) | −0.017 MRR, inside CI noise |

Sum MRR across sets 2.609 → 2.813. Live smoke: "pierce the corporate veil"
now returns Briggs (cited_by 66) at #1 (was: top-5 all application cases).

## Known costs + residual gaps (do not re-litigate without new data)

- **Recent-low-cited-target tension** (the categories2 hit): State v. Wright
  3→11, Burnett 9→11 & 30→44. cited_by is age-confounded; a 2021–2023 target
  can't out-boost old canonicals. Next lever if SearchLog shows real queries
  suffering: recency-aware citedness (cites/year) or intent-aware weight
  (doctrine-seeking vs fact-pattern) — NOT a bigger flat weight.
- **Gacke demotions are jurisprudentially correct but scored as misses**:
  Gacke is overruled (Garrison 2022), carries a negative treatment flag, so
  it gets no boost while its neighbors do (holdings 1→3, categories 5→19).
  The eval labels predate the currency axis.
- Authority-set residuals: Winter/Frederici/Sullivan/Formaro stay >50 —
  RECALL misses (boilerplate-quoted doctrine; seminal opinion not in pool
  competitively); Heemstra/Plain mid-pack (their progeny are themselves
  heavily-cited canonicals). Not fixable by ordering.
- `authority_court_bonus` exists (default 0.0) but is unshipped/unswept.

---

# Phase 3 item 3 RESULT — latency tuning shipped 2026-07-09 (same day)

The plan assumed rerank was the cost; profiling said otherwise. Median stage
times on dev (natural caselaw query, warm embed):

| stage | ms | verdict |
|---|---|---|
| version-level ANN branch (caselaw scope) | ~470 EVERY query | pure waste — filter rejects all rows, iterative scan walks to max_scan_tuples returning [] |
| trigram retriever | ~450 | active harm on sentence queries (see gate) |
| rerank 100×8k | ~500, stable | NOT the bottleneck; 8k→4k saves only ~130ms |
| chunk ANN | ~40 warm / 1–2s cold buffers | dev-box RAM pressure, not code |
| embed (cold Voyage) | ~150 | already cached (14d TTL) |
| authority blend SQL | ~40–70 | fine |

## Shipped changes

1. **Granularity-aware branch skip** (`_embedding_granularities`, search.py):
   scoped vector search only queries the granularity the source is embedded at
   (caselaw=chunks, statutes=versions), probed via cached EXISTS (600s TTL).
   Identical results (the skipped branch returned nothing), −~470ms on every
   caselaw-scoped query, all callers (search/chat/MCP/eval).
2. **Trigram OFF for natural mode** (`NATURAL_USE_TRIGRAM=False`, research.py →
   `retrieve_context(use_trigram=)` → `hybrid_search`): −~450ms on every
   natural query, all scopes. Boolean/citation modes and the case-name
   retriever are unaffected.
3. **REJECTED: rerank_doc_chars 8000→4000** — the isolation eval attributed
   real quality losses to it (Meier 1→2, Ledezma 1→5, Standard Water 1→2,
   authority h@1 −0.08 vs 8k) for only ~130ms. Keep 8000.

## Quality gate (rc, authority+no-trigram+8k vs authority-only shipped)

| set | before | FINAL | |
|---|---|---|---|
| authority | 0.487 / h@1 0.39 / h@5 0.61 | **0.525 / 0.43 / 0.65** | ↑ |
| holdings | 0.785 / 0.65 / 1.00 | 0.785 / 0.65 / 1.00 | = |
| categories | 0.757 / 0.70 / 0.90 | 0.757 / 0.70 / 0.90 | = |
| categories2 | 0.784 / 0.75 / 0.80 | 0.782 / 0.75 / 0.80 (h@10 .85→.95) | = |

Trigram was not just slow — removing it IMPROVED authority MRR (+0.038) and
categories2 h@10 (+0.10). Snapshots: `phase3_{set}_notri8k.json` = the FINAL
shipped config; `phase3_{set}_fast.json` = the rejected 4k variant.

## Measured end-to-end (dev, quiet box, warm)

retrieve_context production kwargs: old p50 ~2.2s → **FINAL p50 ~0.8s** (best
pass 564–1077ms across 8 queries). Occasional ~5s spikes are chunk-index
buffer eviction on the droplet (hits old config equally; prod has its own
profile — judge from prod SearchLog.latency_ms p90 now that both fixes ship).

## Residual latency levers (unshipped, in value order)

- Chunk ANN cold-buffer I/O: the 1024-dim float index is ~2GB; halfvec
  quantization or more RAM would cut the cold tail. Bigger bet.
- Unscoped (all-sources) searches still run both ANN branches by necessity;
  version-skip only helps caselaw-scoped queries. Trigram-off helps all.
- Rerank pool 100→60 untested against the authority blend (deep recoveries
  like Hansen@51 need the wide pool — do not trim without re-gating).
- Parallelize embed/fts/vector inside hybrid_search (threads + per-thread DB
  connections) — invasive, ~150–500ms upside.
