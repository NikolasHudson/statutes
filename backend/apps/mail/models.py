"""Email-assistant surface: attorneys email an address, a worker runs the
existing chat pipeline headlessly, and the answer comes back by email.

An ``AssistantAddress`` is the email analog of ``tenancy.Product.hostname`` —
a product front door. ``assistant@mail.<domain>`` with ``product=None`` is the
unlocked flagship; ``ethics@<delegated-subdomain>`` pinned to a scoped product
is the ISBA shape. Routing an inbound message to its address is the mail
counterpart of ProductResolutionMiddleware.

The chat loop itself is stateless (the web client resends full history every
turn), so ``EmailThread`` holds the server-side conversation state an email
reply chain needs: the exact ``[{role, content}]`` history to replay into
``run_chat_turn`` plus a short token used in the plus-addressed Reply-To
(``assistant+<token>@…``) so threading survives clients that mangle the
In-Reply-To header.

``InboundEmail`` doubles as the work queue — DO App Platform has no broker, so
the webhook stores rows and the ``process_assistant_email --forever`` worker
claims them (the trace-purge worker pattern). Bodies are confidential client
material: rows are purged on the same retention worker, and attachment
*content* is never stored at all.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models


def new_thread_token() -> str:
    """Short, email-local-part-safe thread id (used as the plus-address tag,
    so it must survive address parsing: lowercase hex, no punctuation)."""
    return "t" + secrets.token_hex(5)


class AssistantAddress(models.Model):
    """One assistant inbox: the email front door to a (possibly scoped) product."""

    class Mode(models.TextChoices):
        # Pilot: only explicitly allowlisted senders get answers; everyone
        # else is silently ignored (no reply — replying reveals the address
        # is live and creates backscatter).
        ALLOWLIST = "allowlist", "Allowlist only"
        # Production: any registered, entitled user gets answers.
        ENTITLED = "entitled", "Entitled users"

    address = models.EmailField(
        unique=True,
        help_text="The full inbox address, e.g. assistant@mail.nick.law. "
        "Plus-tags are stripped before matching, so this is the base form.",
    )
    product = models.ForeignKey(
        "tenancy.Product",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assistant_addresses",
        help_text="Scope lock + entitlement source. NULL = flagship (full "
        "corpus, any registered user in 'entitled' mode).",
    )
    display_name = models.CharField(
        max_length=100, default="Hudson Research Assistant"
    )
    active = models.BooleanField(default=True)
    mode = models.CharField(
        max_length=16, choices=Mode.choices, default=Mode.ALLOWLIST
    )
    # Clamped against chat.ALLOWED_CHAT_MODELS at use time, same cost-control
    # posture as the web endpoint's model whitelist.
    model = models.CharField(max_length=40, default="gpt-5-mini")
    signature = models.TextField(
        blank=True, help_text="Optional text above the standard footer."
    )
    disclaimer = models.TextField(
        blank=True, help_text="Extra per-product disclaimer appended to the footer."
    )
    # Loop backstop: auto-responders that slip past the header checks can at
    # worst extract this many answers/day, then go silent.
    max_daily_per_sender = models.PositiveSmallIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "assistant addresses"

    def save(self, *args, **kwargs):
        self.address = self.address.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.address


class AddressAllowlist(models.Model):
    """Pilot gating: senders permitted on an allowlist-mode address."""

    address = models.ForeignKey(
        AssistantAddress, on_delete=models.CASCADE, related_name="allowlist"
    )
    email = models.EmailField()
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["address", "email"], name="allowlist_unique_per_address"
            )
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.email} on {self.address}"


class EmailThread(models.Model):
    """Server-side conversation state for one email reply chain."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        # Hard bounce / complaint from this recipient: never send again.
        SUPPRESSED = "suppressed", "Suppressed"

    address = models.ForeignKey(
        AssistantAddress, on_delete=models.CASCADE, related_name="threads"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_threads"
    )
    token = models.CharField(
        max_length=16, unique=True, default=new_thread_token
    )
    subject = models.CharField(max_length=500, blank=True)
    # The exact [{"role": ..., "content": ...}] history replayed into
    # run_chat_turn on the next inbound reply. Confidential; trimmed to the
    # last MAX_THREAD_HISTORY entries by the worker.
    messages = models.JSONField(default=list, blank=True)
    turn_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.token} ({self.address})"


class InboundEmail(models.Model):
    """One received message: audit row + work-queue item.

    ``provider_id`` is Postmark's MessageID (the dedupe key — Postmark retries
    the webhook on non-200, so inserts must be idempotent). The RFC 5322
    Message-ID header, when present, lands in ``rfc_message_id`` and is what
    our reply's In-Reply-To must reference.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        ANSWERED = "answered", "Answered"
        # A gate declined it and a (rate-capped) notice may have been sent.
        REJECTED = "rejected", "Rejected"
        # Silently dropped: unknown sender, failed auth, auto-responder, spam.
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    provider_id = models.CharField(max_length=100, unique=True)
    rfc_message_id = models.CharField(max_length=512, blank=True)
    in_reply_to = models.CharField(max_length=512, blank=True)
    references = models.TextField(blank=True)
    address = models.ForeignKey(
        AssistantAddress,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound",
    )
    thread = models.ForeignKey(
        EmailThread, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="inbound",
    )
    from_email = models.EmailField()
    to_email = models.CharField(max_length=254, blank=True)
    mailbox_hash = models.CharField(max_length=64, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    # StrippedTextReply when Postmark could split off the quoted chain,
    # else the full TextBody. This is what becomes the user turn.
    body_text = models.TextField(blank=True)
    spf_pass = models.BooleanField(null=True)
    dkim_pass = models.BooleanField(null=True)
    spam_score = models.FloatField(null=True, blank=True)
    is_auto_generated = models.BooleanField(default=False)
    # Full provider payload minus attachment content (metadata only) — kept
    # under the same retention purge as ChatTrace.
    raw_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reject_reason = models.CharField(max_length=200, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    # Backoff for retries after a ChatTurnError; the worker only claims rows
    # whose next_attempt_at has passed.
    next_attempt_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.from_email} -> {self.to_email} [{self.status}]"


class OutboundEmail(models.Model):
    """One sent reply, kept so future In-Reply-To headers can find the thread."""

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    thread = models.ForeignKey(
        EmailThread, on_delete=models.CASCADE, related_name="outbound"
    )
    in_reply_to_inbound = models.ForeignKey(
        InboundEmail, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="replies",
    )
    # Our RFC Message-ID (indexed: inbound reply threading looks it up).
    message_id = models.CharField(max_length=512, unique=True)
    subject = models.CharField(max_length=500, blank=True)
    body_text = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SENT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.subject} -> thread {self.thread.token}"
