# Semantic Search Baseline — `voyage-law-2`

**Purpose:** pin a reproducible "before" measurement of semantic-search quality so we
can quantify the gain when we swap the embedding model. Scoped to the only two
corpora that carry embeddings: **Iowa Code** and **Iowa Court Rules**. (Iowa
Caselaw has 0 embeddings and is excluded.)

| | |
|---|---|
| Embedder under test | **`voyage-law-2`** (1024-dim) |
| Distance / index | cosine (`pgvector <=>`), HNSW `vector_cosine_ops` |
| Git commit | `d36d718` |
| Generated | 2026-06-05 (UTC) |
| Query expansion | **off** (`ANTHROPIC_API_KEY` unset → `NoopExpander`) |
| Reranker | **off** (core `hybrid_search`, measured pre-rerank) |
| Snapshot | [`baseline_voyage-law-2.json`](./baseline_voyage-law-2.json) |
| Harness | `python manage.py benchmark_embeddings` |

> **Update (2026-06-05):** an upgrade to `voyage-4-large` was measured against this
> baseline — see [**comparison_voyage-law-2_vs_voyage-4-large.md**](./comparison_voyage-law-2_vs_voyage-4-large.md).
> Result is **mixed**: it improves Iowa Code (vector MRR +0.06, fixes the hard
> unrecoverables) but **regresses Iowa Court Rules** (vector MRR −0.04, hit@5 −0.05).
> Dev is currently running voyage-4-large; prod is unaffected.

## TL;DR

- **The vector retriever is the workhorse.** On natural-language / substantive
  queries — the bulk of real attorney traffic — pure semantic search hits the
  right provision in the top-5 **~90% (Code) / ~93% (Rules)** of the time, with
  MRR **0.73 / 0.84**. Lexical FTS alone gets **0.00–0.20** hit@5 on those same
  queries: it is essentially blind to paraphrase.
- **Production `hybrid` currently *underperforms* pure vector** on substantive
  and scenario queries (Rules hit@5 **0.80 hybrid vs 0.93 vector**). The drag is
  the **trigram** retriever fuzzy-matching unrelated headings against long
  queries. Verified: disabling trigram recovers most of the gap
  (0.841 → 0.932 on Rules substantive). This is an *embedder-independent* finding
  and an immediate, free quality win.
- **Headroom the upgrade should target is concrete and small.** Only **4 of 115**
  gold provisions are unrecoverable (not in the vector top-100); they are
  vocabulary-mismatch cases (IPERS jargon, "theft" definition, "CINA"). Another
  ~7 are "near-misses" ranked 7–23 — a stronger embedder should lift these into
  the top-5. Median rank of a missed-at-5 provision is **17 (Code) / 9 (Rules)**.

---

## 1. What is being measured, and why this isn't `eval_search`

We are about to change the embedding model. The existing `eval_search` command
reports only the **fused hybrid** ranking. Hybrid hides the embedder's
contribution: FTS already nails keyword queries, so even a dramatically better
embedder can barely move hybrid hit@5. To see *what the embedder actually buys
us*, we measure the **vector retriever in isolation** and bracket it with two
references:

| Config | What it is | Role in this benchmark |
|---|---|---|
| `fts` | Postgres `tsvector` (`ts_rank_cd`) only | **Lexical control** — embedder-independent floor |
| `vector` | pgvector cosine only | **The thing the embedder changes** — primary signal |
| `hybrid` | FTS + trigram + vector, RRF-fused | **Production core path** (pre-rerank) |

All three run the *production* retriever functions in
`apps/corpus/services/search.py` — nothing is reimplemented for the benchmark.
The query embedding is computed once per query (timed separately) and reused
across configs via a zero-cost cached client, so the same vector drives `vector`
and `hybrid` and we never pay for an embedding twice.

---

## 2. Corpus & embedding coverage

| Source | Nodes | Current+approved | Embedded | Coverage | Body chars (p50 / p90 / max) | Empty bodies |
|---|--:|--:|--:|--:|--:|--:|
| `iowa-code` | 29,739 | 27,869 | 27,869 | **100%** | 671 / 3,350 / 129,620 | 1,533 |
| `iowa-court-rules` | 1,263 | 1,193 | 1,193 | **100%** | 786 / 4,366 / 30,415 | 8 |
| `iowa-caselaw` | 159,209 | 111,323 | **0** | 0% | — | — |

