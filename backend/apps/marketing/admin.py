from django.contrib import admin

from .models import Article, ContactSubmission, NewsletterSubscriber


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "published",
        "published_at",
        "read_minutes",
        "source_path",
        "updated_at",
    )
    list_filter = ("published", "category")
    search_fields = ("title", "slug", "excerpt", "body_md")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-published_at",)


@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "email", "organization", "page", "status")
    list_filter = ("status", "page")
    search_fields = ("name", "email", "organization", "message")
    list_editable = ("status",)
    readonly_fields = (
        "name",
        "email",
        "organization",
        "role",
        "message",
        "page",
        "ip",
        "created_at",
    )
    ordering = ("-created_at",)


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "unsubscribed_at")
    search_fields = ("email",)
    ordering = ("-created_at",)
