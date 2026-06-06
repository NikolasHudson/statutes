# Embedder Upgrade Result: `voyage-law-2` → `voyage-4-large`

Measured 2026-06-05 with `python manage.py benchmark_embeddings` (commit `d36d718`),
same eval sets / methodology / corpus as the [baseline](./analysis.md). Both
models run at **1024-dim** (each model's default) against the same
`NodeVersion.embedding` column — no schema change. Snapshots:
[`baseline_voyage-law-2.json`](./baseline_voyage-law-2.json) ·
[`candidate_voyage-4-large.json`](./candidate_voyage-4-large.json).

All deltas below are on the **vector retriever** (the only thing the embedder
changes). Results were confirmed deterministic — every flipped query reproduced
its recorded rank on a live re-run — and the embedder-independent `fts` numbers
are byte-identical across the two runs, confirming the harness is stable.

> **FINAL VERDICT (2026-06-05): keep `voyage-law-2` — do not adopt voyage-4-large.**
> The sections below show the *pre-rerank* picture (mixed: Code up, Rules down).
> But the product runs a reranker, and the **full 2×2 with `rerank-2.5`** (see the
> [Reranking section](#reranking-rerank-25-changes-the-picture)) shows that on the
> production path (`hybrid + rerank`), voyage-law-2 **wins Code** (0.983 vs 0.932
> hit@5) and **ties Rules** (0.982). The reranker washes out 4-large's vector
> gains while 4-large's new blind spots survive. **The lever that actually helps
> is the reranker (bump `rerank-2`→`rerank-2.5`), not the embedder.** Snapshots:
> [law-2+rerank](./candidate_voyage-law-2_rerank-2.5.json) ·
> [4-large+rerank](./candidate_voyage-4-large_rerank-2.5.json).

## Verdict: mixed, not a clean upgrade *(pre-rerank — see reranking section)*

> **`voyage-4-large` improves Iowa Code, regresses Iowa Court Rules.** It is a
> stronger *general* / conceptual matcher (paraphrase, fact-pattern scenarios,
> vocabulary-mismatch lookups) but a weaker *legal-specialized* one (direct
> procedural rules, citation-style lookups). The win on Code is concentrated in
> deep-rank quality (MRR, hit@1, hit@10); top-5 success is roughly flat on Code
> and **down ~5 points on Rules**.

| | Iowa Code (n=59) | Iowa Court Rules (n=56) |
|---|---|---|
| **vector MRR** | 0.733 → **0.795** (+0.061) | 0.838 → **0.795** (−0.043) |
| vector hit@1 | 0.627 → 0.695 (**+0.068**) | 0.768 → 0.714 (**−0.054**) |
| vector hit@5 | 0.898 → 0.915 (+0.017) | 0.929 → 0.875 (**−0.054**) |
| vector hit@10 | 0.898 → 0.949 (**+0.051**) | 0.982 → 0.929 (**−0.053**) |
| vector nDCG@10 | 0.768 → 0.818 (**+0.050**) | 0.845 → 0.809 (−0.035) |
| unrecoverable (gold not in top-100) | 3 → 3 (*different 3*) | 1 → **3** |

## What moved, by query class (vector hit@5)

| Corpus / class | n | law-2 → 4-large | |
|---|--:|---|---|
| Code · paraphrase | 9 | 0.78 → **1.00** | **+0.22** |
| Code · keyword | 18 | 0.94 → 0.94 | +0.00 |
| Code · substantive (NL) | 29 | 0.93 → 0.90 | −0.03 |
| Rules · scenario | 5 | 0.80 → **1.00** | **+0.20** |
| Rules · substantive | 44 | 0.95 → 0.89 | **−0.07** |
| Rules · citation_lookup | 2 | 1.00 → 0.50 | **−0.50** |

The signal is consistent: **conceptual/loose queries get better, direct/
procedural lookups get worse.** voyage-4-large generalizes the query intent;
voyage-law-2's domain tuning was better at matching the precise, formulaic
language of procedural rules and named-section lookups.

## The headline wins — Code's hard cases solved

The three provisions the baseline flagged as *unrecoverable* (not even in the
top-100) — pure vocabulary-mismatch — jumped to **rank 1**:

| Query | Gold | law-2 rank | 4-large rank |
|---|---|--:|--:|
| "investment standards for retirement fund" | `97B.7A` | — (not in top-100) | **1** |
| "early retirement date IPERS" | `97B.47` | — | **1** |
| "How does Iowa law define theft?" | `714.1` | — | **1** |
| "what is sexual abuse under iowa law" | `709.1` | 17 | **1** |
| "rules referring to other statutes" | `4.3` | 23 | **2** |

## The regressions — and they hit high-traffic provisions

voyage-4-large traded Code's old blind spots for new ones, and lost ground on
core Rules procedure. Several queries that worked at **rank 1–4** fell out of the
top-100 entirely:

| Corpus | Query | Gold | law-2 rank | 4-large rank |
|---|---|---|--:|--:|
| Code | "Under the Iowa Code's rules of construction, how are words … construed" | `4.1` | **1** | — |
| Code | "what age qualifies as a child for juvenile justice" | `232.2` | 4 | — |
| Code | "Is an injured worker entitled to medical care under … workers' comp" | (wc) | 3 | — |
| Code | "place of confinement for felons" | `902.5` | 4 | 8 |
| Rules | "deadline to file a motion to enlarge or amend findings" | `1.904` | **1** | — |
| Rules | "requirements for a motion for summary judgment" | (sj) | 4 | — |
| Rules | "commence and certify a class action" | `1.261/1.262` | 2 | — |
| Rules | "how many CLE hours must an Iowa lawyer" | (cle) | 4 | 8 |

These are not obscure: rules of statutory construction (`4.1`), the juvenile
"child" definition (`232.2`), summary-judgment and post-trial-motion deadlines
are bread-and-butter lookups. Losing them from the top-100 is a real product risk.

## Calibration & latency

- **Absolute cosine dropped** (Code top-1 sim p50 0.577 → 0.531; Rules 0.591 →
  0.515). Ranking is unaffected (cosine ordering is what matters), but **any
  similarity threshold** — abstention cutoffs, "low-confidence" UI badges — tuned
  for voyage-law-2 must be **re-tuned** for voyage-4-large; the same number means
  something different.
- **Latency is a wash** (same dim): query embed p50 175 → 182 ms; vector DB scan
  7 → 7 ms. No speed cost or benefit.

## Recommendation

This is a **per-corpus decision, not a global one.** Options, roughly in order:

1. **Split the model by corpus** — voyage-4-large for `iowa-code`, voyage-law-2
   for `iowa-court-rules`. The data supports it cleanly, and the model is already
   env-driven; this would require per-source model selection (small change to
   `vector_search` / the embed job to pick a model per Source).
2. **Keep voyage-law-2 for now** if a single global model is required: the
   primary top-5 metric is flat-to-down overall (Rules −5 pts, Code +1.7 pts),
   and the Rules regression plus new Code blind spots outweigh the deep-rank gains
   for a single-model deploy.
3. **Re-measure with the reranker on.** This baseline is pre-`rerank-2`. The
   Voyage cross-encoder may recover the procedural-lookup losses (it re-scores the
   top-K, and most regressed gold is still retrievable, just ranked low) — worth a
   dedicated run before deciding.
4. **Grow the eval set first.** n = 59 / 56 and several class cells are n ≤ 5
   (`citation_lookup` swung on 2 queries). The direction is clear but the
   magnitude on small classes is noisy; more queries would firm up the per-corpus
   call.

## Current state of the dev environment

Dev is **now running voyage-4-large** end-to-end: `.env` has
`VOYAGE_EMBED_MODEL=voyage-4-large`, and `iowa-code` + `iowa-court-rules` are
100% re-embedded with it (verified by a cosine self-check = 1.0000). Production is
**unaffected** — the code default is still `voyage-law-2`, and prod's stored
vectors are unchanged. To revert dev: remove the `.env` line (or set it back) and
re-run `embed_corpus --source iowa-code --source iowa-court-rules --force`.

## Reranking (`rerank-2.5`) changes the picture

The numbers above are **pre-rerank**. Production retrieves a pool of 20 (hybrid)
and reorders it with a Voyage cross-encoder, keeping the top 6
(`chat._enriched_search`, `CHAT_CANDIDATE_POOL=20`). Re-measuring on the **same
voyage-4-large embeddings** with `benchmark_embeddings --rerank` (model
`rerank-2.5`, env-driven via `VOYAGE_RERANK_MODEL`, pool=20):

> **Determinism note.** voyage-4-large query embeddings are byte-identical across
> API calls; the only run-to-run variance is the **approximate HNSW index**
> reshuffling ranks 6+ (top-5 is stable). So `hit@1/3/5` are solid, while `hit@10`
> / MRR / `unrecovered` carry ~1–2 pts of tail noise. **All rerank deltas below
> are within a single run** (same query vectors and candidate pools), so they are
> free of that noise.

### All five configs, voyage-4-large (n = 59 Code / 56 Rules)

| Corpus | config | MRR | hit@1 | hit@5 | hit@10 | nDCG@10 |
|---|---|--:|--:|--:|--:|--:|
| Code | vector | 0.818 | 0.729 | 0.932 | 0.966 | 0.840 |
| Code | hybrid | 0.728 | 0.644 | 0.848 | 0.915 | 0.765 |
| Code | vector + rerank | 0.849 | 0.780 | 0.949 | 0.966 | 0.874 |
| Code | **hybrid + rerank** | **0.830** | 0.763 | **0.932** | 0.949 | 0.848 |
| Rules | vector | 0.800 | 0.714 | 0.875 | 0.929 | 0.813 |
| Rules | hybrid | 0.651 | 0.536 | 0.804 | 0.929 | 0.697 |
| Rules | vector + rerank | 0.868 | 0.821 | 0.946 | 0.946 | 0.866 |
| Rules | **hybrid + rerank** | **0.903** | **0.857** | **0.982** | **0.982** | **0.900** |

### What reranking does

1. **It lifts every config, most dramatically `hybrid`** — the cross-encoder
   discards the trigram noise that RRF had unioned in. `hybrid+rerank` MRR jumps
   +0.10 (Code) / **+0.25 (Rules)**; hit@1 +0.12 / **+0.32**. `hybrid+rerank` is
   the **best config overall**: hit@5 **0.932 (Code) / 0.982 (Rules)**.
2. **It recovers most of voyage-4-large's regressions** — not by fixing the
   embedder, but because the *lexical* retrievers (FTS/trigram) pull the
   vector-missed gold into the top-20 pool and `rerank-2.5` then promotes it:

   | Query | Gold | vector | vector+rr | **hybrid+rr** |
   |---|---|--:|--:|--:|
   | "deadline to file a motion to enlarge / amend findings" | `1.904` | — | — | **1** |
   | "commence and certify a class action" | `1.261/1.262` | — | — | **1** |
   | "how many CLE hours must a lawyer…" | (cle) | 8 | 2 | **2** |
   | "place of confinement for felons" | `902.5` | 8 | 2 | **2** |
   | "what is a CINA proceeding…" *(definition)* | `8.11` | — | **1** | **1** |

3. **Residual blind spots remain** — gold in *neither* the vector top-100 *nor*
   the lexical pool, so nothing can rerank it into view. The remaining
   `hybrid+rerank` misses@5: `232.2` (juvenile "child"), `1.981` (summary
   judgment), `614.1` (limitations), `85.27` (workers' comp medical), and
   `562A.27` (eviction, lands at rank 6). These are the true remaining risk and
   the best targets for query expansion or an eval-set/ingest fix.

4. **Cost:** one rerank call (~240 ms p50 for a pool of 20) per query, on top of
   the embed round-trip. Production already pays this once per chat turn.

### The full 2×2 — voyage-law-2 + rerank-2.5 measured against prod

The clean head-to-head was run by pointing the harness at the **production
database** (which still holds voyage-law-2 vectors; read-only, query embedder
matched to law-2) — no re-embed needed. FTS scores were byte-identical to the
dev runs, confirming the corpus text is the same in both DBs, so the cross-model
comparison is valid. (Latency in that run is network-inflated — remote DB — and
not comparable; quality metrics are.)

**hit@5 / MRR, each model measured within its own run:**

| config | voyage-law-2 | voyage-4-large |
|---|---|---|
| **iowa-code** | | |
| vector | 0.898 / 0.750 | 0.932 / 0.818 |
| vector + rerank | 0.915 / 0.834 | **0.949 / 0.849** |
| hybrid + rerank *(production)* | **0.983 / 0.867** | 0.932 / 0.830 |
| **iowa-court-rules** | | |
| vector | **0.929 / 0.838** | 0.875 / 0.800 |
| vector + rerank | **0.982 / 0.917** | 0.946 / 0.868 |
| hybrid + rerank *(production)* | 0.982 / **0.918** | 0.982 / 0.903 |

### Bottom line — the upgrade does **not** pay off under the production stack

On the path the product actually runs (`hybrid + rerank-2.5`), **voyage-law-2
wins Code (0.983 vs 0.932 hit@5) and ties Rules (0.982 / 0.982, law-2 slightly
higher MRR).** The reranker erases voyage-4-large's apparent vector-level
advantage:

- 4-large's headline wins (the unrecoverable IPERS/theft cases) get recovered for
  **law-2 too** — FTS/trigram pull them into the top-20 pool and rerank promotes
  them. law-2's only Code miss@5 is `562A.27` (which 4-large also misses).
- 4-large's **new** blind spots survive even hybrid+rerank: it misses `232.2`
  (juvenile "child"), `614.1` (limitations), `85.27` (workers'-comp) — all of
  which law-2 gets. So 4-large is **−3 net** on Code with no Rules gain.
- The Code gap (3 queries / 5 pts) is above the ~1–2 pt HNSW tail noise and is
  tied to those specific named provisions, not run variance.

**Recommendation: keep `voyage-law-2`. The win here is the *reranker*, not the
embedder.** Concretely:

1. **Do not adopt voyage-4-large** — it costs Code recall (−5 pts hit@5 even with
   rerank) for no Rules benefit. Revert dev to voyage-law-2.
2. **Bump the reranker `rerank-2` → `rerank-2.5` in prod** (`VOYAGE_RERANK_MODEL`)
   — it's the biggest lever measured and is safe to flip with no re-embed (live,
   stateless). *Caveat:* this study measured rerank-2.5 only; the isolated
   rerank-2 → rerank-2.5 delta was not separately benchmarked.
3. **Residual blind spots are corpus/eval issues, not embedder ones:** `232.2`,
   `614.1`, `85.27`, `1.981`, `8.11` are missed under multiple configs — candidates
   for query expansion, an ingest check, or eval-set review.
4. The pre-rerank **trigram drag** finding still holds, but rerank masks it in the
   production path, lowering its priority.

## Reproduce

```bash
cd backend
# pre-rerank
python manage.py benchmark_embeddings --out benchmarks/embeddings/candidate_voyage-4-large.json
# with production reranker (rerank-2.5, pool=20)
python manage.py benchmark_embeddings --rerank --out benchmarks/embeddings/candidate_voyage-4-large_rerank-2.5.json
# diff results.<source>.{vector,hybrid,vector_rr,hybrid_rr} {mrr, hit, ndcg}
```
