"""The email-assistant worker pipeline: gates → thread → chat turn → reply.

Mirrors the web chat view's wrapper stack around ``run_chat_turn`` (which does
none of this itself — its docstring makes auth/quota/trace the caller's job):

  web view:  session auth → product scope/entitlement → quota → turn → trace
  here:      SPF/DKIM + loop guards → sender→User → allowlist/entitlement
             → quota + per-sender cap → turn (verification gate inside)
             → trace → rendered reply

Silent-vs-notice policy: anything that suggests the mail wasn't a legitimate,
entitled human (failed auth, unknown sender, auto-generated, over the sender
cap) is dropped SILENTLY — replying confirms a live address, creates
backscatter, and feeds mail loops. Notices go only to authenticated,
registered users hitting a legitimate wall (quota, entitlement), and at most
one per sender per day.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import timedelta
from email.utils import make_msgid
from types import SimpleNamespace

from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from ninja.errors import HttpError

from apps.accounts.models import User
from apps.api.chat import (
    ALLOWED_CHAT_MODELS,
    DEFAULT_CHAT_MODEL,
    ChatTurnError,
    _enforce_chat_quota,
    run_chat_turn,
)
from apps.api.trace_capture import record_chat_trace
from apps.api.usage import FEATURE_CHAT, FEATURE_EMAIL, collect_usage
from apps.tenancy.entitlement import is_entitled
from apps.tenancy.services import has_paid_access
from django.conf import settings as django_settings

from . import render
from .models import AssistantAddress, EmailThread, InboundEmail, OutboundEmail

logger = logging.getLogger(__name__)

# One exchange = 2 entries; 20 keeps roughly ten turns of context and bounds
# the replayed token cost per reply.
MAX_THREAD_HISTORY = 20
# An email body beyond this is almost certainly a pasted document, which the
# email surface doesn't support yet (Verify Document does, on the web app).
MAX_BODY_CHARS = 20_000
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 300


def claim_pending(batch: int = 10) -> list[InboundEmail]:
    """Atomically claim up to ``batch`` due rows. skip_locked makes a second
    worker instance safe: two workers never claim the same row."""
    now = timezone.now()
    with transaction.atomic():
        rows = list(
            InboundEmail.objects.select_for_update(skip_locked=True)
            .filter(status=InboundEmail.Status.PENDING, next_attempt_at__lte=now)
            .order_by("created_at")[:batch]
        )
        for row in rows:
            row.status = InboundEmail.Status.PROCESSING
            row.attempts += 1
        if rows:
            InboundEmail.objects.bulk_update(rows, ["status", "attempts"])
    return rows


def process_inbound(inbound: InboundEmail) -> None:
    """Run one claimed inbound message through the full pipeline. Never
    raises: every outcome lands in ``inbound.status`` so the worker loop and
    the admin can see what happened."""
    try:
        _process(inbound)
    except Exception:  # noqa: BLE001 — one poison message must not kill the worker
        logger.exception("unhandled failure processing inbound %s", inbound.pk)
        _finish(inbound, InboundEmail.Status.FAILED, "unhandled exception")


def _process(inbound: InboundEmail) -> None:
    address = inbound.address
    if address is None or not address.active:
        _finish(inbound, InboundEmail.Status.IGNORED, "no active assistant address")
        return

    # -- Trust gates (silent drops) ----------------------------------------
    if inbound.is_auto_generated:
        _finish(inbound, InboundEmail.Status.IGNORED, "auto-generated mail")
        return
    if django_settings.EMAIL_REQUIRE_SENDER_AUTH and not (
        inbound.spf_pass or inbound.dkim_pass
    ):
        # A spoofed From must never receive an answer meant for the real
        # owner of that mailbox. Unknown (None/None) fails closed.
        _finish(inbound, InboundEmail.Status.IGNORED, "sender failed SPF/DKIM")
        return
    if inbound.spam_score is not None and inbound.spam_score >= 5.0:
        _finish(inbound, InboundEmail.Status.IGNORED, "spam score")
        return

    user = User.objects.filter(email__iexact=inbound.from_email).first()
    if user is None or not user.is_active:
        _finish(inbound, InboundEmail.Status.IGNORED, "no registered user")
        return

    if address.mode == AssistantAddress.Mode.ALLOWLIST:
        if not address.allowlist.filter(email=inbound.from_email.lower()).exists():
            _finish(inbound, InboundEmail.Status.IGNORED, "not on allowlist")
            return

    # -- Legitimate-user gates (may notify, once per sender per day) --------
    if address.product is not None and not is_entitled(user, address.product):
        _notify_once(
            inbound,
            address,
            user,
            "no-access",
            f"Your account doesn't have access to {address.product.name}. "
            "If it's provided by your bar association or firm, register with "
            "that email address; otherwise contact "
            f"{address.product.support_email or 'support'}.",
        )
        _finish(inbound, InboundEmail.Status.REJECTED, "not entitled")
        return

    # No free tier (BILLING_REQUIRE_PAID): the assistant spends LLM budget, so
    # a sender whose account holds no live plan gets one polite pointer at the
    # billing page instead of an answer.
    if not has_paid_access(user):
        _notify_once(
            inbound,
            address,
            user,
            "no-subscription",
            "Your account doesn't have an active plan, so the email assistant "
            "can't answer. Start your free trial or manage your subscription "
            "under Account → Billing in the app.",
        )
        _finish(inbound, InboundEmail.Status.REJECTED, "no active plan")
        return

    answered_today = InboundEmail.objects.filter(
        address=address,
        from_email=inbound.from_email,
        created_at__date=timezone.localdate(),
        status=InboundEmail.Status.ANSWERED,
    ).count()
    if answered_today >= address.max_daily_per_sender:
        # Silent: past this point "one more notice" is itself loop fuel.
        _finish(inbound, InboundEmail.Status.IGNORED, "per-sender daily cap")
        return

    try:
        _enforce_chat_quota(user)
    except HttpError as exc:
        _notify_once(inbound, address, user, "quota", str(exc.message))
        _finish(inbound, InboundEmail.Status.REJECTED, "chat quota")
        return

    # -- Thread + body -------------------------------------------------------
    thread = _resolve_thread(inbound, address, user)

    # STOP is judged on the stripped text: it's a bare reply action, and a
    # quoted chain containing the word STOP must not trip it.
    if (inbound.body_text or "").strip().upper() == "STOP":
        if thread.pk:
            thread.status = EmailThread.Status.SUPPRESSED
            thread.save(update_fields=["status", "last_activity"])
        _finish(inbound, InboundEmail.Status.IGNORED, "sender opted out")
        return
    if thread.status != EmailThread.Status.OPEN:
        _finish(inbound, InboundEmail.Status.IGNORED, f"thread {thread.status}")
        return

    body = _turn_body(inbound, thread_is_new=thread.pk is None)
    if not body:
        _finish(inbound, InboundEmail.Status.IGNORED, "empty body")
        return

    if thread.pk is None:
        thread.save()

    inbound.thread = thread
    inbound.save(update_fields=["thread"])

    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS]

    messages = list(thread.messages or [])[-MAX_THREAD_HISTORY:]
    messages.append({"role": "user", "content": body})

    # -- The turn ------------------------------------------------------------
    product = address.product
    source_slug = None
    if product is not None and product.allowed_source_slugs:
        # Same clamp as chat._enforce_product_scope: a scoped address can
        # never search outside its product's sources.
        source_slug = product.allowed_source_slugs[0]
    model = address.model if address.model in ALLOWED_CHAT_MODELS else DEFAULT_CHAT_MODEL

    trace: list = []
    started = time.monotonic()
    try:
        # Same loop as the web chat, so the loop emits feature="chat";
        # relabel on flush so the dashboard books this under email.
        with collect_usage(user, relabel={FEATURE_CHAT: FEATURE_EMAIL}):
            content, actual_model = run_chat_turn(
                messages=messages,
                source_slug=source_slug,
                model=model,
                api_key=django_settings.OPENAI_API_KEY,
                trace=trace,
            )
    except ChatTurnError as exc:
        _record_trace(user, messages, source_slug, "", trace, model,
                      started, error=exc.client_message)
        if inbound.attempts < MAX_ATTEMPTS:
            inbound.status = InboundEmail.Status.PENDING
            inbound.next_attempt_at = timezone.now() + timedelta(
                seconds=RETRY_BACKOFF_SECONDS * inbound.attempts
            )
            inbound.save(update_fields=["status", "next_attempt_at"])
            logger.warning(
                "inbound %s turn failed (attempt %s), retrying: %s",
                inbound.pk, inbound.attempts, exc.client_message,
            )
            return
        _send_reply(
            inbound, address, thread, user,
            "I wasn't able to complete the research for this question due to a "
            "temporary problem on my side. Please try sending it again later, "
            "or use the web app.",
        )
        _finish(inbound, InboundEmail.Status.FAILED, exc.client_message[:200])
        return

    _record_trace(user, messages, source_slug, content, trace, actual_model, started)

    # -- Reply + persist state ------------------------------------------------
    # Official PDFs attach only when the sender EXPRESSLY asked ("send me the
    # pdf of § 714.16") — links are always offered, attachments are opt-in.
    attachments = (
        render.official_pdf_attachments(body) if render.wants_pdf(body) else []
    )
    _send_reply(inbound, address, thread, user, content, attachments=attachments)

    # New list, not append: run_chat_turn's caller-visible contract is that
    # `messages` is the turn INPUT; mutating it afterwards would surprise any
    # future caller (and test) still holding the reference.
    thread.messages = [*messages, {"role": "assistant", "content": content}][
        -MAX_THREAD_HISTORY:
    ]
    thread.turn_count += 1
    if not thread.subject and inbound.subject:
        thread.subject = inbound.subject
    thread.save()

    _finish(inbound, InboundEmail.Status.ANSWERED, "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Forward indicators: "Fwd:"/"FW:" subjects and the separator lines Gmail,
# Outlook, and Apple Mail insert above forwarded material.
_FORWARD_RE = re.compile(
    r"(?im)^\s*(?:fwd?|fw)\s*:|-{2,}\s*Forwarded message\s*-{2,}|^Begin forwarded message"
)


def _turn_body(inbound: InboundEmail, *, thread_is_new: bool) -> str:
    """The text handed to the model as this turn's user message.

    Postmark's StrippedTextReply removes everything below a reply/forward
    separator. That's right for a reply inside our thread (our own previous
    answer is quoted there, and it's already in the thread history) — but a
    FORWARDED email is the payload, not noise: an attorney forwarding a
    client's message wants THAT analyzed, and stripping it leaves only their
    one-line cover note. So: new conversations and anything forward-shaped
    get the full body; only in-thread replies get the stripped form."""
    payload = inbound.raw_payload or {}
    stripped = str(payload.get("StrippedTextReply") or "").strip()
    full = str(payload.get("TextBody") or "").strip() or (inbound.body_text or "").strip()
    if thread_is_new:
        return full or stripped
    if _FORWARD_RE.search(inbound.subject or "") or _FORWARD_RE.search(full):
        return full or stripped
    return stripped or full


def _resolve_thread(
    inbound: InboundEmail, address: AssistantAddress, user
) -> EmailThread:
    """Find the conversation this message continues, or build a fresh
    (unsaved) one. Precedence: plus-address token (survives header-mangling
    clients) → In-Reply-To/References against our sent Message-IDs → new.
    A matched thread must belong to the sender — otherwise forwarding a reply
    would splice someone into another user's conversation history."""
    if inbound.mailbox_hash:
        thread = EmailThread.objects.filter(
            token=inbound.mailbox_hash, address=address
        ).first()
        if thread and thread.user_id == user.pk:
            return thread

    ref_ids = {
        rid.strip().strip("<>")
        for rid in (inbound.references or "").split() + [inbound.in_reply_to or ""]
        if rid.strip()
    }
    if ref_ids:
        sent = (
            OutboundEmail.objects.filter(thread__address=address, thread__user=user)
            .order_by("-created_at")
            .values_list("message_id", "thread_id")[:200]
        )
        for message_id, thread_id in sent:
            if message_id.strip("<>") in ref_ids:
                return EmailThread.objects.get(pk=thread_id)

    return EmailThread(
        address=address, user=user, subject=inbound.subject[:500]
    )


