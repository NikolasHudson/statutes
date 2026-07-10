"""Case-level retrieval eval for the embedded caselaw corpus.

Why a separate command from ``benchmark_embeddings``/``eval_search``: those match
a retrieved ``NodeVersion`` to an ``expected_path`` by *exact node path*. Caselaw
does not work that way. A decision is a *cluster* (``cl-cluster-<id>``) whose text
lives on one or more child *opinion* nodes (``cl-cluster-<id>/op-<id>``), each
chunked and embedded separately. The relevant retrieval unit is the **case**, so a
hit on ANY opinion under the target cluster counts — and the ranked list must be
collapsed to cluster granularity before scoring (lead + dissent of the same case
should not occupy two of the top-5 slots).

The eval set (``data/caselaw_eval_queries.json``) pairs a natural-language
description of each case's holding — what an attorney would type WITHOUT naming the
case — with the decision it should surface. This is the hard, realistic test of the
embeddings: conceptual recall, not citation/name lookup.

Three production retrievers are measured in isolation and fused:

    vector  — pgvector cosine over NodeChunk passages (the caselaw workhorse)
    fts      — Postgres tsvector (lexical control; weak on paraphrase)
    hybrid   — fts + trigram + vector, RRF-fused (production core path)

optionally (``--rerank``) two cross-encoder configs:

    vector_rr — top-pool of vector, re-scored by the Voyage reranker
    hybrid_rr — top-pool of hybrid, re-scored by the Voyage reranker

Reported per config: hit@k, MRR, nDCG@k (k=1,3,5,10), recovered-rate, and the
case-level rank of the target in every query — plus, for every miss, the cases that
outranked the target (the single most useful diagnostic for tuning).

    python manage.py eval_caselaw
    python manage.py eval_caselaw --rerank
    python manage.py eval_caselaw --scope all          # don't scope to caselaw
    python manage.py eval_caselaw --deep 200 --k 1,3,5,10
    python manage.py eval_caselaw --out benchmarks/caselaw/run.json
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
from apps.corpus.services.rerank import NoopReranker, default_reranker
from apps.corpus.services.retrieval import DEFAULT_MMR_LAMBDA, retrieve_context
from apps.corpus.services.retrieval_judge import OpenAIRetrievalJudge, default_judge
from apps.corpus.services.search import fts_search, hybrid_search, vector_search
from apps.corpus.services.voyage import (
    EMBEDDING_DIM,
    INPUT_TYPE_QUERY,
    FakeEmbeddingClient,
    default_client,
)

DEFAULT_QUERIES = "apps/corpus/data/caselaw_eval_queries.json"
DEFAULT_OUT = "benchmarks/caselaw/caselaw_retrieval.json"

# Per-doc char cap when reranking. Opinions run to 100k+ chars; the reranker
# truncates anyway and a whole-opinion request would blow the per-request token
# budget. We feed heading + a body prefix (production reranks heading+body); the
# prefix usually carries the syllabus/holding, where the conceptual signal sits.
RERANK_DOC_CHARS = 8000

# Per-case excerpt fed to the LLM judge. The opinion start carries the
# syllabus/issue/disposition, which is what a relevance/answerability call needs;
# a few thousand chars × judge-k cases keeps one judge request well within budget.
JUDGE_EXCERPT_CHARS = 1800


class _CachedClient:
    """Returns a pre-computed query vector at zero network cost so the real
    retrievers run while we time the embed round-trip once, separately."""

    def __init__(self, model: str, vector: list[float]):
        self.model = model
        self._vector = vector

    def embed_texts(self, texts, *, input_type=INPUT_TYPE_QUERY):
        return [self._vector for _ in texts]


def _cluster_of(path: str) -> str:
    """Decision cluster a node path belongs to: the segment before the first '/'.
    Opinion paths are ``cl-cluster-<id>/op-<id>``; a decision path is the cluster
    itself, so this is identity for decision nodes."""
    return path.split("/", 1)[0]


def _pctile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, math.ceil(q * len(s)) - 1))
    return s[idx]


def _wilson_ci(successes: float, n: int, z: float = 1.96) -> list[float]:
    """Wilson score 95% CI for a binomial proportion (``successes/n``).

    Use Wilson, not the normal approximation: at our regime (n≈20, hit@1 in
    0.2–0.75) the normal interval over/under-covers badly and can stray outside
    [0,1]. This is what makes an A/B delta falsifiable — if two configs' hit@1
    intervals overlap heavily at n=20, the 'win' is inside the noise floor and
    must not be shipped on this eval alone. Returns ``[low, high]`` clamped to
    [0,1]. ``successes`` is a float because hit@k is summed from per-query 1.0/0.0."""
    if n <= 0:
        return [0.0, 0.0]
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def _dist(values: list) -> dict:
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


def _metrics_from_rank(first_rank: int | None, ks: list[int]) -> dict:
    """Single-relevant-item ranking metrics from the target's first rank.

    With exactly one relevant item, recall@k == hit@k and ideal-DCG == 1, so
    nDCG@k collapses to 1/log2(rank+1) when the item is within k."""
    out = {
        "first_rank": first_rank,
        "reciprocal_rank": (1.0 / first_rank) if first_rank else 0.0,
        "hit": {},
        "ndcg": {},
    }
    for k in ks:
        within = first_rank is not None and first_rank <= k
        out["hit"][str(k)] = 1.0 if within else 0.0
        out["ndcg"][str(k)] = (1.0 / math.log2(first_rank + 1)) if within else 0.0
    return out


def _rank_clusters(
    hits: list[tuple[int, float]], nv_to_cluster: dict[int, str]
) -> list[tuple[str, float]]:
    """Collapse a ranked ``[(nv_id, score), ...]`` list to cluster granularity,
    keeping each cluster once at its best (first) appearance."""
    seen: set[str] = set()
    out: list[tuple[str, float]] = []
    for nv_id, score in hits:
        cl = nv_to_cluster.get(nv_id)
        if cl is None or cl in seen:
            continue
        seen.add(cl)
        out.append((cl, score))
    return out


class Command(BaseCommand):
    help = "Case-level retrieval eval over the embedded caselaw corpus."

    def add_arguments(self, parser):
        parser.add_argument("--queries", default=DEFAULT_QUERIES)
        parser.add_argument("--out", default=DEFAULT_OUT)
        parser.add_argument("--k", default="1,3,5,10")
        parser.add_argument(
            "--deep",
            type=int,
            default=100,
            help="Candidate depth per retriever for rank-based metrics.",
        )
        parser.add_argument(
            "--scope",
            choices=["caselaw", "all"],
            default="caselaw",
            help="'caselaw' scopes every retriever to the eval set's source; "
            "'all' searches the whole corpus (statutes compete).",
        )
        parser.add_argument(
            "--rerank",
            action="store_true",
            help="Also measure vector_rr / hybrid_rr (Voyage cross-encoder).",
        )
        parser.add_argument("--rerank-pool", type=int, default=20)
        parser.add_argument(
            "--ef-search",
            type=int,
            default=None,
            help="Override hnsw.ef_search (pgvector default 40) for this run, "
            "session-scoped. Raising it widens the HNSW beam — the single biggest "
            "recall lever for the chunk index.",
        )
        parser.add_argument(
            "--judge",
            action="store_true",
            help="Run an OpenAI LLM-judge pass over the top-K retrieved cases: it "
            "answers each query from what was retrieved and grades answerability, "
            "the controlling case, and stale (overruled) law surfaced. Needs "
            "OPENAI_API_KEY. Measures answer quality, which rank metrics cannot.",
        )
        parser.add_argument(
            "--judge-model",
            default="gpt-4o",
            help="OpenAI model for the judge (default gpt-4o).",
        )
        parser.add_argument(
            "--judge-config",
            default=None,
            help="Which retriever's top-K the judge reads (default: hybrid_rr if "
            "--rerank else hybrid).",
        )
        parser.add_argument("--judge-k", type=int, default=5)
        parser.add_argument(
            "--use-retrieve-context",
            action="store_true",
            help="Add an 'rc' config that routes through the production shared "
            "pipeline (apps.corpus.services.retrieval.retrieve_context): hybrid "
            "retrieve -> Voyage rerank (citation lane bypasses) -> decision-cluster "
            "dedup -> MMR -> chunk-aware excerpts -> U-order. This is the ONLY "
            "config that exercises the PR2 surface behaviors; the others measure "
            "raw retrievers. Pair with --judge --judge-config rc to grade the "
            "chunk-centered excerpts the chat/MCP surfaces actually return.",
        )
        # PR2 A/B knobs — isolate one rc behavior. dedup/u-order/chunk-excerpt
        # default ON (production); MMR defaults OFF (eval showed it regresses),
        # so it is opt-IN here via --rc-mmr.
        parser.add_argument("--rc-no-dedup", action="store_true")
        parser.add_argument("--rc-mmr", action="store_true")
        parser.add_argument("--rc-no-u-order", action="store_true")
        parser.add_argument("--rc-no-chunk-excerpt", action="store_true")
        # Phase 3 authority blend (retrieve_context authority_weight /
        # authority_court_bonus). 0.0 = off = the phase3_baseline_* behavior.
        parser.add_argument("--rc-authority", type=float, default=0.0)
        parser.add_argument("--rc-authority-court", type=float, default=0.0)
        # Phase 3 latency levers.
        parser.add_argument("--rc-no-trigram", action="store_true")
        parser.add_argument("--rc-doc-chars", type=int, default=None)
        parser.add_argument(
            "--allow-fake",
            action="store_true",
            help="Permit the fake embedder (results are meaningless; wiring smoke only).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print the cases that outranked the target for every query, not just misses.",
        )

    def handle(self, *args, **opts):
        client = default_client()
        if isinstance(client, FakeEmbeddingClient) and not opts["allow_fake"]:
            raise CommandError(
                "default_client() is the FAKE embedder (VOYAGE_API_KEY unset). "
                "Pass --allow-fake only for a wiring smoke test."
            )

        ks = sorted({int(x) for x in opts["k"].split(",") if x.strip()})
        deep = opts["deep"]
        if max(ks) > deep:
            raise CommandError(f"--deep ({deep}) must be >= max --k ({max(ks)}).")

        qpath = Path(settings.BASE_DIR) / opts["queries"]
        if not qpath.exists():
            raise CommandError(f"queries file not found: {qpath}")
        payload = json.loads(qpath.read_text())
        entries = [e for e in payload.get("queries", []) if e.get("query")]
        if not entries:
            raise CommandError("no queries with a 'query' field")

        scope_source = payload.get("scope_source", "iowa-caselaw")
        source_slug = scope_source if opts["scope"] == "caselaw" else None
        src = Source.objects.filter(slug=scope_source).first()
        if src is None:
            raise CommandError(f"source '{scope_source}' not loaded.")

        rerank_on = opts["rerank"]
        rerank_pool = opts["rerank_pool"]
        reranker = default_reranker() if rerank_on else None
        if rerank_on and isinstance(reranker, NoopReranker):
            raise CommandError(
                "default_reranker() is the NOOP reranker (VOYAGE_API_KEY unset)."
            )
        if rerank_on and max(ks) > rerank_pool:
            raise CommandError(f"--rerank-pool must be >= max --k ({max(ks)}).")

        configs = ["vector", "fts", "hybrid"]
        if rerank_on:
            configs += ["vector_rr", "hybrid_rr"]

        # The shared-pipeline config. rc reranks with Voyage internally regardless
        # of --rerank (it mirrors production), so it needs a real reranker.
        rc_on = opts["use_retrieve_context"]
        rc_reranker = default_reranker()
        if rc_on and isinstance(rc_reranker, NoopReranker):
            raise CommandError(
                "--use-retrieve-context needs the Voyage reranker (VOYAGE_API_KEY "
                "unset → NoopReranker, which would not exercise the rerank lane)."
            )
        rc_kwargs = dict(
            dedup_clusters=not opts["rc_no_dedup"],
            # MMR is off in production (it regressed); --rc-mmr opts it back in.
            mmr_lambda=DEFAULT_MMR_LAMBDA if opts["rc_mmr"] else None,
            u_order=not opts["rc_no_u_order"],
            chunk_excerpts=not opts["rc_no_chunk_excerpt"],
            authority_weight=opts["rc_authority"],
            authority_court_bonus=opts["rc_authority_court"],
            use_trigram=not opts["rc_no_trigram"],
        )
        if opts["rc_doc_chars"] is not None:
            rc_kwargs["rerank_doc_chars"] = opts["rc_doc_chars"]
        if rc_on:
            configs.append("rc")

        # LLM judge (optional). Reads ONE config's top-K per query.
        judge_on = opts["judge"]
        judge = None
        judge_config = opts["judge_config"] or ("hybrid_rr" if rerank_on else "hybrid")
        judge_k = opts["judge_k"]
        if judge_on:
            if judge_config not in configs:
                raise CommandError(
                    f"--judge-config '{judge_config}' not in active configs {configs} "
                    f"(did you forget --rerank?)."
                )
            judge = (
                OpenAIRetrievalJudge(model=opts["judge_model"])
                if getattr(settings, "OPENAI_API_KEY", "")
                else default_judge()
            )
            if judge is None:
                raise CommandError("--judge needs OPENAI_API_KEY (settings/.env).")

        # Validate targets resolve to a loaded decision cluster.
        target_paths = {e["target_cluster"] for e in entries}
        loaded_clusters = set(
            Node.objects.filter(
                source=src, parent__isnull=True, path__in=target_paths
            ).values_list("path", flat=True)
        )
        missing = sorted(target_paths - loaded_clusters)
        if missing:
            self.stderr.write(
                self.style.WARNING(f"targets not loaded (skipped): {missing}")
            )
        entries = [e for e in entries if e["target_cluster"] in loaded_clusters]
        if not entries:
            raise CommandError("no eval targets are loaded in this corpus.")

        self.stdout.write("Warming up embedder ...")
        client.embed_texts(["warmup"], input_type=INPUT_TYPE_QUERY)

        # Optionally widen the HNSW beam (session-scoped). pgvector registers the
        # hnsw.ef_search GUC only after its module loads, so run one real vector
        # query first (loads the module on this connection), then SET it; the
        # value then sticks for every vector_search/hybrid_search in this process.
        # Load the pgvector module on this connection (the connection_created
        # signal already sets hnsw.ef_search, but a warmup query guarantees the
        # GUC is registered before we read or override it).
        vector_search("warmup", limit=1, source_slug=source_slug, client=client)
        from django.db import connection

        ef_search = opts["ef_search"]
        if ef_search is not None:
            with connection.cursor() as cur:
                cur.execute("SET hnsw.ef_search = %s;", [ef_search])
            self.stdout.write(f"hnsw.ef_search set to {ef_search} (session-scoped).")
        # Record whatever is actually in effect (signal default or override).
        with connection.cursor() as cur:
            cur.execute("SHOW hnsw.ef_search;")
            effective_ef = cur.fetchone()[0]

        latency = {"embed": [], "vector": [], "fts": [], "hybrid": []}
        if rerank_on:
            latency["rerank"] = []
        if judge_on:
            latency["judge"] = []
        if rc_on:
            latency["rc"] = []
        # rc shows this many passages — enough for the deepest rank metric and the
        # judge to both read the same displayed set.
        rc_display = max(max(ks), judge_k if judge_on else 0)
        per_query: list[dict] = []

        for e in entries:
            query = e["query"].strip()
            target = e["target_cluster"]

            # 1) embed once (timed), reuse for vector + hybrid.
            t = time.perf_counter()
            [qvec] = client.embed_texts([query], input_type=INPUT_TYPE_QUERY)
            latency["embed"].append((time.perf_counter() - t) * 1000)
            cached = _CachedClient(client.model, qvec)

            # 2) run the three retrievers deep.
            t = time.perf_counter()
            vec_hits = vector_search(
                query, limit=deep, source_slug=source_slug, client=cached
            )
            latency["vector"].append((time.perf_counter() - t) * 1000)

            t = time.perf_counter()
            fts_hits = fts_search(query, limit=deep, source_slug=source_slug)
            latency["fts"].append((time.perf_counter() - t) * 1000)

            t = time.perf_counter()
            hyb_objs = hybrid_search(
                query,
                limit=deep,
                per_retriever=deep,
                source_slug=source_slug,
                client=cached,
            )
            latency["hybrid"].append((time.perf_counter() - t) * 1000)
            hyb_hits = [(h.node_version_id, h.score) for h in hyb_objs]

            # 3) map every returned nv -> cluster (one batched query per config union).
            all_ids = {i for i, _ in (*vec_hits, *fts_hits, *hyb_hits)}
            nv_to_cluster = {
                nv_id: _cluster_of(path)
                for nv_id, path in NodeVersion.objects.filter(
                    id__in=all_ids
                ).values_list("id", "node__path")
            }

            ranked = {
                "vector": _rank_clusters(vec_hits, nv_to_cluster),
                "fts": _rank_clusters(fts_hits, nv_to_cluster),
                "hybrid": _rank_clusters(hyb_hits, nv_to_cluster),
            }

            # 4) optional rerank of each pool (heading + body prefix of the opinion).
            if rerank_on:
                ranked["vector_rr"] = self._rerank_config(
                    query, vec_hits, rerank_pool, reranker, latency
                )
                ranked["hybrid_rr"] = self._rerank_config(
                    query, hyb_hits, rerank_pool, reranker, latency
                )

            # 4b) the shared production pipeline (PR2 surface behaviors).
            rc_passages = []
            if rc_on:
                t = time.perf_counter()
                ctx = retrieve_context(
                    query,
                    source_slug=source_slug,
                    use_vector=True,
                    candidate_pool=deep,
                    display_limit=rc_display,
                    rerank=True,
                    reranker=rc_reranker,
                    enrich_bodies=True,
                    **rc_kwargs,
                )
                latency["rc"].append((time.perf_counter() - t) * 1000)
                rc_passages = ctx.passages
                # Passages are already cluster-deduped (dedup on); U-order is a
                # set-preserving presentation reorder, so hit@k/recovered are
                # honest, MRR reflects displayed order.
                ranked["rc"] = [
                    (_cluster_of(p.path), p.score) for p in rc_passages
                ]

            row = {
                "id": e.get("id"),
                "case_name": e.get("case_name"),
                "citation": e.get("citation"),
                "area": e.get("area"),
                "query": query,
                "target": target,
                "configs": {},
            }
            for cfg, rc in ranked.items():
                clusters = [c for c, _ in rc]
                first_rank = (
                    clusters.index(target) + 1 if target in clusters else None
                )
                m = _metrics_from_rank(first_rank, ks)
                # Distinct decision-clusters shown in the top-k — the dedup signal.
                # The raw configs are already cluster-collapsed (_rank_clusters),
                # so this is ~min(k, len) for them; it only drops below k for an
                # rc run with dedup OFF (duplicate opinions filling slots).
                m["distinct_clusters"] = {
                    str(k): len(set(clusters[:k])) for k in ks
                }
                # cases ranked above the target (diagnostic) + target's own score.
                above = clusters[: (first_rank - 1) if first_rank else len(clusters)]
                m["outranked_by"] = above[:5]
                if cfg == "vector":
                    m["top1_sim"] = round(rc[0][1], 4) if rc else None
                    m["target_sim"] = (
                        round(rc[first_rank - 1][1], 4) if first_rank else None
                    )
                row["configs"][cfg] = m

            # 5) optional LLM-judge pass over the judge config's top-K.
            if judge_on:
                if judge_config == "rc":
                    # Judge the SAME chunk-centered excerpts the surface returns —
                    # this is what measures the chunk-excerpt change on answerable.
                    cases = self._rc_judge_cases(src, rc_passages, judge_k)
                else:
                    jclusters = [c for c, _ in ranked.get(judge_config, [])]
                    cases = self._judge_payload(src, jclusters, judge_k)
                t = time.perf_counter()
                verdict = judge.judge(query, cases)
                latency["judge"].append((time.perf_counter() - t) * 1000)
                shown = [c["cluster"] for c in cases]
                row["judge"] = {
                    **verdict.to_dict(),
                    "config": judge_config,
                    "shown_clusters": shown,
                    "shown_cases": [c["case_name"] for c in cases],
                    "target_in_shown": target in shown,
                }

            per_query.append(row)

        # case names for clusters that show up in diagnostics.
        diag_clusters: set[str] = set()
        for r in per_query:
            for m in r["configs"].values():
                diag_clusters.update(m["outranked_by"])
            diag_clusters.add(r["target"])
        cluster_names = {
            p: (md or {}).get("case_name", p)
            for p, md in Node.objects.filter(
                source=src, path__in=diag_clusters
            ).values_list("path", "source_metadata")
        }

        results = self._aggregate(per_query, ks, configs)
        if judge_on:
            results["judge"] = self._aggregate_judge(
                per_query, judge_config, judge.model, judge_k
            )
        snapshot = {
            "meta": {
                "kind": "caselaw-retrieval-eval",
                "embedder": client.model,
                "embedding_dim": EMBEDDING_DIM,
                "reranker": (
                    getattr(reranker, "model", "?") if rerank_on else "none"
                ),
                # The rc config reranks with default_reranker() (Voyage) regardless
                # of --rerank, so record it separately — else an rc-only run looks
                # like "reranker: none" when it actually reranked the whole pool.
                "rc": (
                    {"reranker": getattr(rc_reranker, "model", "?"), **rc_kwargs}
                    if rc_on
                    else None
                ),
                "judge": (judge.model if judge_on else "none"),
                "judge_config": (judge_config if judge_on else None),
                "scope": opts["scope"],
                "scope_source": scope_source if source_slug else "(whole corpus)",
                "hnsw_ef_search": effective_ef,
                "configs": configs,
                "deep_candidates": deep,
                "k_values": ks,
                "n_queries": len(per_query),
                "git_commit": _git_commit(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "results": results,
            "latency_ms": {n: _dist(v) for n, v in latency.items()},
            "per_query": per_query,
        }
        out_path = Path(settings.BASE_DIR) / opts["out"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2))

        self._report(snapshot, ks, cluster_names, verbose=opts["verbose"])
        self.stdout.write(self.style.SUCCESS(f"\nSnapshot written: {out_path}"))

    def _rerank_config(self, query, hits, pool, reranker, latency):
        ids = [nv_id for nv_id, _ in hits[:pool]]
        if not ids:
            return []
        texts = {
            i: f"{(h or '')}\n{(b or '')[:RERANK_DOC_CHARS]}"
            for i, h, b in NodeVersion.objects.filter(id__in=ids).values_list(
                "id", "node__heading", "body_text"
            )
        }
        cands = [(i, texts.get(i, "")) for i in ids]
        t = time.perf_counter()
        ranked_ids = reranker.rerank(query, cands, top_k=pool)
        latency["rerank"].append((time.perf_counter() - t) * 1000)
        # rerank only reorders within the pool; map back to clusters.
        nv_to_cluster = {
            nv_id: _cluster_of(path)
            for nv_id, path in NodeVersion.objects.filter(
                id__in=ranked_ids
            ).values_list("id", "node__path")
        }
        return _rank_clusters([(i, 0.0) for i in ranked_ids], nv_to_cluster)

    def _judge_payload(self, src, clusters, k):
        """Build the judge's view of the top-K clusters: case name + citation +
        date + a start-of-opinion excerpt (the syllabus/issue/disposition)."""
        clusters = clusters[:k]
        meta = {
            p: (md or {})
            for p, md in Node.objects.filter(
                source=src, path__in=clusters
            ).values_list("path", "source_metadata")
        }
        cases = []
        for i, cl in enumerate(clusters, 1):
            md = meta.get(cl, {})
            body = (
                NodeVersion.objects.filter(node__source=src, node__parent__path=cl)
                .order_by("node__path")
                .values_list("body_text", flat=True)
                .first()
            ) or ""
            cites = md.get("citations") or []
            cases.append({
                "rank": i,
                "cluster": cl,
                "case_name": md.get("case_name") or cl,
                "citation": cites[0] if cites else "",
                "date": md.get("date_filed") or "",
                "excerpt": " ".join(body.split())[:JUDGE_EXCERPT_CHARS],
            })
        return cases

    def _rc_judge_cases(self, src, passages, k):
        """Judge view of the rc config: the chunk-centered excerpt the surface
        actually returns (passage.excerpt), not a fresh opinion-head prefix. The
        case name / citation / date still come from the decision metadata so the
        only thing that varies vs ``_judge_payload`` is the excerpt — which is the
        whole point of measuring the chunk-excerpt change."""
        passages = passages[:k]
        clusters = [_cluster_of(p.path) for p in passages]
        meta = {
            p: (md or {})
            for p, md in Node.objects.filter(
                source=src, path__in=clusters
            ).values_list("path", "source_metadata")
        }
        cases = []
        for i, p in enumerate(passages, 1):
            cl = _cluster_of(p.path)
            md = meta.get(cl, {})
            cites = md.get("citations") or []
            cases.append({
                "rank": i,
                "cluster": cl,
                "case_name": md.get("case_name") or cl,
                "citation": cites[0] if cites else "",
                "date": md.get("date_filed") or "",
                "excerpt": " ".join((p.excerpt or "").split())[:JUDGE_EXCERPT_CHARS],
            })
        return cases

    # ---- aggregation -----------------------------------------------------

    def _aggregate_judge(self, per_query, judge_config, model, k):
        """Roll up the per-query judge verdicts. The headline is the
        answerable-rate (can a correct answer be produced from the top-K),
        which the rank metrics cannot measure; plus a cross-tab against
        target_in_shown that exposes 'relevant-but-not-the-target' wins and
        'controlling case present but stale law ranked above it' failures."""
        rows = [r["judge"] for r in per_query if "judge" in r]
        n = len(rows)
        if not n:
            return {"n": 0}
        ans = {a: sum(1 for r in rows if r["answerable"] == a)
               for a in ("yes", "partial", "no")}
        in_shown = [r for r in rows if r["target_in_shown"]]
        not_shown = [r for r in rows if not r["target_in_shown"]]
        stale = [r for r in rows if r.get("stale_warning")]
        return {
            "config": judge_config,
            "model": model,
            "k": k,
            "n": n,
            "errors": sum(1 for r in rows if r.get("error")),
            "answerable_counts": ans,
            "answerable_yes_rate": round(ans["yes"] / n, 4),
            "answerable_yes_or_partial_rate": round((ans["yes"] + ans["partial"]) / n, 4),
            "controlling_present_rate": round(
                sum(1 for r in rows if r["controlling_present"]) / n, 4
            ),
            "stale_warning_count": len(stale),
            "stale_cases": [
                {"id": pr["id"], "warning": pr["judge"]["stale_warning"]}
                for pr in per_query
                if pr.get("judge", {}).get("stale_warning")
            ],
            "target_in_shown_rate": round(len(in_shown) / n, 4),
            # The key cross-tab: when the labeled target is NOT in the shown
            # top-K, can the question still be answered from the neighbors?
            "answerable_when_target_absent": {
                "n": len(not_shown),
                "yes_or_partial": sum(
                    1 for r in not_shown if r["answerable"] in ("yes", "partial")
                ),
            },
        }

    def _aggregate(self, per_query, ks, configs):
        n = max(len(per_query), 1)
        out = {"overall": {}, "by_area": {}}
        for cfg in configs:
            ms = [r["configs"][cfg] for r in per_query]
            ranks = [m["first_rank"] for m in ms if m["first_rank"]]
            out["overall"][cfg] = {
                "mrr": round(sum(m["reciprocal_rank"] for m in ms) / n, 4),
                "hit": {
                    str(k): round(sum(m["hit"][str(k)] for m in ms) / n, 4) for k in ks
                },
                # Wilson 95% CI per hit@k — overlap between configs == not
                # significant at this n. See _wilson_ci.
                "hit_ci": {
                    str(k): _wilson_ci(sum(m["hit"][str(k)] for m in ms), n)
                    for k in ks
                },
                "ndcg": {
                    str(k): round(sum(m["ndcg"][str(k)] for m in ms) / n, 4)
                    for k in ks
                },
                "distinct_clusters": {
                    str(k): round(
                        mean(m["distinct_clusters"][str(k)] for m in ms), 2
                    )
                    for k in ks
                },
                "recovered_rate": round(len(ranks) / n, 4),
                "recovered_ci": _wilson_ci(len(ranks), n),
                "unrecovered": sum(1 for m in ms if m["first_rank"] is None),
                "rank": {
                    "p50": median(ranks) if ranks else None,
                    "mean": round(mean(ranks), 2) if ranks else None,
                    "max": max(ranks) if ranks else None,
                },
            }
        areas = sorted({r["area"] for r in per_query if r.get("area")})
        for a in areas:
            rows = [r for r in per_query if r.get("area") == a]
            out["by_area"][a] = {"n": len(rows)}
            for cfg in configs:
                ms = [r["configs"][cfg] for r in rows]
                out["by_area"][a][cfg] = {
                    "hit@1": round(mean(m["hit"]["1"] for m in ms), 3),
                    "hit@5": round(mean(m["hit"]["5"] for m in ms), 3),
                    "mrr": round(mean(m["reciprocal_rank"] for m in ms), 3),
                }
        # vector similarity analytics
        vms = [r["configs"]["vector"] for r in per_query]
        out["vector_analytics"] = {
            "top1_sim": _dist([m.get("top1_sim") for m in vms]),
            "target_sim": _dist([m.get("target_sim") for m in vms]),
        }
        return out

    # ---- reporting -------------------------------------------------------

    def _report(self, snap, ks, names, verbose):
        m = snap["meta"]
        w = self.stdout.write
        h = self.style.MIGRATE_HEADING

        def nm(cluster):
            s = names.get(cluster, cluster)
            return (s[:38] + "…") if len(s) > 39 else s

        w("\n" + "=" * 78)
        w(h("CASELAW RETRIEVAL EVAL"))
        w(f"  embedder : {m['embedder']}  ({m['embedding_dim']}-dim, cosine)")
        w(f"  scope    : {m['scope']}  ->  {m['scope_source']}")
        w(f"  reranker : {m['reranker']}   deep={m['deep_candidates']}   "
          f"hnsw.ef_search={m['hnsw_ef_search']}   commit={m['git_commit']}")
        w(f"  queries  : {m['n_queries']} landmark Iowa cases "
          f"(natural-language holding -> case)")

        # config comparison
        w("\n" + "-" * 78)
        w(h("RANKING QUALITY  (case-level; ANY opinion of the case counts)"))
        kmax = max(ks)
        hdr = (f"  {'config':9s} {'MRR':>6s}  "
               + "  ".join(f"hit@{k}" for k in ks)
               + "   " + "  ".join(f"ndcg@{k}" for k in ks)
               + f"   recov  medR  dist@{kmax}")
        w(hdr)
        for cfg in m["configs"]:
            c = snap["results"]["overall"][cfg]
            hits = "  ".join(f" {c['hit'][str(k)]:.2f}" for k in ks)
            ndcg = "  ".join(f"  {c['ndcg'][str(k)]:.2f}" for k in ks)
            medr = c["rank"]["p50"]
            medr = f"{medr:.0f}" if medr is not None else "—"
            dist = c.get("distinct_clusters", {}).get(str(kmax))
            dist = f"{dist:.2f}" if dist is not None else "—"
            w(f"  {cfg:9s} {c['mrr']:.3f}  {hits}   {ndcg}   "
              f"{c['recovered_rate']:.0%}   {medr:>3s}   {dist:>5s}")

        # Wilson 95% CIs on the headline binomial metrics. At small n these are
        # wide on purpose: when two configs' intervals overlap heavily the
        # difference is inside the noise floor — don't ship it on this eval alone.
        ci_ks = [kk for kk in (1, 5) if kk in ks] or [min(ks)]
        w(f"\n  95% CI (Wilson, n={m['n_queries']}) — "
          + " / ".join(f"hit@{kk}" for kk in ci_ks) + ":")
        for cfg in m["configs"]:
            c = snap["results"]["overall"][cfg]
            cells = "   ".join(
                f"hit@{kk} {c['hit'][str(kk)]:.2f} "
                f"[{c['hit_ci'][str(kk)][0]:.2f},{c['hit_ci'][str(kk)][1]:.2f}]"
                for kk in ci_ks
            )
            w(f"    {cfg:9s} {cells}")

        va = snap["results"]["vector_analytics"]
        w(f"\n  vector cosine — target best-chunk sim: "
          f"p50={va['target_sim'].get('p50')}  "
          f"min={va['target_sim'].get('min')}  max={va['target_sim'].get('max')}")
        w(f"  vector cosine — rank-1 hit sim:        "
          f"p50={va['top1_sim'].get('p50')}  max={va['top1_sim'].get('max')}")

        # per-query rank matrix
        w("\n" + "-" * 78)
        w(h("PER-QUERY CASE-LEVEL RANK  (· = not found in top-%d)" % m["deep_candidates"]))
        cfgs = m["configs"]
        w("  #  " + "case".ljust(26) + "area".ljust(22)
          + "".join(f"{c[:7]:>9s}" for c in cfgs))
        for r in snap["per_query"]:
            cells = ""
            for cfg in cfgs:
                fr = r["configs"][cfg]["first_rank"]
                cells += f"{(str(fr) if fr else '·'):>9s}"
            case = (r["case_name"] or "")[:25]
            area = (r["area"] or "")[:21]
            w(f"  {r['id']:<2d} {case:26s}{area:22s}{cells}")

        # by area
        w("\n" + "-" * 78)
        w(h("BY LEGAL AREA  (hit@1 / hit@5 / MRR)"))
        for a, d in snap["results"]["by_area"].items():
            w(f"  {a:34s} n={d['n']}")
            for cfg in cfgs:
                s = d[cfg]
                w(f"      {cfg:9s}  hit@1={s['hit@1']:.2f}  "
                  f"hit@5={s['hit@5']:.2f}  mrr={s['mrr']:.2f}")

        # miss diagnostics (what beat the target)
        w("\n" + "-" * 78)
        w(h("MISS / OUTRANK DIAGNOSTICS"))
        for cfg in cfgs:
            misses = [
                r for r in snap["per_query"]
                if (r["configs"][cfg]["first_rank"] or 999) > (1 if verbose else 5)
            ]
            if not misses:
                w(f"  [{cfg}] clean — every target in top-5.")
                continue
            label = "rank>1" if verbose else "rank>5 or unrecovered"
            w(f"  [{cfg}] {len(misses)} {label}:")
            for r in misses:
                fr = r["configs"][cfg]["first_rank"]
                above = r["configs"][cfg]["outranked_by"]
                frs = str(fr) if fr else f">{m['deep_candidates']}"
                w(f"    #{r['id']} {r['case_name']}  (rank {frs})")
                for cl in above[:3]:
                    flag = "  <-- TARGET" if cl == r["target"] else ""
                    w(f"        ↑ {nm(cl)}{flag}")

        # LLM judge
        jr = snap["results"].get("judge")
        if jr and jr.get("n"):
            w("\n" + "=" * 78)
            w(h("LLM-JUDGE  (answer quality over the retrieved set — what rank can't see)"))
            w(f"  model    : {jr['model']}   reads: top-{jr['k']} of '{jr['config']}'")
            a = jr["answerable_counts"]
            w(f"  answerable from top-{jr['k']}:  yes={a['yes']}  partial={a['partial']}  "
              f"no={a['no']}   (yes {jr['answerable_yes_rate']:.0%}, "
              f"yes+partial {jr['answerable_yes_or_partial_rate']:.0%})")
            w(f"  controlling case present : {jr['controlling_present_rate']:.0%}")
            w(f"  ground-truth in shown top-{jr['k']} : {jr['target_in_shown_rate']:.0%}")
            ta = jr["answerable_when_target_absent"]
            if ta["n"]:
                w(f"  -> when ground-truth NOT shown ({ta['n']} q): "
                  f"{ta['yes_or_partial']} still answerable from neighbors "
                  f"(relevant-but-not-the-target wins)")
            if jr["stale_warning_count"]:
                w(f"  STALE-LAW WARNINGS : {jr['stale_warning_count']} "
                  f"(relevant cases surfaced that are overruled/superseded):")
                for sc in jr["stale_cases"]:
                    w(f"      #{sc['id']}: {sc['warning']}")

            w("\n" + "-" * 78)
            w(h("PER-QUERY JUDGE ANSWERS"))
            for r in snap["per_query"]:
                j = r.get("judge")
                if not j:
                    continue
                flag = "✓shown" if j["target_in_shown"] else "✗not-shown"
                w(f"\n  #{r['id']} [{r.get('area','')}]  ans={j['answerable'].upper()}  "
                  f"controlling={'Y' if j['controlling_present'] else 'N'}  "
                  f"target={flag}")
                w(f"     Q: {r['query'][:96]}")
                w(f"     best: {j['best_case']}")
                w(f"     A: {j['answer']}")
                if j["stale_warning"]:
                    w(f"     ⚠ stale: {j['stale_warning']}")
                if j.get("error"):
                    w(f"     ! judge error: {j['error']}")

        # latency
        w("\n" + "-" * 78)
        w("latency (ms):")
        for name, d in snap["latency_ms"].items():
            if d.get("n"):
                w(f"  {name:9s} p50={d['p50']:.0f}  p90={d['p90']:.0f}  max={d['max']:.0f}")
