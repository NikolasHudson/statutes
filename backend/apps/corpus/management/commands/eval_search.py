"""Run the search eval set and report precision@K.

    python manage.py eval_search                        # default K=5
    python manage.py eval_search --k 10
    python manage.py eval_search --include-pending      # see pending versions too
    python manage.py eval_search --no-vector            # skip embeddings
    python manage.py eval_search --queries path/to.json # custom eval set

Output: per-query hit/miss with the top-K paths returned, then a summary
block with precision@K (averaged over queries that have at least one expected
path present in the loaded corpus). Queries whose expected paths are not
loaded are skipped with a warning so partial corpora don't tank the score.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.corpus.models import Node
from apps.corpus.services.search import hybrid_search


DEFAULT_QUERIES_PATH = (
    Path(settings.BASE_DIR) / "apps" / "corpus" / "data" / "search_eval_queries.json"
)


class Command(BaseCommand):
    help = "Run the search eval set and report precision@K."

    def add_arguments(self, parser):
        parser.add_argument("--k", type=int, default=5)
        parser.add_argument("--no-vector", action="store_true")
        parser.add_argument("--include-pending", action="store_true")
        parser.add_argument(
            "--queries",
            type=str,
            default=str(DEFAULT_QUERIES_PATH),
            help="Path to the eval queries JSON file.",
        )
        parser.add_argument(
            "--verbose-misses",
            action="store_true",
            help="Print full top-K paths for queries that miss.",
        )

    def handle(self, *args, **opts):
        queries_path = Path(opts["queries"])
        if not queries_path.exists():
            raise CommandError(f"queries file not found: {queries_path}")

        try:
            payload = json.loads(queries_path.read_text())
        except json.JSONDecodeError as e:
            raise CommandError(f"invalid JSON: {e}") from e

        queries = payload.get("queries")
        if not isinstance(queries, list) or not queries:
            raise CommandError("queries file must contain a non-empty 'queries' list")

        loaded_paths = set(
            Node.objects.values_list("path", flat=True)
        )

        k = opts["k"]
        scored_queries: list[dict] = []
        skipped: list[dict] = []

        for entry in queries:
            query = entry["query"]
            expected = set(entry.get("expected_paths", []))
            tags = entry.get("tags", [])

            available_expected = expected & loaded_paths
            if not available_expected:
                skipped.append({"query": query, "expected": sorted(expected)})
                continue

            hits = hybrid_search(
                query,
                limit=k,
                include_pending=opts["include_pending"],
                use_vector=not opts["no_vector"],
            )
            top_paths = [h.path for h in hits]
            matched = available_expected & set(top_paths)
            precision = len(matched) / max(len(top_paths), 1)
            recall = len(matched) / len(available_expected)
            hit_at_k = bool(matched)

            scored_queries.append(
                {
                    "query": query,
                    "tags": tags,
                    "expected_in_corpus": sorted(available_expected),
                    "top_paths": top_paths,
                    "matched": sorted(matched),
                    "precision_at_k": precision,
                    "recall_at_k": recall,
                    "hit_at_k": hit_at_k,
                }
            )

        self._print_per_query(scored_queries, k, verbose_misses=opts["verbose_misses"])
        self._print_summary(scored_queries, skipped, k)

    def _print_per_query(
        self, scored: list[dict], k: int, verbose_misses: bool
    ):
        for row in scored:
            status = (
                self.style.SUCCESS("HIT ")
                if row["hit_at_k"]
                else self.style.ERROR("MISS")
            )
            self.stdout.write(
                f"{status} p@{k}={row['precision_at_k']:.2f} "
                f"r@{k}={row['recall_at_k']:.2f}  "
                f"{row['query']!r}"
            )
            if not row["hit_at_k"] or verbose_misses:
                self.stdout.write(
                    f"    expected: {row['expected_in_corpus']}"
                )
                self.stdout.write(f"    got     : {row['top_paths']}")

    def _print_summary(
        self, scored: list[dict], skipped: list[dict], k: int
    ):
        if not scored:
            self.stdout.write(self.style.WARNING("\nNo scoreable queries."))
            return
        n = len(scored)
        avg_p = sum(r["precision_at_k"] for r in scored) / n
        avg_r = sum(r["recall_at_k"] for r in scored) / n
        hits = sum(1 for r in scored if r["hit_at_k"])

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.MIGRATE_HEADING(f"Eval @ K={k}"))
        self.stdout.write(f"  scored queries:    {n}")
        self.stdout.write(f"  hit@{k}:           {hits}/{n} ({hits/n:.0%})")
        self.stdout.write(f"  mean precision@{k}: {avg_p:.3f}")
        self.stdout.write(f"  mean recall@{k}:    {avg_r:.3f}")

        # Tag-level breakdown.
        by_tag: dict[str, list[dict]] = {}
        for r in scored:
            for t in r["tags"]:
                by_tag.setdefault(t, []).append(r)
        if by_tag:
            self.stdout.write("\n  by tag:")
            for tag, rows in sorted(by_tag.items()):
                tag_p = sum(r["precision_at_k"] for r in rows) / len(rows)
                tag_h = sum(1 for r in rows if r["hit_at_k"])
                self.stdout.write(
                    f"    {tag:20s} n={len(rows):3d}  hit@{k}={tag_h}/{len(rows)}  "
                    f"mean p@{k}={tag_p:.3f}"
                )

        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  skipped {len(skipped)} queries — expected paths not in loaded corpus:"
                )
            )
            for s in skipped[:10]:
                self.stdout.write(f"    - {s['query']!r} expected {s['expected']}")
            if len(skipped) > 10:
                self.stdout.write(f"    ... and {len(skipped) - 10} more")
