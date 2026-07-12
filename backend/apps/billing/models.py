"""The webhook idempotency ledger.

Stripe guarantees *at-least-once* delivery, not exactly-once: it retries on any
non-2xx, it can deliver out of order, and it will happily send the same event
twice on a network blip. Every handler in :mod:`apps.billing.webhooks` therefore
runs behind this table — one row per ``evt_...`` id, unique — and a redelivery of
an already-processed event is a no-op.

The row is also the forensic record: ``payload`` is the exact, signature-verified
event body, so "why did this customer get downgraded on the 3rd?" is answerable
from the database alone, without Stripe's dashboard.
"""

from __future__ import annotations

from django.db import models


class StripeEvent(models.Model):
    """One received Stripe webhook event.

    ``processed_at IS NULL`` means "seen, not yet applied" — either in flight, or
    a handler raised and Stripe will retry (we return 500 so it does). That is
    why the guard is on ``processed_at`` and not on mere row existence: a crashed
    handler must be retryable, a completed one must not be re-run.
    """

    event_id = models.CharField(max_length=64, unique=True)
    type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Stamped when a handler has run to completion (or was deliberately skipped
    # as unhandled/unresolvable). Null = not yet applied.
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-received_at",)
        verbose_name = "Stripe event"

    def __str__(self) -> str:
        state = "processed" if self.processed_at else "pending"
        return f"{self.type} {self.event_id} ({state})"
