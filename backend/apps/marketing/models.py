"""Backing store for the public marketing site (marketing-frontend, :3001).

The marketing site is static/SSG and deliberately has no database of its own;
everything it needs from us lives here and is exposed through the public
``/api/marketing/*`` router:

* ``Article`` — one published post. Markdown files under
  ``backend/content/articles/*.md`` are the canonical authoring format
  (synced in by the ``import_articles`` command, idempotent by slug), but an
  article created or edited straight in the Django admin is equally valid —
  the DB row is the source of truth the site renders from, so admin edits
  show up on the next ISR revalidation without a deploy.

* ``ContactSubmission`` — a message from the /contact or /consulting form.
  Rows are the inbox: staff read and triage them in the admin (``status``),
  with an optional Postmark notification fired on arrival.

* ``NewsletterSubscriber`` — bare email capture from the articles page.
  No confirmation flow yet; when a real list provider is adopted this table
  is the export.
"""

from __future__ import annotations

from django.db import models


class Article(models.Model):
    """A marketing-site article. ``body_md`` is markdown; the frontend renders
    it with the site's own prose components, so no HTML is stored or trusted."""

    slug = models.SlugField(max_length=200, unique=True)
    title = models.CharField(max_length=300)
    category = models.CharField(
        max_length=100,
        help_text="Mono eyebrow on cards, e.g. 'Grounding', 'Search', 'Engineering'.",
    )
    # Two lengths of summary: `lede` opens the article header, `excerpt` sells
    # it on index cards. They often differ in register; keep both explicit.
    lede = models.TextField(blank=True)
    excerpt = models.TextField()
    body_md = models.TextField(help_text="Article body, GitHub-flavored markdown.")
    tags = models.JSONField(default=list, blank=True)

    author_name = models.CharField(max_length=120, default="Nick Hudson")
    author_title = models.CharField(
        max_length=200, default="Founder, Hudson Legal Technologies"
    )

    published = models.BooleanField(
        default=False, help_text="Only published articles appear on the site."
    )
    published_at = models.DateField(null=True, blank=True)
    read_minutes = models.PositiveIntegerField(
        default=0, help_text="0 = auto-compute from word count on save."
    )

    # Set by import_articles so a re-run knows which file a row came from;
    # blank for articles authored directly in the admin.
    source_path = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.read_minutes:
            # ~220 wpm is the usual long-form estimate; floor at 1.
            self.read_minutes = max(1, round(len(self.body_md.split()) / 220))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class ContactSubmission(models.Model):
    """One message from the marketing contact form (used on /contact and
    /consulting). This table IS the inbox — triage happens in the admin."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        REPLIED = "replied", "Replied"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    email = models.EmailField()
    organization = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=200, blank=True)
    message = models.TextField()

    # Which page the form was submitted from ('/contact', '/consulting') —
    # consulting leads and general contact read differently.
    page = models.CharField(max_length=200, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW
    )
    notes = models.TextField(blank=True, help_text="Internal triage notes.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class NewsletterSubscriber(models.Model):
    """Email captured by the articles-page subscribe form. Stored lowercase;
    re-submitting an existing address is a silent no-op at the API layer."""

    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.email
