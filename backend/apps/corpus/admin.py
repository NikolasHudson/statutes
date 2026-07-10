from django.contrib import admin, messages

from .models import (
    CaseResearchNote,
    CitationFormat,
    CrossReference,
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    ReviewStatus,
    Source,
)


@admin.register(Jurisdiction)
class JurisdictionAdmin(admin.ModelAdmin):
    list_display = ("name", "abbreviation", "slug")
    search_fields = ("name", "abbreviation", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "jurisdiction", "citation_abbreviation", "slug")
    list_filter = ("jurisdiction",)
    search_fields = ("name", "citation_abbreviation", "slug")
    autocomplete_fields = ("jurisdiction",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(NodeType)
class NodeTypeAdmin(admin.ModelAdmin):
    list_display = ("source", "key", "label_singular", "level", "abbreviation")
    list_filter = ("source",)
    search_fields = ("key", "label_singular", "label_plural")
    autocomplete_fields = ("source",)


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ("path", "heading", "source", "node_type", "is_repealed")
    list_filter = ("source", "node_type", "is_repealed")
    search_fields = ("path", "heading", "ordinal")
    autocomplete_fields = ("source", "node_type", "parent")
    raw_id_fields = ()


@admin.register(NodeVersion)
class NodeVersionAdmin(admin.ModelAdmin):
    list_display = (
        "node",
        "effective_from",
        "effective_to",
        "review_status",
        "enacted_by",
        "created_at",
    )
    list_filter = ("review_status", "effective_from")
    search_fields = ("node__path", "node__heading", "enacted_by", "content_hash")
    autocomplete_fields = ("node",)
    readonly_fields = ("content_hash", "embedding_source_hash", "created_at")
    exclude = ("search_vector", "embedding")
    actions = ("approve_versions", "reject_versions")

    @admin.action(description="Approve selected pending versions")
    def approve_versions(self, request, queryset):
        updated = queryset.filter(review_status=ReviewStatus.PENDING).update(
            review_status=ReviewStatus.APPROVED
        )
        skipped = queryset.count() - updated
        self.message_user(
            request,
            f"Approved {updated} version(s)."
            + (f" Skipped {skipped} non-pending." if skipped else ""),
            level=messages.SUCCESS if updated else messages.WARNING,
        )

    @admin.action(description="Reject selected pending versions")
    def reject_versions(self, request, queryset):
        updated = queryset.filter(review_status=ReviewStatus.PENDING).update(
            review_status=ReviewStatus.REJECTED
        )
        skipped = queryset.count() - updated
        self.message_user(
            request,
            f"Rejected {updated} version(s)."
            + (f" Skipped {skipped} non-pending." if skipped else ""),
            level=messages.SUCCESS if updated else messages.WARNING,
        )


@admin.register(CitationFormat)
class CitationFormatAdmin(admin.ModelAdmin):
    list_display = ("source", "key", "template")
    list_filter = ("source",)
    search_fields = ("key", "template")
    autocomplete_fields = ("source",)


@admin.register(CrossReference)
class CrossReferenceAdmin(admin.ModelAdmin):
    list_display = ("from_version", "to_node", "kind")
    list_filter = ("kind",)
    search_fields = ("external_text", "to_node__path", "from_version__node__path")
    autocomplete_fields = ("from_version", "to_node")


@admin.register(CaseResearchNote)
class CaseResearchNoteAdmin(admin.ModelAdmin):
    """The attorney review queue for automated currency findings (PR9).

    Approve = the finding is real (and a citator-gap candidate for the
    supersession pipeline); Reject = false alarm, suppressed from advisories
    everywhere (and the rejection sticks across re-checks of the same claim).
    """

    list_display = (
        "node", "status", "adverse_kind", "claimed_by", "corpus_verified",
        "review_status", "checked_at",
    )
    list_filter = ("status", "adverse_kind", "review_status", "corpus_verified")
    search_fields = ("node__heading", "claimed_by", "evidence")
    readonly_fields = (
        "node", "kind", "status", "adverse_kind", "claimed_by", "evidence",
        "source_url", "corpus_verified", "corpus_matches", "model",
        "checked_at", "created_at",
    )
    actions = ["approve_notes", "reject_notes"]

    @admin.action(description="Approve selected findings (real)")
    def approve_notes(self, request, queryset):
        updated = queryset.update(review_status=CaseResearchNote.Review.APPROVED)
        self.message_user(request, f"{updated} note(s) approved.", messages.SUCCESS)

    @admin.action(description="Reject selected findings (false alarm)")
    def reject_notes(self, request, queryset):
        updated = queryset.update(review_status=CaseResearchNote.Review.REJECTED)
        self.message_user(request, f"{updated} note(s) rejected.", messages.SUCCESS)
