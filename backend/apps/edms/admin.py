"""Django admin for EDMSpro.

Two deliberate restrictions:

* **No token fields anywhere.** ``CloudIntegration`` is registered without its
  ciphertext columns, so a staff account with admin access cannot read (or
  paste) a user's OneDrive credentials out of a form.
* **Contributions are read-only and not downloadable.** ``CrowdsourceArtifact``
  shows what was collected so a removal request can be answered, and nothing
  more — there is no link to the object and no read path in the app. Deleting
  rows here is disabled too: dropping the index row without deleting the object
  would leave bytes in the bucket that nobody can attribute. Use
  ``purge_crowdsource``, which does both.
"""

from __future__ import annotations

from django.contrib import admin

from .models import (
    CaseFolderMapping,
    CloudIntegration,
    CrowdsourceArtifact,
    EdmsSettings,
    FilingSync,
)


@admin.register(EdmsSettings)
class EdmsSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "cloud_provider", "crowdsource_opt_in", "updated_at")
    list_filter = ("cloud_provider", "crowdsource_opt_in")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)


@admin.register(CloudIntegration)
class CloudIntegrationAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "account_email", "needs_reconnect", "connected_at")
    list_filter = ("provider", "needs_reconnect")
    search_fields = ("user__email", "account_email")
    raw_id_fields = ("user",)
    # Explicit allowlist — never the ``*_enc`` columns.
    fields = (
        "user",
        "provider",
        "account_email",
        "account_name",
        "expires_at",
        "needs_reconnect",
        "last_error",
        "connected_at",
    )
    readonly_fields = ("connected_at",)


@admin.register(CaseFolderMapping)
class CaseFolderMappingAdmin(admin.ModelAdmin):
    list_display = ("user", "case_number", "folder_path", "updated_at")
    search_fields = ("user__email", "case_number", "folder_path")
    raw_id_fields = ("user",)


@admin.register(FilingSync)
class FilingSyncAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "user", "case_number", "doc_title", "status", "destination_path",
    )
    list_filter = ("status", "provider")
    search_fields = ("user__email", "case_number", "doc_title")
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"


@admin.register(CrowdsourceArtifact)
class CrowdsourceArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "submitted_by", "case_type", "doc_type", "byte_size", "status",
    )
    list_filter = ("status", "case_type", "doc_type")
    search_fields = ("submitted_by__email", "case_number", "object_key")
    raw_id_fields = ("submitted_by",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # See module docstring: deleting the row here would orphan the object.
        return False
