"""Inbound-email webhook (Postmark → us).

Postmark receives mail on the assistant domain's MX, parses the MIME, and
POSTs one JSON document per message here. This endpoint is deliberately dumb:
authenticate the caller, dedupe, snapshot the payload, route it to an
``AssistantAddress``, and return 200 fast. No LLM work happens in-request — a
chat turn can run for minutes while Postmark times out at ~30s and would
retry, duplicating answers. The ``process_assistant_email`` worker does the
thinking.

Auth: a shared-secret ``?token=`` on the webhook URL (set the same value in
``EMAIL_INBOUND_WEBHOOK_TOKEN`` and in Postmark's webhook config), compared
constant-time — the docling internal-token pattern. Postmark doesn't sign
webhooks, so the token + TLS is the authenticity story; sender authenticity
(SPF/DKIM verdicts inside the payload) is enforced later by the worker.
"""

from __future__ import annotations

import hmac
import json
import logging

from django.conf import settings
from ninja import Router
from ninja.errors import HttpError

from .models import AssistantAddress, InboundEmail

logger = logging.getLogger(__name__)

mail_router = Router(tags=["mail"])


def _header(payload: dict, name: str) -> str:
    """First value of a header from Postmark's Headers list (case-insensitive).
    NOTE: Postmark promotes some headers (Subject, Date, MessageID) to top-level
    fields and they may be absent from the list; callers handle ''."""
    want = name.lower()
    for h in payload.get("Headers") or []:
        if str(h.get("Name", "")).lower() == want:
            return str(h.get("Value", ""))
    return ""


def _spf_pass(payload: dict) -> bool | None:
    received_spf = _header(payload, "Received-SPF")
    if not received_spf:
        return None
    return received_spf.strip().lower().startswith("pass")


def _dkim_pass(payload: dict) -> bool | None:
    auth_results = _header(payload, "Authentication-Results")
    if not auth_results:
        return None
    return "dkim=pass" in auth_results.lower()


def _spam_score(payload: dict) -> float | None:
    raw = _header(payload, "X-Spam-Score")
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return None


# Marks of machine-generated mail (out-of-office, DSNs, list traffic). We must
# never answer these: an autoresponder that answers our reply creates a mail
# loop, and answering a bounce is backscatter.
def _is_auto_generated(payload: dict) -> bool:
    auto_submitted = _header(payload, "Auto-Submitted").strip().lower()
    if auto_submitted and auto_submitted != "no":
        return True
    if _header(payload, "Precedence").strip().lower() in {"bulk", "junk", "list", "auto_reply"}:
        return True
    if _header(payload, "X-Auto-Response-Suppress") or _header(payload, "X-Autoreply"):
        return True
    if _header(payload, "List-Id") or _header(payload, "List-Unsubscribe"):
        return True
    local = (payload.get("From") or "").split("@")[0].strip().lower().strip("<")
    if local in {"mailer-daemon", "postmaster", "no-reply", "noreply"}:
        return True
    return False


def _base_address(payload: dict) -> str:
    """The assistant inbox this message was addressed to, plus-tag stripped
    (``assistant+t_ab12@x`` → ``assistant@x``). OriginalRecipient is the
    envelope recipient, which is authoritative over To (Bcc/alias delivery)."""
    raw = (payload.get("OriginalRecipient") or "").strip().lower()
    if not raw:
        to_full = payload.get("ToFull") or []
        raw = (to_full[0].get("Email", "") if to_full else "").strip().lower()
    local, _, domain = raw.partition("@")
    return f"{local.split('+')[0]}@{domain}" if domain else raw


def _strip_attachment_content(payload: dict) -> dict:
    """Snapshot the payload without attachment bytes: v1 never reads
    attachments, and client documents must not be persisted by accident."""
    snapshot = dict(payload)
    snapshot["Attachments"] = [
        {"Name": a.get("Name", ""), "ContentType": a.get("ContentType", ""),
         "ContentLength": a.get("ContentLength", 0)}
        for a in payload.get("Attachments") or []
    ]
    return snapshot


@mail_router.post("/inbound", auth=None)
def inbound_webhook(request, token: str = ""):
    expected = settings.EMAIL_INBOUND_WEBHOOK_TOKEN
    if not expected:
        raise HttpError(503, "inbound email is not configured")
    if not hmac.compare_digest(token, expected):
        raise HttpError(403, "bad token")

    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HttpError(400, "invalid JSON body") from exc

    provider_id = str(payload.get("MessageID") or "").strip()
    if not provider_id:
        raise HttpError(400, "missing MessageID")

    from_full = payload.get("FromFull") or {}
    from_email = str(from_full.get("Email") or payload.get("From") or "").strip().lower()
    if not from_email:
        raise HttpError(400, "missing From")

    to_email = _base_address(payload)
    address = AssistantAddress.objects.filter(address=to_email, active=True).first()

    body = payload.get("StrippedTextReply") or payload.get("TextBody") or ""

    inbound, created = InboundEmail.objects.get_or_create(
        provider_id=provider_id,
        defaults={
            "rfc_message_id": _header(payload, "Message-ID"),
            "in_reply_to": _header(payload, "In-Reply-To"),
            "references": _header(payload, "References"),
            "address": address,
            "from_email": from_email,
            "to_email": to_email,
            "mailbox_hash": str(payload.get("MailboxHash") or ""),
            "subject": str(payload.get("Subject") or "")[:500],
            "body_text": body,
            "spf_pass": _spf_pass(payload),
            "dkim_pass": _dkim_pass(payload),
            "spam_score": _spam_score(payload),
            "is_auto_generated": _is_auto_generated(payload),
            "raw_payload": _strip_attachment_content(payload),
            # No matching active address: dead-letter it as ignored so it's
            # auditable but the worker never picks it up.
            "status": InboundEmail.Status.PENDING
            if address
            else InboundEmail.Status.IGNORED,
            "reject_reason": "" if address else "no active assistant address",
        },
    )
    if not created:
        logger.info("inbound webhook duplicate delivery: %s", provider_id)
    return {"ok": True, "duplicate": not created}
