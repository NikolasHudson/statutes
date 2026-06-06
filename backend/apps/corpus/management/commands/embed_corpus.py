"""Run the embedding job for any NodeVersion whose embedding is missing or stale.

    python manage.py embed_corpus
    python manage.py embed_corpus --batch-size 32 --limit 200
    python manage.py embed_corpus --force        # re-embed everything
    # Embed (or re-embed) only the statute + rules corpora, leaving caselaw alone:
    python manage.py embed_corpus --source iowa-code --source iowa-court-rules --force

Without ``VOYAGE_API_KEY`` the deterministic FakeEmbeddingClient is used —
fine for local search testing, useless for retrieval quality.

Use ``--force`` after switching embedding models (or after first setting
VOYAGE_API_KEY when prior runs used the fake client) to invalidate every
row's embedding_source_hash so the job re-embeds from scratch.

Pass ``--source`` (repeatable) to scope both the embedding job and the
``--force`` invalidation to specific sources. Caselaw is unembedded by design
and is ~110k versions, so a plain (unscoped) run will sweep it in — use
``--source`` to avoid that."""

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
                "Invalidate existing embeddings before running (scoped by "
                "--source if given). Use after changing embedding models."
            ),
        )
        parser.add_argument(
            "--source",
            action="append",
            dest="sources",
            default=None,
            metavar="SLUG",
            help=(
                "Restrict to a Source by slug (repeatable), e.g. "
                "--source iowa-code --source iowa-court-rules. Without it, "
                "all sources are eligible — including ~110k caselaw versions."
            ),
        )

    def handle(self, *args, **opts):
        source_slugs = opts["sources"]
        if opts["force"]:
            qs = NodeVersion.objects.all()
            if source_slugs:
                qs = qs.filter(node__source__slug__in=source_slugs)
            n = qs.update(embedding_source_hash="")
            scope = f" for {', '.join(source_slugs)}" if source_slugs else ""
            self.stdout.write(self.style.WARNING(f"Invalidated {n} embeddings{scope}"))

        result = run_embedding_job(
            batch_size=opts["batch_size"],
            limit=opts["limit"],
            source_slugs=source_slugs,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Embedded {result.embedded} | failed {result.failed}"
            )
        )
