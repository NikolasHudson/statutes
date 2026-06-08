# PR2 eval A/B — decision-cluster dedup + chunk-aware excerpts (+ MMR/U-order)

Real-corpus, gpt-4o judge, `caselaw_eval_queries_categories2.json` (n=20), 2026-06-08,
commit `5ca5243` working tree. Each run also recomputes the base configs; the row
below is the **judged** config.

| file | config | MRR | hit@1 | hit@5 | hit@10 | ans_yes | yes+partial | controlling | tgt_shown | dist@5 |
|---|---|---|---|---|---|---|---|---|---|---|
| `baseline_hybrid_rr.json` | current prod (`hybrid_rr`) | 0.751 | 0.70 | 0.80 | 0.85 | 0.75 | 0.90 | 0.75 | 0.80 | 5.00 |
| `rc_no_mmr.json` | **PR2 ship config** (dedup+chunk+U-order+cite, **MMR off**) | **0.790** | 0.75 | 0.85 | **0.90** | 0.70 | 0.95 | **0.80** | **0.85** | 5.00 |
| `rc_full.json` | rc + MMR on (old default) | 0.750 | 0.75 | 0.75 | 0.75 | 0.75 | 1.00 | 0.75 | 0.75 | 5.00 |
| `rc_no_chunk.json` | rc, MMR on, **chunk-excerpt off** | 0.750 | 0.75 | 0.75 | 0.75 | 0.75 | 0.90 | 0.75 | 0.75 | 5.00 |
| `rc_no_dedup.json` | rc, MMR on, **dedup off** | 0.750 | 0.75 | 0.75 | 0.75 | 0.75 | 1.00 | 0.75 | 0.75 | **4.65** |

## Read

- **Ship config (`rc_no_mmr`) vs baseline**: directionally better on 7/8 metrics; within
  the n=20 Wilson noise floor, so "no regression + consistent lift", not "proven win".
- **Chunk-excerpt** (`rc_full` vs `rc_no_chunk`, MMR held on): yes+partial 1.00 vs 0.90 —
  the matched holding-chunk lets the model partially answer cases the opinion-head prefix
  could not. **Kept.**
- **Dedup** (`rc_full` vs `rc_no_dedup`): distinct-clusters@5 5.0 vs 4.65 — collapses a
  case's duplicate opinions out of the display, no answer-quality cost. **Kept.**
- **MMR** (`rc_full` vs `rc_no_mmr`): MMR **hurts** — hit@10 0.75 vs 0.90, target-shown
  0.75 vs 0.85. Diversity demotes the on-point case, which is wrong for pinpoint legal
  retrieval. **Reverted to default-off** (code + `mmr_lambda` param kept for
  diversity-oriented surfaces).
- **U-order**: not isolable here — it is set-preserving (same cases shown, only reordered)
  and the judge reads all k cases with explicit ranks. Ships on per design; revisit if a
  UI surfaces passages in list order.

## Reproduce

```
python manage.py eval_caselaw --rerank --judge --judge-config hybrid_rr \
  --queries apps/corpus/data/caselaw_eval_queries_categories2.json --judge-k 5   # baseline
python manage.py eval_caselaw --use-retrieve-context --judge --judge-config rc \
  --queries apps/corpus/data/caselaw_eval_queries_categories2.json --judge-k 5   # PR2 ship
# add --rc-mmr / --rc-no-dedup / --rc-no-chunk-excerpt / --rc-no-u-order to isolate.
```
