"""Public endpoints for the marketing site (``/api/marketing/*``).

Everything here is ``auth=None`` by design: the callers are the static
marketing site's Next.js route handlers (server-side, same-box in dev,
App Platform in prod) and its ISR page builds. Reads are the published
articles; writes are lead capture. Abuse control on the writes is a
honeypot field plus a per-IP fixed-window throttle — deliberately mild,
since a dropped legitimate lead costs more than a junk row.

That last sentence is the whole design, and the code contradicted it until
2026-07: the throttle raised its 429 *before* the ``ContactSubmission`` insert,
so an over-limit lead was destroyed outright — no row, no email, no retry — and
it did so on a key that (because the marketing site proxies server-side, from one
container) was shared by the entire internet. See the abuse-control block below.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.audit import client_ip

from .models import Article, ContactSubmission, NewsletterSubscriber

logger = logging.getLogger(__name__)

marketing_router = Router(tags=["marketing"])


# ---------------------------------------------------------------------------
# Abuse control
#
# Two thresholds on one per-IP counter, because a contact form has two things
# worth protecting and they are not the same thing:
#
#   * NOTIFY — past this, the lead is still stored, but the heads-up email is
#     suppressed. Flooding must not turn our own inbox into the denial of
#     service, and an email is the part that is cheap to lose: the admin row is
#     the durable record and it is still there.
#   * STORE — past this, the write itself is refused (429). This is the only
#     hard stop left, it exists to bound the table rather than to police the
#     funnel, and so it sits an order of magnitude above any plausible human.
#     Nobody types 50 distinct messages into a contact form in an hour; the
#     honeypot has already taken the bots that don't render JS.
#
# The old single threshold of 5 was not "mild", it was a cap on the company's
# entire lead funnel: ``client_ip`` used to return the left-most X-Forwarded-For
# entry, so every submission proxied through the marketing container shared the
# key ``mkt:contact:<that container's egress IP>``. Prod has no REDIS_URL, so the
# cache is LocMem per gunicorn worker — five leads an hour, site-wide, in the
# worst case, and non-deterministic. Both halves of that are fixed: the key is a
# real client (apps.accounts.audit.client_ip, MARKETING_PROXY_TOKEN) and the
# limits are what a person, not a proxy, would have to exceed.
# ---------------------------------------------------------------------------

_CONTACT_NOTIFY_LIMIT = 5
_CONTACT_STORE_LIMIT = 50
_CONTACT_WINDOW_S = 3600
# The newsletter form is different in kind, so it keeps the plain block: the write
# is a ``get_or_create`` on an address, a resubmission is a no-op, and a rejected
# attempt costs the reader one click — there is no unrecoverable message to lose.
_SUBSCRIBE_LIMIT = 10
_SUBSCRIBE_WINDOW_S = 3600


def _hits(request, bucket: str, window_s: int) -> int:
    """Count this request in a fixed per-IP window and return the running total.
    Redis in prod, locmem in dev — either way `add` + `incr` is atomic enough for
    a marketing form."""
    ip = client_ip(request) or "unknown"
    key = f"mkt:{bucket}:{ip}"
    cache.add(key, 0, window_s)
    try:
        return cache.incr(key)
    except ValueError:  # key expired between add and incr
        return 1


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

    name = payload.name.strip()[:200]
    message = payload.message.strip()
    if not name or not message:
        raise HttpError(400, "Name and message are required.")
    email = _clean_email(payload.email)

    # Counted once, after validation (a 400 is not a lead) and before the write,
    # so the count is the number of leads this client has actually filed.
    hits = _hits(request, "contact", _CONTACT_WINDOW_S)
    if hits > _CONTACT_STORE_LIMIT:
        raise HttpError(429, "Too many submissions; please email us instead.")

    submission = ContactSubmission.objects.create(
        name=name,
        email=email,
        organization=payload.organization.strip()[:200],
        role=payload.role.strip()[:200],
        message=message[:10_000],
        page=payload.page.strip()[:200],
        ip=client_ip(request),
    )
    if hits > _CONTACT_NOTIFY_LIMIT:
        # The lead is safe in the admin; only the heads-up is dropped. Logged,
        # because a suppressed notification is exactly the case where someone
        # will later swear they submitted the form and we never replied.
        logger.warning(
            "contact notification suppressed (throttled): submission=%s hits=%s",
            submission.pk,
            hits,
        )
        return OkOut()
    _notify_contact(submission)
    return OkOut()


def _notify_contact(submission: ContactSubmission) -> None:
    """Email heads-up. The admin row is the durable record, so nothing here may
    fail the request — but nothing here may be quiet, either. The visitor is
    shown a thank-you regardless, so an unlogged failure is a lead that exists
    and that nobody on the team knows about. The live failure mode is mundane:
    Postmark rejects a ``CONTACT_FROM_EMAIL`` it hasn't verified for the sending
    domain, which is precisely what a mail-domain move produces."""
    if not settings.CONTACT_NOTIFY_EMAIL:
        logger.warning(
            "contact submission %s stored, but CONTACT_NOTIFY_EMAIL is unset — "
            "no one was notified; the row is in the admin",
            submission.pk,
        )
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
        # ERROR + traceback: the submission IS saved, so this is not data loss —
        # it is a lead sitting unread behind a green checkmark.
        logger.exception(
            "contact notification email FAILED: submission=%s from=%s to=%s "
            "(the submission is saved; read it in the admin)",
            submission.pk,
            settings.CONTACT_FROM_EMAIL,
            settings.CONTACT_NOTIFY_EMAIL,
        )


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
    if _hits(request, "subscribe", _SUBSCRIBE_WINDOW_S) > _SUBSCRIBE_LIMIT:
        raise HttpError(429, "Too many attempts.")
    NewsletterSubscriber.objects.get_or_create(email=_clean_email(payload.email))
    return OkOut()


class UnsubscribeIn(Schema):
    token: str


@marketing_router.post("/unsubscribe", response=OkOut, auth=None)
def unsubscribe(request, payload: UnsubscribeIn):
    """One-click opt-out from a signed token in the unsubscribe link. Always
    answers 200 (idempotent, and never an oracle for whether an address is on
    the list); a bad/forged token simply changes nothing."""
    email = NewsletterSubscriber.email_from_unsubscribe_token(payload.token)
    if email:
        NewsletterSubscriber.objects.filter(
            email=email, unsubscribed_at__isnull=True
        ).update(unsubscribed_at=timezone.now())
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
