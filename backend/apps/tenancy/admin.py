from django.contrib import admin

from .models import Organization, OrgInvitation, OrgMembership, Product, Subscription


class SubscriptionInline(admin.TabularInline):
    """The org's subscriptions, edited on the Organization page. A blank
    ``product`` is the flagship full-corpus plan; a product is a scoped license."""

    model = Subscription
    fk_name = "org"
    extra = 0
    autocomplete_fields = ("product",)
    fields = ("product", "plan", "status", "seats", "current_period_end")


class OrgMembershipInline(admin.TabularInline):
    model = OrgMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "hostname", "jurisdiction", "is_scoped")
    search_fields = ("name", "slug", "hostname")
    fieldsets = (
        (None, {"fields": ("name", "slug", "hostname")}),
        (
            "Scope lock",
            {"fields": ("allowed_source_slugs", "jurisdiction", "system_prompt_key")},
        ),
        (
            "Brand (login screen)",
            {
                "fields": (
                    "brand_name",
                    "logo_url",
                    "primary_color",
                    "accent_color",
                    "login_tagline",
                    "support_email",
                    "disclaimer",
                )
            },
        ),
    )

    @admin.display(boolean=True, description="Scoped")
    def is_scoped(self, obj):
        return obj.is_scoped


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """NOTE: flipping ``status`` to suspended/canceled here revokes the org's plan
    for every member — but ``User.tier`` is a cache, so run ``reconcile_tiers --fix``
    (or let the nightly cron do it) for the change to land on the hot-path column."""

    list_display = ("name", "slug", "status", "is_personal", "stripe_customer_id")
    list_filter = ("status", "is_personal")
    search_fields = ("name", "slug", "stripe_customer_id")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (SubscriptionInline, OrgMembershipInline)
    fieldsets = (
        (None, {"fields": ("name", "slug", "status", "is_personal")}),
        ("Billing", {"fields": ("stripe_customer_id",)}),
        ("Co-brand (in-app 'Provided by')", {"fields": ("brand_name", "logo_url")}),
    )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "org", "product", "plan", "status", "seats", "created_at")
    list_filter = ("status", "plan", "product")
    autocomplete_fields = ("org", "product")
    search_fields = ("org__name", "product__name", "stripe_subscription_id")


@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "org", "role", "created_at")
    list_filter = ("role",)
    autocomplete_fields = ("user", "org")
    search_fields = ("user__email", "org__name")


@admin.register(OrgInvitation)
class OrgInvitationAdmin(admin.ModelAdmin):
    """Read-mostly: invitations are created by the org API (which emails the raw
    token — never stored). Revoking here is safe; there is nothing to re-send."""

    list_display = ("email", "org", "role", "created_at", "expires_at", "accepted_at",
                    "revoked_at")
    list_filter = ("role",)
    search_fields = ("email", "org__name")
    autocomplete_fields = ("org", "invited_by")
    readonly_fields = ("token_hash", "created_at")
