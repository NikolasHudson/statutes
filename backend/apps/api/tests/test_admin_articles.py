"""Staff-only article management surface (apps.api.admin_articles).

The gate (anon / non-staff 401), CRUD round-trip, slug rules, the
published-needs-a-date rule, and the md-sourced-row delete guard.
"""

from __future__ import annotations

import json
from datetime import date

from django.test import Client, TestCase

from apps.accounts.models import User
from apps.marketing.models import Article

from ._factories import make_user


def _staff(email="staff@example.com") -> User:
    user = make_user(email)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _post(client: Client, data: dict):
    return client.post(
        "/api/admin/articles",
        data=json.dumps(data),
        content_type="application/json",
    )


def _patch(client: Client, article_id: int, data: dict):
    return client.patch(
        f"/api/admin/articles/{article_id}",
        data=json.dumps(data),
        content_type="application/json",
    )


class AdminArticlesGateTests(TestCase):
    def test_anonymous_gets_401(self):
        self.assertEqual(Client().get("/api/admin/articles").status_code, 401)

    def test_non_staff_gets_401(self):
        client = _client(make_user("plain@example.com"))
        self.assertEqual(client.get("/api/admin/articles").status_code, 401)
        self.assertEqual(_post(client, {"title": "Nope"}).status_code, 401)


class AdminArticlesCrudTests(TestCase):
    def setUp(self):
        self.client = _client(_staff())

    def test_create_read_update_delete(self):
        resp = _post(
            self.client,
            {
                "title": "A new post",
                "category": "Search",
                "body_md": "Some words here.",
                "tags": ["One", " Two "],
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["slug"], "a-new-post")  # derived from title
        self.assertFalse(body["published"])
        self.assertEqual(body["tags"], ["One", "Two"])
        self.assertEqual(body["read_minutes"], 1)  # auto-computed
        aid = body["id"]

        # Drafts appear in the admin list but not the public one.
        slugs = [a["slug"] for a in self.client.get("/api/admin/articles").json()]
        self.assertIn("a-new-post", slugs)
        public = Client().get("/api/marketing/articles").json()
        self.assertNotIn("a-new-post", [a["slug"] for a in public])

        resp = _patch(
            self.client,
            aid,
            {"published": True, "published_at": "2026-07-11", "lede": "A lede."},
        )
        self.assertEqual(resp.status_code, 200)
        art = Article.objects.get(pk=aid)
        self.assertTrue(art.published)
        self.assertEqual(art.published_at, date(2026, 7, 11))

        resp = self.client.delete(f"/api/admin/articles/{aid}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Article.objects.filter(pk=aid).exists())

    def test_published_requires_date(self):
        resp = _post(self.client, {"title": "No date", "published": True})
        self.assertEqual(resp.status_code, 400)

    def test_slug_rules(self):
        self.assertEqual(
            _post(self.client, {"title": "One", "slug": "Bad Slug!"}).status_code,
            400,
        )
        _post(self.client, {"title": "One", "slug": "taken"})
        resp = _post(self.client, {"title": "Two", "slug": "taken"})
        self.assertEqual(resp.status_code, 400)
        # Auto-derived slugs dodge collisions with a numeric suffix.
        resp = _post(self.client, {"title": "Taken"})
        self.assertEqual(resp.json()["slug"], "taken-2")

    def test_body_edit_recomputes_read_minutes(self):
        aid = _post(self.client, {"title": "Short", "body_md": "tiny"}).json()["id"]
        _patch(self.client, aid, {"body_md": "word " * 900})
        self.assertEqual(Article.objects.get(pk=aid).read_minutes, 4)

    def test_md_sourced_article_cannot_be_deleted(self):
        art = Article.objects.create(
            slug="from-file",
            title="From a file",
            excerpt="x",
            body_md="x",
            source_path="content/articles/from-file.md",
        )
        resp = self.client.delete(f"/api/admin/articles/{art.id}")
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Article.objects.filter(pk=art.id).exists())