Embeddings are **section-level** (one vector per current, approved `NodeVersion`,
over `heading + "\n\n" + body_text`). Coverage is complete for both embedded
corpora, so retrieval quality is not confounded by missing vectors.

**Two corpus caveats that affect the baseline and the upgrade equally:**
- **1,533 Code sections (5.5%) have empty bodies** (heading-only container/reserved
  nodes). They are embedded from the heading alone — thin signal, but they are
  rarely the gold answer.
- **The longest sections exceed the model's context** (`voyage-law-2` ≈ 16k
  tokens; the 129,620-char Code section is ~30k+ tokens) and were **truncated at
  embedding time**. A new model with a longer context could change recall on
  these long provisions independently of raw embedding quality.

---

## 3. Methodology

**Query sets** (committed, reused as-is; `out_of_scope` entries with empty
`expected_paths` are excluded from scoring):

| Source | File | Scoreable / total |
|---|---|--:|
| `iowa-code` | `apps/corpus/data/search_eval_queries.json` | 30 / 30 |
| `iowa-code` | `apps/api/data/chat_eval_iowa_code_1.json` | 29 / 32 |
| `iowa-court-rules` | `apps/api/data/chat_eval_court_rules.json` | 25 / 27 |
| `iowa-court-rules` | `apps/api/data/chat_eval_court_rules_2.json` | 31 / 34 |
| | **Total** | **59 Code + 56 Rules = 115** |

**Metrics.** Each query/config produces one deep ranked list (`--deep 100`
candidates) from which all cutoff metrics are computed:

- **hit@k** — 1 if any gold provision is in the top-k (a.k.a. success@k).
- **recall@k** — fraction of gold provisions found in top-k (matters for the
  multi-gold queries).
- **precision@k** — gold in top-k ÷ k.
- **nDCG@k** — binary-relevance, discounts by rank position.
- **MRR** — mean of 1/(rank of first gold), over the deep list.

