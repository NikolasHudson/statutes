"""Read-only view of the webhook ledger.

Deliberately not editable: the ledger is an append-only record of what Stripe
told us, and "why did this customer's plan change?" is answered by reading it.
Clearing ``processed_at`` by hand would silently re-arm a replay.
"""

from __future__ import annotations

from django.contrib import admin

from .models import StripeEvent


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "type", "received_at", "processed_at")
    list_filter = ("type", "processed_at")
    search_fields = ("event_id", "type")
    readonly_fields = ("event_id", "type", "payload", "received_at", "processed_at")
    ordering = ("-received_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