def _reply_subject(inbound: InboundEmail, thread: EmailThread) -> str:
    subject = inbound.subject or thread.subject or "Your research question"
    if subject.lower().startswith("re:"):
        return subject
    return f"Re: {subject}"


def _footer_lines(address: AssistantAddress, thread: EmailThread) -> list[str]:
    today = timezone.localdate().isoformat()
    lines = []
    if address.signature:
        lines.append(address.signature)
    lines += [
        f"{address.display_name} <{address.address}>",
        "AI-generated legal research assistance for licensed attorneys - not "
        "legal advice, and not a substitute for your own professional judgment.",
        f"Citations are verified against the corpus as of {today}.",
        f"Reference {thread.token}. Reply to this email to continue the "
        "conversation, or reply STOP to opt out.",
    ]
    if address.disclaimer:
        lines.append(address.disclaimer)
    return lines


def _link_base_url(address: AssistantAddress) -> str:
    """Citation links point at the product's own front door when it has one
    (a scoped app keeps its users on its domain); else the flagship."""
    product = address.product
    if product is not None and product.hostname:
        return f"https://{product.hostname}"
    return django_settings.EMAIL_LINK_BASE_URL


def _plus_address(address: AssistantAddress, thread: EmailThread) -> str:
    local, _, domain = address.address.partition("@")
    return f"{local}+{thread.token}@{domain}"