**Relevance is binary and human-judged**: `expected_paths` are the provision(s)
an attorney would expect to see; *any* of them counts as a hit. This is the right
gate for grounding a chat answer but understates precision (other genuinely-
relevant sections aren't labeled) — see §7.

---

## 4. Headline results

### Iowa Code (n = 59)

| Config | MRR | hit@1 | hit@3 | hit@5 | hit@10 | nDCG@5 | nDCG@10 | recall@5 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `fts` | 0.257 | 0.237 | 0.271 | 0.271 | 0.288 | 0.257 | 0.262 | 0.271 |
| **`vector`** | **0.733** | **0.627** | **0.831** | **0.898** | 0.898 | **0.768** | 0.768 | **0.890** |
| `hybrid` | 0.709 | 0.593 | 0.797 | 0.864 | **0.932** | 0.736 | 0.754 | 0.856 |

### Iowa Court Rules (n = 56)

| Config | MRR | hit@1 | hit@3 | hit@5 | hit@10 | nDCG@5 | nDCG@10 | recall@5 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `fts` | 0.144 | 0.125 | 0.161 | 0.179 | 0.179 | 0.143 | 0.143 | 0.167 |
| **`vector`** | **0.838** | **0.768** | **0.875** | **0.929** | **0.982** | **0.823** | **0.845** | **0.890** |
| `hybrid` | 0.696 | 0.589 | 0.804 | 0.804 | 0.857 | 0.685 | 0.704 | 0.768 |

**Read this as:** semantic search alone is strong; FTS alone is weak on this
(NL-heavy) query mix; and fusion as currently configured *costs* quality versus
pure vector on these queries. The one place hybrid wins is **hit@10 on Code**
(0.932) — fusion drags a few extra correct provisions into the 5–10 band that
vector ranked just below its own top-10.

---

## 5. Where the embedder matters: by query class

hit@5 per config (n in parens). This is the most useful slice for an embedder
swap — it shows the *kind* of query the model has to get right.

### Iowa Code

| Class | n | `fts` | `vector` | `hybrid` | vector MRR |
|---|--:|--:|--:|--:|--:|
| search_substantive (NL) | 29 | **0.00** | 0.93 | 0.83 | 0.76 |
| keyword | 18 | 0.67 | 0.94 | 0.94 | 0.79 |
| paraphrase | 9 | 0.33 | 0.78 | **0.89** | 0.62 |
| natural-language | 3 | 0.33 | 0.67 | 0.67 | 0.44 |

### Iowa Court Rules

| Class | n | `fts` | `vector` | `hybrid` | vector MRR |
|---|--:|--:|--:|--:|--:|
| search_substantive | 44 | 0.20 | **0.95** | 0.82 | 0.85 |
| scenario | 5 | 0.00 | 0.80 | 0.60 | 0.72 |
| citation_lookup | 2 | 0.50 | 1.00 | 1.00 | 1.00 |
| multi_issue | 2 | 0.00 | 1.00 | 1.00 | 1.00 |
| comparison | 1 | 0.00 | 1.00 | 1.00 | 1.00 |
| quote_verification | 1 | 0.00 | 1.00 | 1.00 | 1.00 |
| definition | 1 | 0.00 | **0.00** | 0.00 | 0.00 |

Takeaways:
- **FTS is blind to natural language** (0.00 on substantive queries) — whole-
  question `websearch_to_tsquery` ANDs every content word, so a paraphrased
  question matches nothing. This is *exactly* the gap semantic search fills.
- **Vector is robust across every query shape**, including scenario ("facts →
  which rule") and multi-issue questions where lexical retrieval has no chance.
- **Paraphrase (Code) is the one class where fusion helps** (0.78 → 0.89): when
  both signals are partially right, RRF combines them well.

---

## 6. Backend analytics

### 6.1 Cosine-similarity distribution

The similarity the embedder assigns to its top hit, and to the best-ranked gold
provision. (Higher / better-separated is better; this is a key thing the new
model should move.)

| Source | top-1 sim (p50 / p90 / min) | best-gold sim (p50 / p90 / min) |
|---|--:|--:|
| `iowa-code` | 0.577 / 0.666 / 0.320 | 0.568 / 0.661 / 0.378 |
| `iowa-court-rules` | 0.591 / 0.681 / 0.421 | 0.580 / 0.667 / 0.391 |

Absolute cosine values for `voyage-law-2` sit in a fairly **compressed 0.32–0.76
band** — the model rarely expresses high confidence even when correct, so raw
similarity is a weak abstention/cutoff signal today. Watch whether the new model
widens this band and separates gold from non-gold more cleanly.

### 6.2 Miss diagnostics (vector retriever)

| Source | recovered (gold in top-100) | unrecovered | miss@5 | median rank of a miss |
|---|--:|--:|--:|--:|
| `iowa-code` | 95% (56/59) | 3 | 6 | **17** |
| `iowa-court-rules` | 98% (55/56) | 1 | 4 | **9** |

The **4 unrecoverable** gold provisions (not even in top-100) are the hardest
test for the new model — all are vocabulary-mismatch:

| Source | Query | Gold | top-1 sim |
|---|---|---|--:|
| code | "investment standards for retirement fund" | `97B.7A` | 0.320 |
| code | "early retirement date IPERS" | `97B.47` | 0.346 |
| code | "How does Iowa law define theft?" | `714.1` | 0.416 |
| rules | "What is a CINA proceeding in Iowa juvenile court…" | `8.11` | 0.488 |

The **recoverable near-misses** (ranked just outside top-5) are the cheapest wins
for a better embedder:

| Source | Query | Gold | vector rank |
|---|---|---|--:|
| code | "what is sexual abuse under iowa law" | `709.1` | 17 |
| code | "rules referring to other statutes" | `4.3` | 23 |
| code | "tenant is two weeks behind on rent…" | `562A.27` | 11 |
| rules | "scope of permissible discovery in an Iowa civil…" | `1.503` | 9 |
| rules | "admit business records into evidence" | `5.803` | 7 |
| rules | "district court judge previously practiced at the firm…" | `51:2.11` | 9 |

### 6.3 Latency

| Stage | p50 | p90 | max | Notes |
|---|--:|--:|--:|---|
| **query embed** (Voyage API) | 175 ms | 195 ms | 437 ms | network round-trip; **dominates**; *changes with the model* |
| **vector_search** (DB) | 7 ms | 11 ms | 13 ms | HNSW scan over 1024-dim; changes with dim |
| `fts` (DB) | 9 ms | 40 ms | 431 ms | embedder-independent |
| `hybrid` (DB+fusion) | 475 ms | 1073 ms | 1461 ms | **measured at deep=100** — see caveat |

- **The embed round-trip (~175 ms) is the dominant latency** and the part that
  moves with the model. A larger/slower embedding model raises every query's
  floor; a faster/cheaper one is itself a win. Vector DB scan is negligible
  (~7 ms) but scales with dimensionality, so a model with a different output dim
  changes this line too.
- `hybrid` latency here is an **upper bound**: the benchmark fuses `deep=100`
  candidates per retriever, vs production defaults of `per_retriever=50`,
  `limit=20`. Don't read the 475 ms as the production figure.

---

## 7. Notable findings & recommendations

1. **Semantic search is carrying the product.** FTS alone is unusable on the
   natural-language queries that dominate real usage (hit@5 0.00–0.20). The
   embedder swap is the highest-leverage retrieval change available.

2. **Trigram is hurting production hybrid — fix independently of the swap.** On
   Rules substantive queries (n=44): `hybrid` 0.841 → **0.932 with trigram off**
   → 0.955 pure vector. Trigram's heading fuzzy-match unions unrelated rules into
   RRF on multi-word queries (the `hybrid_search` docstring even warns about
   this). Recommendation: gate trigram off for multi-token / natural-language
   queries, or down-weight it in fusion. This is a free, embedder-independent
   quality gain and should be done *before* the swap so the comparison isn't
   muddied.

3. **Re-evaluate the value of FTS in fusion for this traffic.** Given how weak
   lexical is on NL queries, the current equal-weight RRF leaves vector quality
   on the table. Consider weighting RRF by retriever, or routing keyword-shaped
   queries to FTS and NL queries to vector. (The reranker, currently off in this
   baseline, may also recover the gap — worth measuring separately.)

4. **The upgrade's job is narrow and measurable:** recover the 4 vocabulary-
   mismatch unrecoverables, promote the ~7 near-misses (rank 7–23) into the
   top-5, and widen the cosine-similarity separation. The single `definition`
   miss (`8.11`, "CINA") is a good canary.

---

## 8. Limitations

- **Sample size is modest** (59 Code / 56 Rules). Per-class cells with n ≤ 3
  (natural-language, scenario, definition, comparison) are directional, not
  statistically firm.
- **Binary, sparse gold.** Most queries have one expected path; *any* hit counts.
  This is the correct gate for chat grounding but **understates precision** (a
  retrieved sibling section may be equally valid yet scored as a miss) and caps
  recall. Treat absolute precision@k as a lower bound.
- **Query mix leans natural-language** (the chat-eval files are conversational
  questions). This is representative of assistant traffic but flatters vector vs
  FTS relative to a hypothetical keyword-search UI.
- **No query expansion, no reranker** in this baseline (both are off in this env).
  The production stack with the Voyage `rerank-2` reranker enabled will score
  differently; this baseline measures the *core retrieval* layer only.
- **`voyage-law-2` query embeddings are non-deterministic enough** that hit@k can
  jiggle by a query or two between runs; trends, not single-query flips, are
  what to trust.

---

## 9. Reproduce & compare after the swap

The harness writes an embedder-stamped JSON snapshot, so a post-upgrade run diffs
cleanly against this one.

```bash
cd backend

# Re-run the baseline (current embedder)
python manage.py benchmark_embeddings

# After swapping the embedder, re-embed ONLY the two embedded corpora — a plain
# `embed_corpus --force` would also start embedding ~110k caselaw versions.
python manage.py embed_corpus --source iowa-code --source iowa-court-rules --force

# Then re-run the benchmark to a new, embedder-stamped file:
python manage.py benchmark_embeddings --out benchmarks/embeddings/candidate_<model>.json
```

To compare, diff the `results.<source>.<config>` blocks of the two JSON files —
the headline numbers to watch are **`vector` hit@5 / MRR / nDCG@10** per source,
the **`vector_analytics.unrecovered` count**, the **`miss_first_relevant_rank`**
distribution, and **`best_relevant_sim`** (should rise and separate from
`top1_sim` on misses). The per-query array lets you confirm the specific
unrecoverables in §6.2 were fixed.

> **Important:** before declaring an improvement, re-embed with the new model
> (scoped `embed_corpus --source … --force` as above) and confirm `corpus.*.coverage`
> is back to 100% in the new snapshot — a partial re-embed will silently tank
> vector recall and look like a model regression.
