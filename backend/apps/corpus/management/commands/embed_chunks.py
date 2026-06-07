"""Embed pending NodeChunks (passage-level caselaw vectors).

    python manage.py embed_chunks
    python manage.py embed_chunks --batch-size 64 --limit 1000
    python manage.py embed_chunks --source iowa-caselaw --force   # re-embed from scratch

Counterpart to ``embed_corpus`` (which embeds whole NodeVersions for
statutes/rules). Chunks must already exist — run ``chunk_caselaw`` first.

Without ``VOYAGE_API_KEY`` the deterministic FakeEmbeddingClient is used, which
is fine for plumbing but useless for retrieval quality. Use ``--force`` to
invalidate ``embedding_source_hash`` and re-embed (e.g. after a model swap or a
re-chunk with different parameters)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.corpus.models import NodeChunk
from apps.corpus.services.embeddings import run_chunk_embedding_job


class Command(BaseCommand):
    help = "Embed pending NodeChunks via the configured embedding client."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=64)
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of chunks to embed in this run.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Invalidate existing chunk embeddings before running (scoped by --source).",
        )
        parser.add_argument(
            "--source",
            action="append",
            dest="sources",
            default=None,
            metavar="SLUG",
            help="Restrict to chunks under a Source by slug (repeatable).",
        )
        parser.add_argument(
            "--num-shards", type=int, default=None,
            help="Split pending chunks into this many id-residue slices for parallel runs.",
        )
        parser.add_argument(
            "--shard", type=int, default=None,
            help="Which slice (0..num_shards-1) this worker handles. Requires --num-shards.",
        )

    def handle(self, *args, **opts):
        source_slugs = opts["sources"]
        shard, num_shards = opts["shard"], opts["num_shards"]
        if opts["force"]:
            qs = NodeChunk.objects.all()
            if source_slugs:
                qs = qs.filter(version__node__source__slug__in=source_slugs)
            n = qs.update(embedding_source_hash="")
            scope = f" for {', '.join(source_slugs)}" if source_slugs else ""
            self.stdout.write(self.style.WARNING(f"Invalidated {n} chunk embeddings{scope}"))

        result = run_chunk_embedding_job(
            batch_size=opts["batch_size"],
            limit=opts["limit"],
            source_slugs=source_slugs,
            shard=shard,
            num_shards=num_shards,
        )
        tag = f" [shard {shard}/{num_shards}]" if num_shards else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Embedded {result.embedded} chunks | failed {result.failed}{tag}"
            )
        )
