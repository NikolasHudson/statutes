from django.contrib import admin

from .models import AddressAllowlist, AssistantAddress, EmailThread, InboundEmail, OutboundEmail


class AllowlistInline(admin.TabularInline):
    model = AddressAllowlist
    extra = 0


@admin.register(AssistantAddress)
class AssistantAddressAdmin(admin.ModelAdmin):
    list_display = ("address", "product", "mode", "model", "active", "created_at")
    list_filter = ("mode", "active")
    inlines = [AllowlistInline]


@admin.register(EmailThread)
class EmailThreadAdmin(admin.ModelAdmin):
    list_display = ("token", "address", "user", "subject", "turn_count", "status", "last_activity")
    list_filter = ("status", "address")
    search_fields = ("token", "subject", "user__email")
    # Conversation content is confidential; the list view is the ops surface.
    exclude = ("messages",)
    readonly_fields = ("token", "turn_count", "created_at", "last_activity")


@admin.register(InboundEmail)
class InboundEmailAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "from_email", "to_email", "subject", "status",
        "reject_reason", "attempts",
    )
    list_filter = ("status", "address")
    search_fields = ("from_email", "subject", "provider_id")
    date_hierarchy = "created_at"
    # Body + raw payload are confidential client material; keep them out of
    # the admin form. Ops questions are answered by status/reason/headers.
    exclude = ("body_text", "raw_payload")
    readonly_fields = [
        f.name for f in InboundEmail._meta.fields
        if f.name not in ("status", "next_attempt_at", "body_text", "raw_payload")
    ]


@admin.register(OutboundEmail)
class OutboundEmailAdmin(admin.ModelAdmin):
    list_display = ("created_at", "thread", "subject", "status")
    list_filter = ("status",)
    search_fields = ("subject", "message_id")
    exclude = ("body_text",)
    readonly_fields = ("thread", "in_reply_to_inbound", "message_id", "subject", "created_at")
