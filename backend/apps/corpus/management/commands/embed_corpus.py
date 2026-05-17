"""Run the embedding job for any NodeVersion whose embedding is missing or stale.

    python manage.py embed_corpus
    python manage.py embed_corpus --batch-size 32 --limit 200
    python manage.py embed_corpus --force        # re-embed everything

Without ``VOYAGE_API_KEY`` the deterministic FakeEmbeddingClient is used —
fine for local search testing, useless for retrieval quality.

Use ``--force`` after switching embedding models (or after first setting
VOYAGE_API_KEY when prior runs used the fake client) to invalidate every
row's embedding_source_hash so the job re-embeds from scratch."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.corpus.models import NodeVersion
from apps.corpus.services.embeddings import run_embedding_job


class Command(BaseCommand):
    help = "Embed pending NodeVersions via the configured embedding client."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=64)
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of NodeVersions to embed in this run.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Invalidate every existing embedding before running. Use "
                "after changing embedding models."
            ),
        )

    def handle(self, *args, **opts):
        if opts["force"]:
            n = NodeVersion.objects.update(embedding_source_hash="")
            self.stdout.write(self.style.WARNING(f"Invalidated {n} embeddings"))

        result = run_embedding_job(
            batch_size=opts["batch_size"], limit=opts["limit"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Embedded {result.embedded} | failed {result.failed}"
            )
        )
