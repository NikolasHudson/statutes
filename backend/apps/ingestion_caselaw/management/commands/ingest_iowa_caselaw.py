"""Phase 2+3: write the Iowa caselaw JSONL slice into the corpus tables.

Two streaming passes (decisions → opinions), batched and idempotent. Re-running
is safe: unchanged records are skipped via the preloaded open-version hash map,
and committed batches survive a crash (rerun finishes the rest). Versions are
auto-approved (bulk public caselaw). Use ``--dry-run`` to parse + validate +
count without writing.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...jsonl import iter_jsonl
from ...parser import format_citation, parse_decision, parse_opinion
from ...validators import validate_decision, validate_opinion
from ...writer import (
    get_iowa_caselaw_source,
    get_node_types,
    load_open_version_hashes,
    record_write_run,
    write_decisions_batch,
    write_opinions_batch,
)

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Phase 2+3: write the Iowa caselaw JSONL slice into the corpus."

    def add_arguments(self, parser):
        parser.add_argument(
            "--in-dir",
            required=True,
            help="Directory of Phase-1 JSONL artifacts (clusters/opinions/"
            "citations/dockets).",
        )
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse + validate + count; do not write to the corpus.",
        )

    def handle(self, *args, **opts):
        in_dir = Path(opts["in_dir"])
        batch_size = opts["batch_size"]
        files = {name: in_dir / f"{name}.jsonl"
                 for name in ("clusters", "opinions", "citations", "dockets")}
        for name, path in files.items():
            if not path.exists():
                raise CommandError(f"missing {name}.jsonl in {in_dir}")

        # Small artifacts loaded into memory (Iowa slice is tiny for these).
        citations_by_cluster: dict[int, list[str]] = {}
        for rec in iter_jsonl(files["citations"]):
            citations_by_cluster.setdefault(rec["cl_cluster_id"], []).append(
                format_citation(rec)
            )
        docket_number_by_id: dict[int, str] = {
            rec["docket_id"]: rec.get("docket_number", "")
            for rec in iter_jsonl(files["dockets"])
        }

        issues = Counter()

        def _decisions():
            for rec in iter_jsonl(files["clusters"]):
                parsed = parse_decision(
                    rec,
                    docket_number=docket_number_by_id.get(rec.get("docket_id"), ""),
                    citations=tuple(citations_by_cluster.get(rec["cl_cluster_id"], ())),
                )
                for issue in validate_decision(parsed):
                    issues[issue.code] += 1
                yield parsed

        def _opinions():
            for rec in iter_jsonl(files["opinions"]):
                parsed = parse_opinion(rec)
                for issue in validate_opinion(parsed):
                    issues[issue.code] += 1
                yield parsed

        if opts["dry_run"]:
            n_dec = sum(1 for _ in _decisions())
            n_op = sum(1 for _ in _opinions())
            self.stdout.write(self.style.WARNING("DRY RUN — no writes"))
            self.stdout.write(json.dumps(
                {"decisions": n_dec, "opinions": n_op, "issues": dict(issues)},
                indent=2,
            ))
            return

        source = get_iowa_caselaw_source()
        types = get_node_types(source)
        open_hashes = load_open_version_hashes(source)
        decision_cache: dict[int, tuple[int, dt.date | None]] = {}
        totals: Counter = Counter()
        max_cid = 0

        # Pass A — decisions (build the cluster→node cache for pass B).
        for batch in _batched(_decisions(), batch_size):
            counts, cache = write_decisions_batch(batch, source, types, open_hashes)
            totals.update(counts)
            decision_cache.update(cache)
            max_cid = max([max_cid, *(p.cl_cluster_id for p in batch)])

        # Pass B — opinions (re-link to cached decision nodes).
        for batch in _batched(_opinions(), batch_size):
            counts = write_opinions_batch(
                batch, source, types, decision_cache, open_hashes
            )
            totals.update(counts)
            max_cid = max([max_cid, *(p.cl_cluster_id for p in batch)])

        run = record_write_run(
            totals=dict(totals), issues=dict(issues),
            last_cluster_id=max_cid or None,
        )

        self.stdout.write(self.style.SUCCESS(f"ingest complete (run #{run.pk}):"))
        self.stdout.write(json.dumps(
            {"totals": dict(totals), "issues": dict(issues)}, indent=2
        ))


def _batched(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