def _send_reply(
    inbound: InboundEmail,
    address: AssistantAddress,
    thread: EmailThread,
    user,
    content: str,
    *,
    attachments: list[tuple[str, bytes]] | None = None,
) -> None:
    """Send one reply and record it. To/Reply-To discipline: the reply goes
    ONLY to the registered account email (which the SPF/DKIM gate authenticated
    as the actual sender) — never to a Reply-To the message asked for.

    The text/plain part is the untouched answer plus a Sources list; the
    text/html alternative carries inline citation links. Both are built by
    apps/mail/render from the same linkify pass, so they can't disagree."""
    if thread.pk is None:  # failure notices can arrive before the thread saved
        thread.save()
    subject = _reply_subject(inbound, thread)
    linked = render.linkify(content, base_url=_link_base_url(address))
    footer_lines = _footer_lines(address, thread)
    text_body = (
        content + linked.sources_text() + "\n\n--\n" + "\n".join(footer_lines)
    )
    html_body = render.render_html_body(
        linked.markdown + linked.sources_markdown(), footer_lines
    )
    local, _, domain = address.address.partition("@")
    message_id = make_msgid(domain=domain or None)

    headers = {"Message-ID": message_id}
    if inbound.rfc_message_id:
        headers["In-Reply-To"] = inbound.rfc_message_id
        refs = (inbound.references or "").split()
        headers["References"] = " ".join([*refs, inbound.rfc_message_id][-10:])

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=f'"{address.display_name}" <{address.address}>',
        to=[user.email],
        reply_to=[_plus_address(address, thread)],
        headers=headers,
    )
    email.attach_alternative(html_body, "text/html")
    for filename, blob in attachments or []:
        email.attach(filename, blob, "application/pdf")
    email.send(fail_silently=False)
    OutboundEmail.objects.create(
        thread=thread,
        in_reply_to_inbound=inbound,
        message_id=message_id,
        subject=subject,
        body_text=text_body,
    )


