"""apps.marketing: contact capture, newsletter capture, public articles,
and the markdown import command."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.marketing.models import Article, ContactSubmission, NewsletterSubscriber

CONTACT_PAYLOAD = {
    "name": "Jane Attorney",
    "email": "jane@example.com",
    "message": "Interested in the email-assistant pilot.",
    "organization": "Example Firm",
    "role": "Partner",
    "page": "/contact",
}


class ContactApiTests(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters are per-IP and persist across tests
        self.client = Client()

    def post(self, payload):
        return self.client.post(
            "/api/marketing/contact", payload, content_type="application/json"
        )

    def test_submission_is_stored(self):
        resp = self.post(CONTACT_PAYLOAD)
        self.assertEqual(resp.status_code, 200)
        row = ContactSubmission.objects.get()
        self.assertEqual(row.name, "Jane Attorney")
        self.assertEqual(row.email, "jane@example.com")
        self.assertEqual(row.page, "/contact")
        self.assertEqual(row.status, ContactSubmission.Status.NEW)

    def test_honeypot_pretends_success_but_stores_nothing(self):
        resp = self.post({**CONTACT_PAYLOAD, "website": "http://spam.example"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ContactSubmission.objects.count(), 0)

    def test_blank_message_rejected(self):
        resp = self.post({**CONTACT_PAYLOAD, "message": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_throttle_kicks_in(self):
        for _ in range(5):
            self.assertEqual(self.post(CONTACT_PAYLOAD).status_code, 200)
        self.assertEqual(self.post(CONTACT_PAYLOAD).status_code, 429)

    @override_settings(CONTACT_NOTIFY_EMAIL="owner@example.com")
    def test_notification_email_sent_when_configured(self):
        self.post(CONTACT_PAYLOAD)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Jane Attorney", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])


class SubscribeApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

    def test_subscribe_is_idempotent_and_lowercased(self):
        for addr in ("Reader@Example.com", "reader@example.com"):
            resp = self.client.post(
                "/api/marketing/subscribe",
                {"email": addr},
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
        sub = NewsletterSubscriber.objects.get()
        self.assertEqual(sub.email, "reader@example.com")


class ArticleApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        Article.objects.create(
            slug="live-post",
            title="Live post",
            category="Search",
            excerpt="An excerpt.",
            body_md="One two three.",
            published=True,
            published_at=date(2026, 6, 24),
        )
        Article.objects.create(
            slug="draft-post",
            title="Draft post",
            category="Search",
            excerpt="Hidden.",
            body_md="Words.",
            published=False,
        )

    def test_list_returns_only_published(self):
        resp = self.client.get("/api/marketing/articles")
        self.assertEqual(resp.status_code, 200)
        slugs = [a["slug"] for a in resp.json()]
        self.assertEqual(slugs, ["live-post"])

    def test_detail_includes_body_and_404s_on_draft(self):
        resp = self.client.get("/api/marketing/articles/live-post")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["body_md"], "One two three.")
        self.assertEqual(
            self.client.get("/api/marketing/articles/draft-post").status_code, 404
        )

    def test_read_minutes_autocomputed(self):
        self.assertEqual(Article.objects.get(slug="live-post").read_minutes, 1)


MD_FILE = """---
title: Test article
category: Engineering
date: 2026-07-01
excerpt: Short excerpt.
tags: [One, Two]
---

Body paragraph.
"""


class ImportArticlesTests(TestCase):
    def test_import_creates_then_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test-article.md"
            path.write_text(MD_FILE, encoding="utf-8")
            call_command("import_articles", "--dir", tmp)
            art = Article.objects.get(slug="test-article")
            self.assertEqual(art.title, "Test article")
            self.assertEqual(art.published_at, date(2026, 7, 1))
            self.assertEqual(art.tags, ["One", "Two"])
            self.assertTrue(art.published)
            self.assertEqual(art.body_md.strip(), "Body paragraph.")
            self.assertEqual(art.read_minutes, 1)

            path.write_text(
                MD_FILE.replace("Test article", "Retitled"), encoding="utf-8"
            )
            call_command("import_articles", "--dir", tmp)
            self.assertEqual(Article.objects.count(), 1)
            self.assertEqual(Article.objects.get(slug="test-article").title, "Retitled")

    def test_repo_content_dir_imports_cleanly(self):
        call_command("import_articles")
        self.assertTrue(
            Article.objects.filter(
                slug="why-legal-ai-invents-citations", published=True
            ).exists()
        )
