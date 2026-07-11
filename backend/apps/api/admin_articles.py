"""Staff-only article management API for the admin SPA (/admin/articles).

Third member of the admin surface, on the same posture as
:mod:`apps.api.admin_usage` and :mod:`apps.api.admin_users`:
:class:`StaffSessionAuth` on the router (session cookie + ``is_staff``, with
the CSRF token enforced on every unsafe method).

The rows are ``marketing.Article`` — the source of truth the public marketing
site renders from (see apps/marketing). Two authoring paths write here:
markdown files synced by ``import_articles`` (``source_path`` set) and this
API (``source_path`` blank). Editing an md-sourced article is allowed — the
DB is what the site serves — but the next ``import_articles`` run will
overwrite those edits from the file, so the UI shows a warning on such rows.

Unlike user management there is no superuser fence and no audit trail:
articles are public content, not account state.
"""

from __future__ import annotations

import datetime as dt
import re

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.api.admin_usage import StaffSessionAuth
from apps.marketing.models import Article

admin_articles_router = Router(auth=StaffSessionAuth())

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AdminArticleRow(Schema):
    id: int
    slug: str
    title: str
    category: str
    published: bool
    published_at: dt.date | None
    read_minutes: int
    updated_at: dt.datetime
    # Non-empty = row is synced from a markdown file; admin edits survive
    # only until the next import_articles run.
    source_path: str


class AdminArticleDetail(AdminArticleRow):
    lede: str
    excerpt: str
    body_md: str
    tags: list[str]
    author_name: str
    author_title: str


class AdminArticleIn(Schema):
    title: str
    slug: str = ""  # blank = derive from the title
    category: str = ""
    lede: str = ""
    excerpt: str = ""
    body_md: str = ""
    tags: list[str] = []
    author_name: str = ""  # blank = model defaults
    author_title: str = ""
    published: bool = False
    published_at: dt.date | None = None
    read_minutes: int = 0  # 0 = auto-compute from word count


class AdminArticlePatch(Schema):
    """All optional — the client sends only what changes."""

    title: str | None = None
    slug: str | None = None
    category: str | None = None
    lede: str | None = None
    excerpt: str | None = None
    body_md: str | None = None
    tags: list[str] | None = None
    author_name: str | None = None
    author_title: str | None = None
    published: bool | None = None
    published_at: dt.date | None = None
    read_minutes: int | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_article(article_id: int) -> Article:
    try:
        return Article.objects.get(pk=article_id)
    except Article.DoesNotExist as exc:
        raise HttpError(404, "article not found") from exc


def _clean_slug(raw: str, *, exclude_pk: int | None = None) -> str:
    slug = raw.strip().lower()
    if not _SLUG_RE.fullmatch(slug):
        raise HttpError(
            400, "slug must be lowercase letters, digits and hyphens (a-b-c)"
        )
    clash = Article.objects.filter(slug=slug)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise HttpError(400, f"an article with slug {slug!r} already exists")
    return slug


def _slug_from_title(title: str) -> str:
    from django.utils.text import slugify

    base = slugify(title)[:190] or "article"
    slug = base
    n = 2
    while Article.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _detail(a: Article) -> AdminArticleDetail:
    return AdminArticleDetail(
        id=a.id,
        slug=a.slug,
        title=a.title,
        category=a.category,
        published=a.published,
        published_at=a.published_at,
        read_minutes=a.read_minutes,
        updated_at=a.updated_at,
        source_path=a.source_path,
        lede=a.lede,
        excerpt=a.excerpt,
        body_md=a.body_md,
        tags=list(a.tags or []),
        author_name=a.author_name,
        author_title=a.author_title,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@admin_articles_router.get("", response=list[AdminArticleRow])
def list_articles(request):
    """Every article, drafts included (the public endpoint filters to
    published; this surface exists to manage the rest)."""
    return [
        AdminArticleRow(
            id=a.id,
            slug=a.slug,
            title=a.title,
            category=a.category,
            published=a.published,
            published_at=a.published_at,
            read_minutes=a.read_minutes,
            updated_at=a.updated_at,
            source_path=a.source_path,
        )
        for a in Article.objects.all()
    ]


@admin_articles_router.get("/{article_id}", response=AdminArticleDetail)
def article_detail(request, article_id: int):
    return _detail(_get_article(article_id))


@admin_articles_router.post("", response=AdminArticleDetail)
def create_article(request, payload: AdminArticleIn):
    title = payload.title.strip()
    if not title:
        raise HttpError(400, "title is required")
    slug = (
        _clean_slug(payload.slug)
        if payload.slug.strip()
        else _slug_from_title(title)
    )
    if payload.published and not payload.published_at:
        raise HttpError(400, "a published article needs a publication date")

    article = Article(
        slug=slug,
        title=title,
        category=payload.category.strip(),
        lede=payload.lede.strip(),
        excerpt=payload.excerpt.strip(),
        body_md=payload.body_md,
        tags=[t.strip() for t in payload.tags if t.strip()],
        published=payload.published,
        published_at=payload.published_at,
        read_minutes=max(0, payload.read_minutes),
    )
    if payload.author_name.strip():
        article.author_name = payload.author_name.strip()
    if payload.author_title.strip():
        article.author_title = payload.author_title.strip()
    article.save()
    return _detail(article)


@admin_articles_router.patch("/{article_id}", response=AdminArticleDetail)
def update_article(request, article_id: int, payload: AdminArticlePatch):
    article = _get_article(article_id)
    data = payload.model_dump(exclude_unset=True)

    if "slug" in data:
        article.slug = _clean_slug(data["slug"] or "", exclude_pk=article.pk)
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise HttpError(400, "title cannot be blank")
        article.title = title
    for field in ("category", "lede", "excerpt", "author_name", "author_title"):
        if field in data:
            setattr(article, field, (data[field] or "").strip())
    if "body_md" in data:
        article.body_md = data["body_md"] or ""
        if "read_minutes" not in data:
            article.read_minutes = 0  # body changed → recompute on save
    if "tags" in data:
        article.tags = [t.strip() for t in (data["tags"] or []) if t.strip()]
    if "published" in data:
        article.published = bool(data["published"])
    if "published_at" in data:
        article.published_at = data["published_at"]
    if "read_minutes" in data and data["read_minutes"] is not None:
        article.read_minutes = max(0, int(data["read_minutes"]))

    if article.published and not article.published_at:
        raise HttpError(400, "a published article needs a publication date")

    article.save()
    return _detail(article)


@admin_articles_router.delete("/{article_id}", response=dict)
def delete_article(request, article_id: int):
    article = _get_article(article_id)
    if article.source_path:
        # An md-sourced row would just reappear on the next import; the file
        # is the thing to delete (then the row, once the file is gone).
        raise HttpError(
            400,
            "this article is synced from a markdown file "
            f"({article.source_path}); remove the file first, then delete here",
        )
    article.delete()
    return {"status": "deleted", "id": article_id}
