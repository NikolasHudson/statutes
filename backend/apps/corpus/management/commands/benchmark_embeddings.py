"""Embedder-upgrade baseline benchmark for semantic search.

Why this exists (and why it is not just ``eval_search``): we are about to swap
the embedding model. ``eval_search`` reports only the *fused* hybrid ranking,
which hides the embedder's contribution — FTS already nails keyword queries, so
a much better embedder can barely move hybrid hit@5. To see "what improvements
we get" we have to measure the **vector retriever in isolation** and compare it
against a lexical control (FTS-only) and the production fusion (hybrid).

This command therefore runs every eval query through three configurations:

    vector  — pgvector cosine only  (the thing the embedder changes)
    fts      — Postgres tsvector only (embedder-independent control)
    hybrid   — FTS + trigram + vector, RRF-fused (production core path)

and reports, per source and per query-class:

    hit@k, recall@k, precision@k, nDCG@k  (k = 1,3,5,10)  + MRR

plus backend analytics the swap should move:

    - cosine-similarity distributions (top-1 and best-relevant)
    - miss diagnostics: when the right doc is NOT in vector top-5, how far down
      is it (rank), and what fraction is unrecoverable (not in top-`deep`)
    - latency split: query-embed round-trip vs vector DB scan vs fts vs hybrid

Output is a human summary plus a machine-readable JSON snapshot stamped with the
embedder identity + git commit, so the post-upgrade run diffs cleanly against
this baseline.

    python manage.py benchmark_embeddings
    python manage.py benchmark_embeddings --out benchmarks/embeddings/baseline.json
    python manage.py benchmark_embeddings --deep 100 --k 1,3,5,10
    python manage.py benchmark_embeddings --limit-queries 5        # smoke test

The default eval set is the union of the committed query files for the two
embedded corpora (iowa-code, iowa-court-rules). Caselaw has no embeddings and is
excluded automatically.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.corpus.models import Node, NodeVersion, Source
from apps.corpus.services.search import fts_search, hybrid_search, vector_search
from apps.corpus.services.rerank import NoopReranker, default_reranker
from apps.corpus.services.voyage import (
    EMBEDDING_DIM,
    INPUT_TYPE_QUERY,
    FakeEmbeddingClient,
    default_client,
)


# (source_slug, query_file) pairs that make up the default benchmark. Every file
# uses the {query|question, expected_paths, tags|kind} shape eval_search already
# understands. Only the two embedded corpora are listed.
DEFAULT_SPECS = [
    ("iowa-code", "apps/corpus/data/search_eval_queries.json"),
    ("iowa-code", "apps/api/data/chat_eval_iowa_code_1.json"),
    ("iowa-court-rules", "apps/api/data/chat_eval_court_rules.json"),
    ("iowa-court-rules", "apps/api/data/chat_eval_court_rules_2.json"),
]

DEFAULT_OUT = "benchmarks/embeddings/baseline_voyage-law-2.json"


class _CachedClient:
    """An EmbeddingClient that returns a pre-computed query vector with zero
    network cost. Lets us drive the *real* production retrievers
    (``vector_search`` / ``hybrid_search``) while timing the embed round-trip
    separately and never paying for the same embedding twice."""

    def __init__(self, model: str, vector: list[float]):
        self.model = model
        self._vector = vector

    def embed_texts(self, texts, *, input_type=INPUT_TYPE_QUERY):
        return [self._vector for _ in texts]


def _pctile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in [0,1]). Empty -> 0.0."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, math.ceil(q * len(s)) - 1))
    return s[idx]


def _dist(values: list[float]) -> dict:
    """Summary stats for a list of numbers."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "min": round(min(vals), 4),
        "p25": round(_pctile(vals, 0.25), 4),
        "p50": round(median(vals), 4),
        "mean": round(mean(vals), 4),
        "p75": round(_pctile(vals, 0.75), 4),
        "p90": round(_pctile(vals, 0.90), 4),
        "max": round(max(vals), 4),
    }


def _ranks_of(ranked_paths: list[str], relevant: set[str]) -> list[int]:
    """1-based ranks at which a relevant path appears in the ranked list."""
    return [i for i, p in enumerate(ranked_paths, start=1) if p in relevant]


