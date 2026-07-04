from django.contrib import admin

from .models import Organization, OrgMembership, Product, Subscription


class SubscriptionInline(admin.TabularInline):
    """Org-held subscriptions, edited on the Organization page. The inline only
    sets ``org`` (``user`` stays NULL), satisfying the org-XOR-user constraint."""

    model = Subscription
    fk_name = "org"
    extra = 0
    autocomplete_fields = ("product",)
    fields = ("product", "status")


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
    list_display = ("name", "slug", "status")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (SubscriptionInline, OrgMembershipInline)
    fieldsets = (
        (None, {"fields": ("name", "slug", "status")}),
        ("Co-brand (in-app 'Provided by')", {"fields": ("brand_name", "logo_url")}),
    )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "product", "org", "user", "status", "created_at")
    list_filter = ("status", "product")
    autocomplete_fields = ("org", "user", "product")
    search_fields = ("org__name", "user__email", "product__name")


@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "org", "role", "created_at")
    list_filter = ("role",)
    autocomplete_fields = ("user", "org")
    search_fields = ("user__email", "org__name")
