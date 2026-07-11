"""Sync ``content/articles/*.md`` into the ``marketing.Article`` table.

Markdown files with YAML frontmatter are the canonical authoring format for
articles — reviewable in git, deployed like code. This command upserts them
by slug, so it is safe to run on every deploy (or by hand after adding a
file). Articles created directly in the Django admin (no ``source_path``)
are never touched.

Frontmatter keys: title (required), slug (defaults to the filename),
category, lede, excerpt, tags, date (-> published_at), read_minutes,
author_name, author_title, published (default true).

Usage::

    python manage.py import_articles            # sync content/articles/
    python manage.py import_articles --dir path # sync another directory
"""

from __future__ import annotations

from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.marketing.models import Article


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). The file must open with a ``---``
    fence; everything after the closing fence is the markdown body."""
    if not text.startswith("---"):
        raise ValueError("missing frontmatter (file must start with ---)")
    try:
        _, fm, body = text.split("---", 2)
    except ValueError as exc:
        raise ValueError("unterminated frontmatter fence") from exc
    meta = yaml.safe_load(fm) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a mapping")
    return meta, body.strip() + "\n"


class Command(BaseCommand):
    help = "Upsert marketing articles from markdown files (idempotent by slug)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default=str(Path(settings.BASE_DIR) / "content" / "articles"),
            help="Directory of .md files (default: content/articles/).",
        )

    def handle(self, *args, **options):
        directory = Path(options["dir"])
        if not directory.is_dir():
            raise CommandError(f"not a directory: {directory}")

        created = updated = 0
        for path in sorted(directory.glob("*.md")):
            try:
                meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise CommandError(f"{path.name}: {exc}") from exc
            if "title" not in meta:
                raise CommandError(f"{path.name}: frontmatter needs a title")

            slug = str(meta.get("slug") or path.stem)
            date = meta.get("date")  # yaml parses ISO dates to datetime.date
            base = Path(settings.BASE_DIR)
            source = (
                str(path.relative_to(base)) if path.is_relative_to(base) else str(path)
            )
            fields = {
                "title": str(meta["title"]),
                "category": str(meta.get("category", "")),
                "lede": str(meta.get("lede", "")),
                "excerpt": str(meta.get("excerpt", "")),
                "body_md": body,
                "tags": [str(t) for t in (meta.get("tags") or [])],
                "published": bool(meta.get("published", True)),
                "published_at": date,
                "read_minutes": int(meta.get("read_minutes", 0)),
                "source_path": source,
            }
            for key in ("author_name", "author_title"):
                if meta.get(key):
                    fields[key] = str(meta[key])

            # read_minutes=0 in frontmatter means "recompute": Article.save()
            # fills it from the word count before the row is written.
            _, was_created = Article.objects.update_or_create(
                slug=slug, defaults=fields
            )
            created += was_created
            updated += not was_created
            self.stdout.write(f"  {'created' if was_created else 'updated'}  {slug}")

        self.stdout.write(
            self.style.SUCCESS(f"import_articles: {created} created, {updated} updated")
        )