def _notify_once(
    inbound: InboundEmail,
    address: AssistantAddress,
    user,
    kind: str,
    text: str,
) -> None:
    """At most one notice of each kind per sender per day — a notice loop is
    still a loop."""
    key = f"mail:notice:{address.pk}:{kind}:{user.pk}:{timezone.localdate()}"
    if not cache.add(key, 1, timeout=2 * 86_400):
        return
    thread = inbound.thread or _resolve_thread(inbound, address, user)
    try:
        _send_reply(inbound, address, thread, user, text)
    except Exception:  # noqa: BLE001 — the notice is best-effort
        logger.exception("failed to send %s notice for inbound %s", kind, inbound.pk)


def _record_trace(
    user, messages, source_slug, content, trace, model, started, error: str = ""
) -> None:
    """Email turns land in ChatTrace exactly like web turns (unattributed by
    design — see trace_capture). The shim mimics the ninja payload shape."""
    payload = SimpleNamespace(
        messages=[SimpleNamespace(**m) for m in messages],
        source_slug=source_slug,
    )
    record_chat_trace(
        user=user,
        payload=payload,
        content=content,
        trace=trace,
        model=model,
        latency_ms=int((time.monotonic() - started) * 1000),
        error=error,
    )


def _finish(inbound: InboundEmail, status: str, reason: str) -> None:
    inbound.status = status
    inbound.reject_reason = reason[:200]
    inbound.processed_at = timezone.now()
    inbound.save(update_fields=["status", "reject_reason", "processed_at"])
    if reason:
        logger.info("inbound %s -> %s (%s)", inbound.pk, status, reason)
