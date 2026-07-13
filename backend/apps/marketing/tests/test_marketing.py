"""apps.marketing: contact capture, newsletter capture, public articles,
and the markdown import command."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.marketing import api as marketing_api
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

    @override_settings(CONTACT_NOTIFY_EMAIL="owner@example.com")
    def test_throttled_submission_still_persists_the_lead(self):
        """The regression this module exists to prevent.

        The throttle used to 429 *before* the insert, so an over-limit lead was
        destroyed: no row, no email, no retry. Past the notify limit the row must
        still be written — only the heads-up email is suppressed, because the
        admin row is the durable record and our inbox is the thing being flooded.
        """
        with mock.patch.object(marketing_api, "_CONTACT_NOTIFY_LIMIT", 2):
            statuses = [self.post(CONTACT_PAYLOAD).status_code for _ in range(5)]

        self.assertEqual(statuses, [200] * 5)
        self.assertEqual(ContactSubmission.objects.count(), 5)  # every lead kept
        self.assertEqual(len(mail.outbox), 2)  # only the notifications are capped

    def test_store_limit_is_the_only_hard_stop(self):
        """Well above any human, and it exists to bound the table, not the funnel."""
        with mock.patch.object(marketing_api, "_CONTACT_STORE_LIMIT", 3):
            statuses = [self.post(CONTACT_PAYLOAD).status_code for _ in range(4)]

        self.assertEqual(statuses, [200, 200, 200, 429])
        self.assertEqual(ContactSubmission.objects.count(), 3)

    def test_throttle_counts_clients_not_proxies(self):
        """Two visitors behind our own edge get their own buckets: the counter is
        keyed on the address the edge appended, not on the connecting proxy."""
        with mock.patch.object(marketing_api, "_CONTACT_STORE_LIMIT", 1):
            for client_addr in ("203.0.113.9", "203.0.113.10"):
                resp = self.client.post(
                    "/api/marketing/contact",
                    CONTACT_PAYLOAD,
                    content_type="application/json",
                    HTTP_X_FORWARDED_FOR=client_addr,
                    REMOTE_ADDR="10.0.0.1",
                )
                self.assertEqual(resp.status_code, 200)
        self.assertEqual(ContactSubmission.objects.count(), 2)

    @override_settings(MARKETING_PROXY_TOKEN="s3cret-token")
    def test_marketing_proxys_asserted_ip_is_honoured_only_with_the_secret(self):
        """The lead reaches Django from the marketing container, so the visitor's
        address is not a property of the connection we see. The proxy asserts it in
        X-Real-Client-IP and proves the assertion with a shared secret.

        The proxy sources that value from CF-Connecting-IP (which Cloudflare
        overwrites, so a visitor cannot forge it) and deliberately does NOT relay
        X-Forwarded-For — relaying an appended chain would let a visitor pick the
        IP their leads are throttled and recorded under, which is the forgery the
        whole change closes.
        """
        self.client.post(
            "/api/marketing/contact",
            CONTACT_PAYLOAD,
            content_type="application/json",
            HTTP_X_REAL_CLIENT_IP="198.51.100.7",
            HTTP_X_MARKETING_PROXY_TOKEN="s3cret-token",
            REMOTE_ADDR="192.0.2.50",  # the marketing container's egress address
        )
        self.client.post(
            "/api/marketing/contact",
            {**CONTACT_PAYLOAD, "email": "spoofer@example.com"},
            content_type="application/json",
            HTTP_X_REAL_CLIENT_IP="198.51.100.7",
            HTTP_X_MARKETING_PROXY_TOKEN="wrong-token",
            REMOTE_ADDR="192.0.2.50",
        )
        # A stranger who found the endpoint and simply typed the header, no token.
        self.client.post(
            "/api/marketing/contact",
            {**CONTACT_PAYLOAD, "email": "stranger@example.com"},
            content_type="application/json",
            HTTP_X_REAL_CLIENT_IP="8.8.8.8",
            REMOTE_ADDR="192.0.2.50",
        )
        stored = {row.email: row.ip for row in ContactSubmission.objects.all()}
        self.assertEqual(stored["jane@example.com"], "198.51.100.7")
        # Without a valid token the caller is the box that connected, and its claim
        # about whom it is forwarding for buys it nothing.
        self.assertEqual(stored["spoofer@example.com"], "192.0.2.50")
        self.assertEqual(stored["stranger@example.com"], "192.0.2.50")

    @override_settings(MARKETING_PROXY_TOKEN="s3cret-token")
    def test_a_visitor_cannot_pick_their_own_lead_throttle_bucket(self):
        """The point of attributing leads correctly: the throttle must bind. A
        visitor rotating a header they control must not mint a fresh bucket, or the
        50/hour store cap is decorative."""
        with mock.patch.object(marketing_api, "_CONTACT_STORE_LIMIT", 3):
            for n in range(5):
                resp = self.client.post(
                    "/api/marketing/contact",
                    {**CONTACT_PAYLOAD, "email": f"flood{n}@example.com"},
                    content_type="application/json",
                    # The chain as Django really receives it: the attacker's rotated
                    # padding on the left, then the address our own edge APPENDED
                    # (here, the marketing container's egress). The edge always
                    # appends — that is the whole reason the right-most entry, and
                    # not the left-most, is the one worth reading.
                    HTTP_X_FORWARDED_FOR=f"10.9.9.{n}, 192.0.2.50",
                    HTTP_X_REAL_CLIENT_IP=f"10.8.8.{n}",  # no token -> ignored
                    REMOTE_ADDR="10.0.0.1",
                )
        self.assertEqual(resp.status_code, 429, resp.content)

    @override_settings(CONTACT_NOTIFY_EMAIL="owner@example.com")
    def test_notification_email_sent_when_configured(self):
        self.post(CONTACT_PAYLOAD)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Jane Attorney", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])

    def test_lead_is_stored_when_notifications_are_off(self):
        """CONTACT_NOTIFY_EMAIL unset is production's state today: the row is the
        record, and losing it because nobody configured a mailbox is not a trade
        we make."""
        with self.assertLogs("apps.marketing.api", level="WARNING") as logs:
            self.assertEqual(self.post(CONTACT_PAYLOAD).status_code, 200)
        self.assertEqual(ContactSubmission.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("CONTACT_NOTIFY_EMAIL is unset", "\n".join(logs.output))

    @override_settings(CONTACT_NOTIFY_EMAIL="owner@example.com")
    def test_notification_failure_is_logged_at_error_and_the_lead_survives(self):
        """Postmark rejecting an unverified CONTACT_FROM_EMAIL (what a mail-domain
        move produces) must not look like success to us as well as to the visitor."""
        with mock.patch.object(
            marketing_api, "send_mail", side_effect=RuntimeError("sender not verified")
        ):
            with self.assertLogs("apps.marketing.api", level="ERROR") as logs:
                self.assertEqual(self.post(CONTACT_PAYLOAD).status_code, 200)

        self.assertEqual(ContactSubmission.objects.count(), 1)
        self.assertIn("notification email FAILED", "\n".join(logs.output))


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
