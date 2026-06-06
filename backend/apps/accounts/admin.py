from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import APIKey, AuditEvent, User, UserProfile


class UserProfileInline(admin.StackedInline):
    """Edit a user's profile / preferences alongside the account. One row per
    user (OneToOne), so no extras to add."""

    model = UserProfile
    can_delete = False
    extra = 0
    readonly_fields = ("onboarding_completed_at", "tos_accepted_at", "updated_at")
    verbose_name_plural = "Profile & preferences"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "tier", "is_staff", "is_active", "date_joined")
    list_filter = ("tier", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "full_name", "first_name", "last_name")
    inlines = (UserProfileInline,)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Profile"), {"fields": ("first_name", "last_name", "full_name", "tier")}),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "full_name", "tier"),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined")


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "prefix", "created_at", "last_used_at", "revoked_at")
    list_filter = ("revoked_at",)
    search_fields = ("name", "user__email", "prefix")
    readonly_fields = ("prefix", "hashed_key", "created_at", "last_used_at")
    autocomplete_fields = ("user",)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Read-only view of the append-only security audit trail. The model is
    append-only by contract (AuditEvent.save), and the admin enforces the same:
    no add / change / delete, so the forensic record can't be edited from here.
    """

    list_display = ("created_at", "event_type", "outcome", "actor_email", "source_ip")
    list_filter = ("event_type", "outcome", "created_at")
    search_fields = ("actor_email", "source_ip")
    date_hierarchy = "created_at"
    readonly_fields = (
        "actor",
        "actor_email",
        "event_type",
        "outcome",
        "created_at",
        "source_ip",
        "user_agent",
        "detail",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
