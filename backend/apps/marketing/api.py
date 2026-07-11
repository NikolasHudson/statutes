"""Public endpoints for the marketing site (``/api/marketing/*``).

Everything here is ``auth=None`` by design: the callers are the static
marketing site's Next.js route handlers (server-side, same-box in dev,
App Platform in prod) and its ISR page builds. Reads are the published
articles; writes are lead capture. Abuse control on the writes is a
honeypot field plus a per-IP fixed-window throttle — deliberately mild,
since a dropped legitimate lead costs more than a junk row.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.audit import client_ip

from .models import Article, ContactSubmission, NewsletterSubscriber

logger = logging.getLogger(__name__)

marketing_router = Router(tags=["marketing"])


# ---------------------------------------------------------------------------
# Abuse control
# ---------------------------------------------------------------------------


def _throttled(request, bucket: str, limit: int, window_s: int) -> bool:
    """Fixed-window per-IP counter on the default cache. Redis in prod,
    locmem in dev — either way `add` + `incr` is atomic enough for a
    marketing form."""
    ip = client_ip(request) or "unknown"
    key = f"mkt:{bucket}:{ip}"
    cache.add(key, 0, window_s)
    try:
        count = cache.incr(key)
    except ValueError:  # key expired between add and incr
        count = 1
    return count > limit


def _clean_email(raw: str) -> str:
    """Normalized (lowercased) address, or a 400 if it isn't one. Django's
    validator, not pydantic's EmailStr — the latter needs an extra package."""
    email = raw.strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        raise HttpError(400, "Enter a valid email address.")
    return email


# ---------------------------------------------------------------------------
# Contact form
# ---------------------------------------------------------------------------


class ContactIn(Schema):
    name: str
    email: str
    message: str
    organization: str = ""
    role: str = ""
    page: str = ""
    # Honeypot — hidden on the real form; bots that fill it get a fake 200.
    website: str = ""


class OkOut(Schema):
    ok: bool = True


@marketing_router.post("/contact", response=OkOut, auth=None)
def submit_contact(request, payload: ContactIn):
    if payload.website:
        return OkOut()  # honeypot hit: pretend success, store nothing
    if _throttled(request, "contact", limit=5, window_s=3600):
        raise HttpError(429, "Too many submissions; please email us instead.")

    name = payload.name.strip()[:200]
    message = payload.message.strip()
    if not name or not message:
        raise HttpError(400, "Name and message are required.")

    submission = ContactSubmission.objects.create(
        name=name,
        email=_clean_email(payload.email),
        organization=payload.organization.strip()[:200],
        role=payload.role.strip()[:200],
        message=message[:10_000],
        page=payload.page.strip()[:200],
        ip=client_ip(request),
    )
    _notify_contact(submission)
    return OkOut()


def _notify_contact(submission: ContactSubmission) -> None:
    """Best-effort email heads-up; the admin row is the durable record."""
    if not settings.CONTACT_NOTIFY_EMAIL:
        return
    body = (
        f"From: {submission.name} <{submission.email}>\n"
        f"Organization: {submission.organization or '—'}\n"
        f"Role: {submission.role or '—'}\n"
        f"Page: {submission.page or '—'}\n\n"
        f"{submission.message}\n\n"
        f"Reply directly to the sender, then mark the submission handled in the admin."
    )
    try:
        send_mail(
            subject=f"[Hudson contact] {submission.name}",
            message=body,
            from_email=settings.CONTACT_FROM_EMAIL,
            recipient_list=[settings.CONTACT_NOTIFY_EMAIL],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 — notification must never fail the API call
        logger.exception("contact notification email failed (submission saved)")


# ---------------------------------------------------------------------------
# Newsletter
# ---------------------------------------------------------------------------


class SubscribeIn(Schema):
    email: str
    website: str = ""  # honeypot


@marketing_router.post("/subscribe", response=OkOut, auth=None)
def subscribe(request, payload: SubscribeIn):
    if payload.website:
        return OkOut()
    if _throttled(request, "subscribe", limit=10, window_s=3600):
        raise HttpError(429, "Too many attempts.")
    NewsletterSubscriber.objects.get_or_create(email=_clean_email(payload.email))
    return OkOut()


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------


class ArticleCard(Schema):
    slug: str
    title: str
    category: str
    excerpt: str
    published_at: str
    read_minutes: int


class ArticleDetail(ArticleCard):
    lede: str
    body_md: str
    tags: list[str]
    author_name: str
    author_title: str


def _card(a: Article) -> dict:
    return {
        "slug": a.slug,
        "title": a.title,
        "category": a.category,
        "excerpt": a.excerpt,
        "published_at": a.published_at.isoformat() if a.published_at else "",
        "read_minutes": a.read_minutes,
    }


@marketing_router.get("/articles", response=list[ArticleCard], auth=None)
def list_articles(request):
    return [_card(a) for a in Article.objects.filter(published=True)]


@marketing_router.get("/articles/{slug}", response=ArticleDetail, auth=None)
def get_article(request, slug: str):
    try:
        a = Article.objects.get(slug=slug, published=True)
    except Article.DoesNotExist:
        raise HttpError(404, "No such article.")
    return {
        **_card(a),
        "lede": a.lede,
        "body_md": a.body_md,
        "tags": list(a.tags or []),
        "author_name": a.author_name,
        "author_title": a.author_title,
    }