def _ndcg_at_k(ranked_paths: list[str], relevant: set[str], k: int) -> float:
    """Binary-relevance nDCG@k."""
    dcg = 0.0
    for i, p in enumerate(ranked_paths[:k], start=1):
        if p in relevant:
            dcg += 1.0 / math.log2(i + 1)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def _query_metrics(ranked_paths: list[str], relevant: set[str], ks: list[int]) -> dict:
    """All ranking metrics for one query/config from a single deep ranked list."""
    ranks = _ranks_of(ranked_paths, relevant)
    first_rank = min(ranks) if ranks else None
    out = {
        "first_relevant_rank": first_rank,
        "reciprocal_rank": (1.0 / first_rank) if first_rank else 0.0,
        "hit": {}, "recall": {}, "precision": {}, "ndcg": {},
    }
    for k in ks:
        in_topk = [r for r in ranks if r <= k]
        out["hit"][str(k)] = 1.0 if in_topk else 0.0
        out["recall"][str(k)] = len(in_topk) / len(relevant) if relevant else 0.0
        out["precision"][str(k)] = len(in_topk) / k
        out["ndcg"][str(k)] = _ndcg_at_k(ranked_paths, relevant, k)
    return out


def _git_commit() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], cwd=settings.BASE_DIR
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


class Command(BaseCommand):
    help = "Baseline benchmark for semantic search ahead of an embedder swap."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=DEFAULT_OUT, help="JSON snapshot path.")
        parser.add_argument(
            "--deep", type=int, default=100,
            help="Candidate depth per retriever for rank-based metrics (MRR, miss rank).",
        )
        parser.add_argument("--k", default="1,3,5,10", help="Comma-separated cutoffs.")
        parser.add_argument(
            "--limit-queries", type=int, default=None,
            help="Cap queries per file (smoke test).",
        )
        parser.add_argument(
            "--allow-fake", action="store_true",
            help="Permit the deterministic fake embedder (benchmark is meaningless; smoke only).",
        )
        parser.add_argument(
            "--rerank", action="store_true",
            help="Also measure rerank configs: vector+rr and hybrid+rr (Voyage cross-encoder).",
        )
        parser.add_argument(
            "--rerank-pool", type=int, default=20,
            help="Candidate pool size handed to the reranker (production CHAT_CANDIDATE_POOL=20).",
        )

    def handle(self, *args, **opts):
        client = default_client()
        if isinstance(client, FakeEmbeddingClient) and not opts["allow_fake"]:
            raise CommandError(
                "default_client() is the FAKE embedder (VOYAGE_API_KEY unset). "
                "Benchmarking fake vectors is meaningless — set the key, or pass "
                "--allow-fake for a wiring smoke test."
            )

        ks = sorted({int(x) for x in opts["k"].split(",") if x.strip()})
        deep = opts["deep"]
        if max(ks) > deep:
            raise CommandError(f"--deep ({deep}) must be >= max --k ({max(ks)}).")

        rerank_on = opts["rerank"]
        rerank_pool = opts["rerank_pool"]
        reranker = default_reranker() if rerank_on else None
        if rerank_on and isinstance(reranker, NoopReranker):
            raise CommandError(
                "default_reranker() is the NOOP reranker (VOYAGE_API_KEY unset). "
                "Reranking would be a no-op truncation — set the key."
            )
        if rerank_on and max(ks) > rerank_pool:
            raise CommandError(
                f"--rerank-pool ({rerank_pool}) must be >= max --k ({max(ks)}); "
                "the reranker only reorders within the pool."
            )
        # Config order = report order. Reranked configs only when --rerank.
        configs = ["fts", "vector", "hybrid"]
        if rerank_on:
            configs += ["vector_rr", "hybrid_rr"]

        # Resolve specs -> only embedded sources that exist + queries that load.
        loaded_paths: dict[str, set[str]] = {}
        nv_to_path: dict[str, dict[int, str]] = {}
        nv_to_text: dict[str, dict[int, str]] = {}  # heading\nbody, only when reranking
        specs = []
        for slug, rel in DEFAULT_SPECS:
            if not Source.objects.filter(slug=slug).exists():
                continue
            qfile = Path(settings.BASE_DIR) / rel
            if not qfile.exists():
                self.stderr.write(self.style.WARNING(f"skip missing query file: {rel}"))
                continue
            if slug not in loaded_paths:
                loaded_paths[slug] = set(
                    Node.objects.filter(source__slug=slug).values_list("path", flat=True)
                )
                nv_to_path[slug] = dict(
                    NodeVersion.objects.filter(
                        node__source__slug=slug,
                        effective_to__isnull=True,
                        review_status="approved",
                    ).values_list("id", "node__path")
                )
                if rerank_on:
                    # Match production: rerank on "heading\nbody" (see chat._enriched_search).
                    nv_to_text[slug] = {
                        i: f"{h or ''}\n{b or ''}"
                        for i, h, b in NodeVersion.objects.filter(
                            node__source__slug=slug,
                            effective_to__isnull=True,
                            review_status="approved",
                        ).values_list("id", "node__heading", "body_text")
                    }
            specs.append((slug, rel, qfile))

        if not specs:
            raise CommandError("No embedded sources with query files found.")

        # Warm up the embedding endpoint (first call pays TLS/cold-start).
        self.stdout.write("Warming up embedder ...")
        client.embed_texts(["warmup"], input_type=INPUT_TYPE_QUERY)

        per_query: list[dict] = []
        latency = {"embed": [], "vector_search": [], "fts": [], "hybrid": []}
        if rerank_on:
            latency["rerank"] = []
        query_sets = []

        for slug, rel, qfile in specs:
            payload = json.loads(qfile.read_text())
            entries = payload.get("queries", [])
            if opts["limit_queries"]:
                entries = entries[: opts["limit_queries"]]
            total = len(entries)
            oos = 0
            scoreable = 0

            for entry in entries:
                query = (entry.get("query") or entry.get("question") or "").strip()
                expected = set(entry.get("expected_paths", []))
                if not expected:
                    oos += 1
                    continue
                relevant = expected & loaded_paths[slug]
                if not query or not relevant:
                    continue
                scoreable += 1
                qclass = entry.get("kind") or (entry.get("tags") or ["untagged"])[0]

                # 1) Embed once (timed in isolation), then reuse everywhere.
                t = time.perf_counter()
                [qvec] = client.embed_texts([query], input_type=INPUT_TYPE_QUERY)
                latency["embed"].append((time.perf_counter() - t) * 1000)
                cached = _CachedClient(client.model, qvec)

                # 2) vector-only (production vector_search, zero-cost embed).
                t = time.perf_counter()
                vec_hits = vector_search(query, limit=deep, source_slug=slug, client=cached)
                latency["vector_search"].append((time.perf_counter() - t) * 1000)
                vec_paths, vec_scores = [], []
                for nv_id, score in vec_hits:
                    p = nv_to_path[slug].get(nv_id)
                    if p is not None:
                        vec_paths.append(p)
                        vec_scores.append(score)

                # 3) fts-only (lexical control).
                t = time.perf_counter()
                fts_hits = fts_search(query, limit=deep, source_slug=slug)
                latency["fts"].append((time.perf_counter() - t) * 1000)
                fts_paths = [nv_to_path[slug].get(n) for n, _ in fts_hits]
                fts_paths = [p for p in fts_paths if p is not None]

                # 4) hybrid (production fusion; cached client => embed not re-timed).
                t = time.perf_counter()
                hyb_hits = hybrid_search(
                    query, limit=deep, per_retriever=deep,
                    source_slug=slug, client=cached,
                )
                latency["hybrid"].append((time.perf_counter() - t) * 1000)
                hyb_paths = [h.path for h in hyb_hits]

                row = {
                    "source": slug,
                    "file": rel,
                    "query": query,
                    "class": qclass,
                    "relevant": sorted(relevant),
                    "n_relevant": len(relevant),
                    "vector": _query_metrics(vec_paths, relevant, ks),
                    "fts": _query_metrics(fts_paths, relevant, ks),
                    "hybrid": _query_metrics(hyb_paths, relevant, ks),
                }
                # Vector-specific signal the swap should move.
                row["vector"]["top1_sim"] = round(vec_scores[0], 4) if vec_scores else None
                br = row["vector"]["first_relevant_rank"]
                row["vector"]["best_relevant_sim"] = (
                    round(vec_scores[br - 1], 4) if br else None
                )
                row["vector"]["recovered"] = br is not None

                # 5) reranked configs: re-score the top-`rerank_pool` candidates of
                # a retriever with the Voyage cross-encoder (production: hybrid pool=20).
                if rerank_on:
                    vec_pool = [
                        (nv_id, nv_to_text[slug].get(nv_id, ""))
                        for nv_id, _ in vec_hits[:rerank_pool]
                    ]
                    t = time.perf_counter()
                    v_ranked = reranker.rerank(query, vec_pool, top_k=rerank_pool)
                    latency["rerank"].append((time.perf_counter() - t) * 1000)
                    row["vector_rr"] = _query_metrics(
                        [nv_to_path[slug].get(i) for i in v_ranked], relevant, ks
                    )
                    # hybrid pool reuses SearchHit text (heading + body already loaded).
                    hyb_pool = [
                        (h.node_version_id, f"{h.heading}\n{h.body_text}")
                        for h in hyb_hits[:rerank_pool]
                    ]
                    t = time.perf_counter()
                    h_ranked = reranker.rerank(query, hyb_pool, top_k=rerank_pool)
                    latency["rerank"].append((time.perf_counter() - t) * 1000)
                    row["hybrid_rr"] = _query_metrics(
                        [nv_to_path[slug].get(i) for i in h_ranked], relevant, ks
                    )
                per_query.append(row)

            query_sets.append(
                {"source": slug, "file": rel, "total": total,
                 "out_of_scope": oos, "scoreable": scoreable}
            )

        results = self._aggregate(per_query, ks, configs)
        corpus = self._corpus_stats(list(loaded_paths.keys()))

        snapshot = {
            "meta": {
                "kind": "semantic-search-baseline",
                "embedder": client.model,
                "embedding_dim": EMBEDDING_DIM,
                "distance": "cosine (pgvector <=>)",
                "index": "HNSW vector_cosine_ops",
                "query_expansion": "none (ANTHROPIC_API_KEY unset -> NoopExpander)",
                "reranker": (
                    f"{getattr(reranker, 'model', '?')} (pool={rerank_pool})"
                    if rerank_on else "none (pre-rerank)"
                ),
                "configs": configs,
                "deep_candidates": deep,
                "k_values": ks,
                "git_commit": _git_commit(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "corpus": corpus,
            "query_sets": query_sets,
            "results": results,
            "latency_ms": {name: _dist(vals) for name, vals in latency.items()},
            "per_query": per_query,
        }

        out_path = Path(settings.BASE_DIR) / opts["out"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2))
        self._print_report(snapshot, ks)
        self.stdout.write(self.style.SUCCESS(f"\nSnapshot written: {out_path}"))

    # ---- aggregation -----------------------------------------------------

    def _aggregate(self, per_query: list[dict], ks: list[int], configs: list[str]) -> dict:
        out: dict = {}
        sources = sorted({r["source"] for r in per_query})
        for slug in sources:
            rows = [r for r in per_query if r["source"] == slug]
            out[slug] = {"n_queries": len(rows)}
            for cfg in configs:
                out[slug][cfg] = self._agg_config(rows, cfg, ks)
            # vector analytics
            vrows = [r["vector"] for r in rows]
            misses = [v for v in vrows if v["hit"]["5"] == 0.0]
            out[slug]["vector_analytics"] = {
                "top1_sim": _dist([v.get("top1_sim") for v in vrows]),
                "best_relevant_sim": _dist([v.get("best_relevant_sim") for v in vrows]),
                "recovered_rate": round(
                    sum(1 for v in vrows if v["recovered"]) / max(len(vrows), 1), 4
                ),
                "unrecovered": sum(1 for v in vrows if not v["recovered"]),
                "miss_at_5_count": len(misses),
                "miss_first_relevant_rank": _dist(
                    [v["first_relevant_rank"] for v in misses if v["first_relevant_rank"]]
                ),
            }
            # by query-class (hit@5 / recall@5 / ndcg@5 / mrr per config)
            classes = sorted({r["class"] for r in rows})
            by_class: dict = {}
            for c in classes:
                crows = [r for r in rows if r["class"] == c]
                by_class[c] = {"n": len(crows)}
                for cfg in configs:
                    by_class[c][cfg] = {
                        "hit@5": round(mean(r[cfg]["hit"]["5"] for r in crows), 3),
                        "recall@5": round(mean(r[cfg]["recall"]["5"] for r in crows), 3),
                        "ndcg@5": round(mean(r[cfg]["ndcg"]["5"] for r in crows), 3),
                        "mrr": round(mean(r[cfg]["reciprocal_rank"] for r in crows), 3),
                    }
            out[slug]["by_class"] = by_class
        return out

    def _agg_config(self, rows: list[dict], cfg: str, ks: list[int]) -> dict:
        n = max(len(rows), 1)
        agg = {"mrr": round(sum(r[cfg]["reciprocal_rank"] for r in rows) / n, 4)}
        for metric in ("hit", "recall", "precision", "ndcg"):
            agg[metric] = {
                str(k): round(sum(r[cfg][metric][str(k)] for r in rows) / n, 4)
                for k in ks
            }
        return agg

    def _corpus_stats(self, slugs: list[str]) -> dict:
        out: dict = {}
        for slug in slugs:
            cur = NodeVersion.objects.filter(
                node__source__slug=slug, effective_to__isnull=True,
                review_status="approved",
            )
            embedded = cur.filter(embedding__isnull=False)
            lens = sorted(len(b or "") for b in embedded.values_list("body_text", flat=True))
            out[slug] = {
                "nodes": Node.objects.filter(source__slug=slug).count(),
                "current_approved": cur.count(),
                "embedded": embedded.count(),
                "coverage": round(embedded.count() / max(cur.count(), 1), 4),
                "body_chars": {
                    "p50": int(median(lens)) if lens else 0,
                    "mean": int(mean(lens)) if lens else 0,
                    "p90": int(_pctile(lens, 0.90)) if lens else 0,
                    "max": lens[-1] if lens else 0,
                    "empty": sum(1 for x in lens if x == 0),
                },
            }
        return out

    # ---- reporting -------------------------------------------------------

    def _print_report(self, snap: dict, ks: list[int]):
        m = snap["meta"]
        w = self.stdout.write
        w("\n" + "=" * 72)
        w(self.style.MIGRATE_HEADING("SEMANTIC SEARCH BASELINE"))
        w(f"  embedder : {m['embedder']}  ({m['embedding_dim']}-dim, {m['distance']})")
        w(f"  commit   : {m['git_commit']}   deep={m['deep_candidates']}")
        for qs in snap["query_sets"]:
            w(f"  set      : {qs['source']:16s} {Path(qs['file']).name:32s} "
              f"scoreable={qs['scoreable']}/{qs['total']} (oos={qs['out_of_scope']})")

        w(f"  reranker : {m['reranker']}")
        for slug, res in snap["results"].items():
            w("\n" + "-" * 72)
            w(self.style.MIGRATE_HEADING(f"{slug}  (n={res['n_queries']})"))
            header = "  config     MRR  " + "  ".join(f"hit@{k}" for k in ks) + "   " + \
                     "  ".join(f"ndcg@{k}" for k in ks)
            w(header)
            for cfg in m["configs"]:
                c = res[cfg]
                hits = "  ".join(f"{c['hit'][str(k)]:.3f}" for k in ks)
                ndcg = "  ".join(f"{c['ndcg'][str(k)]:.3f}" for k in ks)
                w(f"  {cfg:9s} {c['mrr']:.3f}  {hits}   {ndcg}")
            va = res["vector_analytics"]
            w(f"  vector top1-sim p50={va['top1_sim'].get('p50')}  "
              f"best-relevant-sim p50={va['best_relevant_sim'].get('p50')}")
            w(f"  vector recovered={va['recovered_rate']:.0%}  "
              f"unrecovered={va['unrecovered']}  miss@5={va['miss_at_5_count']}  "
              f"miss-rank p50={va['miss_first_relevant_rank'].get('p50')}")

        w("\n" + "-" * 72)
        w("latency (ms):")
        for name, d in snap["latency_ms"].items():
            if d.get("n"):
                w(f"  {name:14s} p50={d['p50']:.0f}  p90={d['p90']:.0f}  max={d['max']:.0f}")
