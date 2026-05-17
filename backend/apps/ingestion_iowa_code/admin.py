from django.contrib import admin

from .models import IngestionRun, RawIngestion


@admin.register(RawIngestion)
class RawIngestionAdmin(admin.ModelAdmin):
    list_display = (
        "source_kind",
        "code_year",
        "fetched_at",
        "byte_size",
        "content_hash_short",
    )
    list_filter = ("source_kind", "code_year")
    search_fields = ("content_hash", "fetched_from", "storage_path")
    readonly_fields = (
        "source_kind",
        "code_year",
        "fetched_at",
        "fetched_from",
        "content_hash",
        "byte_size",
        "storage_path",
    )

    @admin.display(description="hash")
    def content_hash_short(self, obj):
        return obj.content_hash[:12]


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "raw",
        "status",
        "started_at",
        "finished_at",
        "nodes_added",
        "nodes_amended",
        "nodes_repealed",
        "nodes_unchanged",
    )
    list_filter = ("status",)
    readonly_fields = (
        "raw",
        "started_at",
        "finished_at",
        "nodes_added",
        "nodes_amended",
        "nodes_repealed",
        "nodes_unchanged",
        "validation_errors",
        "log",
    )
