"""Chunk caselaw NodeVersions into NodeChunk rows (no embeddings yet).

    # Chunk the first 100 cases and eyeball boundaries:
    python manage.py chunk_caselaw --limit 100
    # Chunk the WHOLE source (streams in batches, skips already-chunked versions):
    python manage.py chunk_caselaw
    # Sweep parameters over a sample, write nothing:
    python manage.py chunk_caselaw --limit 100 --target-tokens 600 --dry-run
    # Re-chunk everything from scratch (e.g. after changing target/overlap):
    python manage.py chunk_caselaw --rechunk

``--limit`` counts *cases* (decision nodes); every current opinion under them
(plus any decision head-matter version) is chunked. Omit it to do the whole
source. The job streams decisions in batches so memory stays bounded over the
full ~111k-version corpus, and it is **resumable**: by default a version that
already has chunks is skipped (so a re-run continues where a crash left off and
preserves any embeddings already computed). Pass ``--rechunk`` to force
delete-and-rebuild when chunk parameters change.

Token counts use the real voyage-law-2 tokenizer (local, no API call). This
command only writes NodeChunk text/offsets/hashes — embeddings come later via
``embed_chunks``, so it is free to run.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.corpus.models import Node, NodeChunk, NodeVersion, Source
from apps.corpus.services.chunking import (
    DEFAULT_OVERLAP_TOKENS,
    DEFAULT_TARGET_TOKENS,
    build_chunks,
    voyage_token_counter,
)


class _Agg:
    """Running aggregate so we never hold the whole corpus in memory."""

    def __init__(self):
        self.n_versions = 0
        self.n_chunks = 0
        self.tok_sum = 0
        self.tok_min = None
        self.tok_max = 0
        self.cpv_min = None
        self.cpv_max = 0
        self.over_cap = 0

    def add(self, chunks):
        toks = [c.token_count for c in chunks]
        self.n_versions += 1
        self.n_chunks += len(chunks)
        self.tok_sum += sum(toks)
        lo, hi = min(toks), max(toks)
        self.tok_min = lo if self.tok_min is None else min(self.tok_min, lo)
        self.tok_max = max(self.tok_max, hi)
        self.cpv_min = len(chunks) if self.cpv_min is None else min(self.cpv_min, len(chunks))
        self.cpv_max = max(self.cpv_max, len(chunks))
        self.over_cap += sum(1 for t in toks if t > 16000)


class Command(BaseCommand):
    help = "Chunk caselaw NodeVersions into NodeChunk rows for passage retrieval."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="iowa-caselaw", metavar="SLUG")
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Number of cases (decisions) to chunk. Omit for the whole source.",
        )
        parser.add_argument(
            "--batch-cases", type=int, default=2000,
            help="Decisions processed (and committed) per batch.",
        )
        parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
        parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
        parser.add_argument(
            "--rechunk", action="store_true",
            help="Delete and rebuild chunks even for versions already chunked.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Compute and report, but write nothing."
        )
        parser.add_argument(
            "--show", type=int, default=3,
            help="Print sample chunks for this many versions (from the first batch).",
        )

    def handle(self, *args, **opts):
        try:
            source = Source.objects.get(slug=opts["source"])
        except Source.DoesNotExist:
            raise CommandError(f"No Source with slug {opts['source']!r}")

        decision_ids = list(
            Node.objects.filter(source=source, parent__isnull=True)
            .order_by("id")
            .values_list("id", flat=True)
        )
        if opts["limit"] is not None:
            decision_ids = decision_ids[: opts["limit"]]
        if not decision_ids:
            raise CommandError(f"No decisions found for source {source.slug!r}")

        count_tokens = voyage_token_counter()
        target, overlap = opts["target_tokens"], opts["overlap_tokens"]
        rechunk, dry, show = opts["rechunk"], opts["dry_run"], opts["show"]
        batch_cases = max(1, opts["batch_cases"])
        n_batches = (len(decision_ids) + batch_cases - 1) // batch_cases

        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(
            f"chunk_caselaw [{source.slug}] — {len(decision_ids):,} cases, "
            f"{n_batches} batch(es), target={target}/overlap={overlap}, "
            f"{'rechunk' if rechunk else 'skip-existing'}"
            f"{' (DRY RUN)' if dry else ''}"
        ))

        agg = _Agg()
        sample: list[tuple[NodeVersion, list[NodeChunk]]] = []
        skipped = 0

        for bi in range(n_batches):
            batch_dids = decision_ids[bi * batch_cases : (bi + 1) * batch_cases]
            versions = list(
                NodeVersion.objects.filter(effective_to__isnull=True)
                .filter(Q(node_id__in=batch_dids) | Q(node__parent_id__in=batch_dids))
                .select_related("node", "node__parent")
            )
            if not rechunk and versions:
                have = set(
                    NodeChunk.objects.filter(version_id__in=[v.id for v in versions])
                    .values_list("version_id", flat=True).distinct()
                )
                skipped += len(have)
                versions = [v for v in versions if v.id not in have]

            batch_chunks: list[NodeChunk] = []
            for v in versions:
                chunks = build_chunks(
                    v, count_tokens=count_tokens, target_tokens=target, overlap_tokens=overlap
                )
                if not chunks:
                    continue
                batch_chunks.extend(chunks)
                agg.add(chunks)
                if len(sample) < show:
                    sample.append((v, chunks))

            if not dry and batch_chunks:
                with transaction.atomic():
                    if rechunk:
                        NodeChunk.objects.filter(
                            version_id__in=[v.id for v in versions]
                        ).delete()
                    NodeChunk.objects.bulk_create(batch_chunks, batch_size=1000)

            w(f"  batch {bi + 1}/{n_batches}: +{len(versions)} versions, "
              f"+{len(batch_chunks)} chunks  (running: {agg.n_versions:,} v / "
              f"{agg.n_chunks:,} c{f', {skipped:,} skipped' if skipped else ''})")

        self._report(agg=agg, sample=sample, target=target, dry_run=dry,
                     show=show, skipped=skipped)

    # -- reporting -----------------------------------------------------------

    def _report(self, *, agg, sample, target, dry_run, show, skipped):
        w = self.stdout.write
        cavg = round(agg.n_chunks / agg.n_versions, 1) if agg.n_versions else 0
        tavg = round(agg.tok_sum / agg.n_chunks, 1) if agg.n_chunks else 0
        mode = (self.style.WARNING("DRY RUN — nothing written")
                if dry_run else self.style.SUCCESS("written"))
        w("")
        w(self.style.MIGRATE_HEADING(f"done — {mode}"))
        w(f"  versions chunked: {agg.n_versions:,}"
          + (f"   ({skipped:,} already chunked, skipped)" if skipped else ""))
        w(f"  chunks          : {agg.n_chunks:,}")
        w(f"  chunks/version  : min {agg.cpv_min or 0} · avg {cavg} · max {agg.cpv_max}")
        w(f"  tokens/chunk    : min {agg.tok_min or 0} · avg {tavg} · max {agg.tok_max}")
        w(f"  over 16k cap    : {agg.over_cap} chunks (would be truncated by voyage)")
        w(f"  total tokens    : {agg.tok_sum:,}")
        w(f"  est. embed cost : ${agg.tok_sum / 1_000_000 * 0.12:,.2f} @ $0.12/1M (voyage-law-2)")

        if show and sample:
            w("")
            w(self.style.MIGRATE_HEADING(f"sample — {len(sample)} version(s)"))
            for v, chunks in sample:
                w("")
                w(self.style.HTTP_INFO(f"  {v.node.path}  ({len(chunks)} chunks)"))
                w(f"  header: {chunks[0].context_header}")
                for c in chunks:
                    head = _oneline(c.body_text[:140])
                    span = f"[{c.char_start}:{c.char_end}]"
                    w(f"    #{c.ordinal} {c.token_count:>4}tok {span:>14}  {head}")


def _oneline(text: str) -> str:
    return " ".join(text.split())
