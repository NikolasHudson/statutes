"""End-to-end tests for the Phase 3 REST surface.

Uses Django's test client through the Ninja URL router, so each test
exercises auth, parameter validation, and serialization together — the
way a real caller would.

Tagged 'postgres' because the search route exercises FTS / trigram /
vector under the hood, all of which are Postgres features."""

from __future__ import annotations

import datetime as dt
import json

from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, tag
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Tier
from apps.corpus.models import (
    CrossReference,
    CrossReferenceKind,
    Node,
    NodeType,
    NodeVersion,
    ReviewStatus,
)
from apps.corpus.services.lookups import reset_default_source_cache

from ._factories import make_api_key, make_iowa_corpus_minimal, make_user


@tag("postgres")
class APIRouteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(tier=Tier.SOLO)
        cls.api_key, cls.raw_key = make_api_key(cls.user)
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def _hdrs(self, key: str | None = None):
        if key is None:
            key = self.raw_key
        return {"HTTP_X_API_KEY": key}

    # -- health -----------------------------------------------------------

    def test_health_is_public(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    # -- auth -------------------------------------------------------------

    def test_lookup_requires_api_key(self):
        resp = self.client.get("/api/lookup/714.16")
        self.assertEqual(resp.status_code, 401)

    def test_lookup_rejects_bad_key(self):
        resp = self.client.get("/api/lookup/714.16", **self._hdrs("not-a-key"))
        self.assertEqual(resp.status_code, 401)

    # -- lookup -----------------------------------------------------------

    def test_lookup_resolves_known_section(self):
        resp = self.client.get("/api/lookup/714.16", **self._hdrs())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["found"])
        self.assertEqual(body["section"]["node"]["path"], "714.16")
        self.assertEqual(body["section"]["node"]["heading"], "Consumer fraud")
        # contract: every response has a date stamp
        self.assertEqual(body["as_of_date"], dt.date.today().isoformat())
        # contract: official URL link
        self.assertIn(
            "legis.iowa.gov", body["section"]["node"]["official_url"]
        )

    def test_lookup_unknown_section_returns_candidates(self):
        # Section 714.99 doesn't exist, but 714 chapter does + 714.16 sibling.
        resp = self.client.get("/api/lookup/714.99", **self._hdrs())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["found"])
        self.assertIsNone(body["section"])
        # Brief: never silently substitute. We surface candidates.
        paths = [c["path"] for c in body["candidates"]]
        self.assertIn("714.16", paths)

    def test_lookup_handles_iowa_code_form(self):
        resp = self.client.get(
            "/api/lookup/Iowa Code § 714.16", **self._hdrs()
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["found"])

    # -- search -----------------------------------------------------------

    def test_search_returns_hits_for_query_present_in_corpus(self):
        # use_vector=False so the test does not depend on embeddings
        resp = self.client.post(
            "/api/search",
            data=json.dumps({"query": "consumer fraud", "use_vector": False}),
            content_type="application/json",
            **self._hdrs(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["hits"], "expected at least one hit")
        self.assertEqual(body["hits"][0]["node"]["path"], "714.16")
        self.assertEqual(body["as_of_date"], dt.date.today().isoformat())

    def test_search_rejects_empty_query(self):
        resp = self.client.post(
            "/api/search",
            data=json.dumps({"query": "  "}),
            content_type="application/json",
            **self._hdrs(),
        )
        self.assertEqual(resp.status_code, 400)

    # -- history / at-date -----------------------------------------------

    def test_history_returns_versions(self):
        resp = self.client.get(
            f"/api/sections/{self.section.id}/history", **self._hdrs()
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["versions"]), 1)
        self.assertEqual(
            body["versions"][0]["effective_from"], "2025-01-01"
        )

    def test_at_date_returns_404_when_predates_first_version(self):
        resp = self.client.get(
            f"/api/sections/{self.section.id}/at/2020-06-01",
            **self._hdrs(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_at_date_returns_version_in_effect(self):
        resp = self.client.get(
            f"/api/sections/{self.section.id}/at/2025-06-01",
            **self._hdrs(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["version"]["effective_from"], "2025-01-01")

    # -- cross references ------------------------------------------------

    def test_cross_references_returns_outgoing_refs(self):
        target = Node.objects.create(
            source=self.source,
            node_type=NodeType.objects.get(source=self.source, key="section"),
            parent=self.section.parent,
            ordinal="17",
            path="714.17",
            heading="Theft definitions",
        )
        CrossReference.objects.create(
            from_version=self.version,
            to_node=target,
            kind=CrossReferenceKind.INTERNAL,
        )
        resp = self.client.get(
            f"/api/sections/{self.section.id}/cross-references",
            **self._hdrs(),
        )
        self.assertEqual(resp.status_code, 200)
        refs = resp.json()["references"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["direction"], "outgoing")
        self.assertEqual(refs[0]["other"]["path"], "714.17")

    # -- definitions ------------------------------------------------------

    def test_definitions_finds_inline_definition(self):
        resp = self.client.get(
            "/api/definitions/merchant", **self._hdrs()
        )
        self.assertEqual(resp.status_code, 200)
        defs = resp.json()["definitions"]
        self.assertTrue(defs, "expected a definition match")
        self.assertEqual(defs[0]["term"].lower(), "'merchant'")
        self.assertIn("person engaged", defs[0]["definition"])

    # -- recent amendments -----------------------------------------------

    def test_recent_amendments_lists_recent_versions(self):
        resp = self.client.get(
            "/api/recent-amendments?since=2024-01-01", **self._hdrs()
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()["amendments"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["change_kind"], "new")

    # -- tier gating -----------------------------------------------------

    def test_free_tier_cannot_call_history(self):
        free = make_user(email="free@example.com", tier=Tier.FREE)
        _, raw = make_api_key(free, name="free")
        resp = self.client.get(
            f"/api/sections/{self.section.id}/history",
            **{"HTTP_X_API_KEY": raw},
        )
        self.assertEqual(resp.status_code, 403)

    def test_free_tier_can_call_lookup(self):
        free = make_user(email="free2@example.com", tier=Tier.FREE)
        _, raw = make_api_key(free, name="free2")
        resp = self.client.get(
            "/api/lookup/714.16", **{"HTTP_X_API_KEY": raw}
        )
        self.assertEqual(resp.status_code, 200)

    # -- rate limit ------------------------------------------------------

    def test_quota_headers_present_on_success(self):
        resp = self.client.get("/api/lookup/714.16", **self._hdrs())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("X-RateLimit-Remaining", resp.headers)


@tag("postgres")
class BrowseSearchRouteTests(TestCase):
    """The public, unauthenticated /api/browse/search endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def test_search_is_public(self):
        resp = self.client.get("/api/browse/search", {"q": "consumer fraud"})
        self.assertEqual(resp.status_code, 200)

    def test_keyword_query_returns_browse_shaped_hit(self):
        resp = self.client.get("/api/browse/search", {"q": "consumer fraud"})
        body = resp.json()
        self.assertGreaterEqual(body["count"], 1)
        hit = body["results"][0]
        self.assertEqual(hit["node_id"], self.section.id)
        self.assertIn("714.16", hit["citation"])
        self.assertEqual(hit["chapter"]["ordinal"], "714")
        self.assertTrue(hit["snippet"])

    def test_exact_citation_is_pinned_first_and_flagged(self):
        resp = self.client.get("/api/browse/search", {"q": "714.16"})
        body = resp.json()
        self.assertGreaterEqual(body["count"], 1)
        top = body["results"][0]
        self.assertEqual(top["node_id"], self.section.id)
        self.assertTrue(top["exact"])
        # The pinned node must not also appear as a fuzzy hit below it.
        ids = [r["node_id"] for r in body["results"]]
        self.assertEqual(ids.count(self.section.id), 1)

    def test_short_query_returns_empty_not_error(self):
        resp = self.client.get("/api/browse/search", {"q": "a"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])

    def test_unknown_source_scope_yields_no_hits(self):
        resp = self.client.get(
            "/api/browse/search",
            {"q": "consumer fraud", "source": "no-such-source"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    def test_source_scope_matches_known_source(self):
        resp = self.client.get(
            "/api/browse/search",
            {"q": "consumer fraud", "source": "iowa-code"},
        )
        body = resp.json()
        self.assertEqual(body["scope"], "iowa-code")
        self.assertGreaterEqual(body["count"], 1)


class BrowseDetailQueryCountTests(TestCase):
    """Regression guard for the N+1 fixed in chapter_detail / node_detail:
    the query count must not grow with the number of children."""

    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()
        cls.chapter = cls.section.parent
        cls.section_t = NodeType.objects.get(source=cls.source, key="section")

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def _add_sections(self, n: int, start: int = 100) -> None:
        for i in range(start, start + n):
            Node.objects.create(
                source=self.source,
                node_type=self.section_t,
                parent=self.chapter,
                ordinal=str(i),
                path=f"714.{i}",
                heading=f"Section {i}",
            )

    def _count_chapter_detail_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/browse/chapters/{self.chapter.id}")
            self.assertEqual(resp.status_code, 200)
        return len(ctx.captured_queries)

    def test_chapter_detail_query_count_is_constant_in_child_count(self):
        self._add_sections(2, start=200)
        few = self._count_chapter_detail_queries()
        self._add_sections(8, start=300)
        many = self._count_chapter_detail_queries()
        # 8 extra children must not add 8 extra queries (the N+1 symptom).
        self.assertEqual(
            few,
            many,
            f"chapter_detail issued {many} queries for 10 children vs "
            f"{few} for 2 — query count scales with children (N+1).",
        )

    def test_node_detail_query_count_is_bounded(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/browse/nodes/{self.section.id}")
            self.assertEqual(resp.status_code, 200)
        # node + version + (parent/source via select_related). Generous
        # ceiling; the point is it must not regress into per-relation fetches.
        self.assertLessEqual(
            len(ctx.captured_queries),
            5,
            f"node_detail issued {len(ctx.captured_queries)} queries: "
            f"{[q['sql'][:80] for q in ctx.captured_queries]}",
        )


class BrowseCacheHeaderTests(TestCase):
    """Browse read endpoints must be Cloudflare/browser cacheable: a shared
    Cache-Control TTL plus an ETag that drives 304 revalidation."""

    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()
        cls.chapter = cls.section.parent

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def test_detail_endpoints_are_publicly_cacheable_with_etag(self):
        for url in (
            "/api/browse/sources",
            "/api/browse/sources/iowa-code/chapters",
            f"/api/browse/chapters/{self.chapter.id}",
            f"/api/browse/nodes/{self.section.id}",
        ):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertIn("s-maxage=60", resp["Cache-Control"], url)
            self.assertIn("public", resp["Cache-Control"], url)
            self.assertTrue(resp["ETag"], url)

    def test_matching_if_none_match_returns_304(self):
        url = f"/api/browse/chapters/{self.chapter.id}"
        first = self.client.get(url)
        etag = first["ETag"]
        again = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again["ETag"], etag)
        self.assertFalse(again.content)


@tag("postgres")
class BrowseResolveAndCrossRefTests(TestCase):
    """The public citation-native permalink resolver, and the inline
    cross_refs the reader renders as clickable links."""

    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()
        cls.chapter = cls.section.parent  # 714
        cls.section_t = NodeType.objects.get(source=cls.source, key="section")
        # A second section so 714.16 can cite it.
        cls.s8 = Node.objects.create(
            source=cls.source,
            node_type=cls.section_t,
            parent=cls.chapter,
            ordinal="8",
            path="714.8",
            heading="Theft defined",
        )
        body = "Conduct that also violates section 714.8 is punishable."
        cls.s8v = NodeVersion.objects.create(
            node=cls.s8,
            body_text="Theft is the taking of property.",
            effective_from=dt.date(2025, 1, 1),
            content_hash="a" * 64,
            review_status=ReviewStatus.APPROVED,
        )
        # Repoint 714.16's current version body at one with a cross-ref.
        cls.version.body_text = body
        cls.version.save(update_fields=["body_text"])

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def test_resolve_is_public_and_returns_node_id(self):
        resp = self.client.get(
            "/api/browse/resolve", {"source": "iowa-code", "cite": "714.16"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["node_id"], self.section.id)
        self.assertEqual(data["path"], "714.16")
        self.assertFalse(data["is_chapter"])

    def test_resolve_chapter_only_citation(self):
        resp = self.client.get(
            "/api/browse/resolve", {"source": "iowa-code", "cite": "chapter 714"}
        )
        data = resp.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["node_id"], self.chapter.id)
        self.assertTrue(data["is_chapter"])

    def test_resolve_unknown_section_returns_candidates_not_a_guess(self):
        resp = self.client.get(
            "/api/browse/resolve", {"source": "iowa-code", "cite": "714.404"}
        )
        data = resp.json()
        self.assertFalse(data["found"])
        # Same-chapter near-misses are offered, never substituted.
        self.assertTrue(
            any(c["path"] in {"714.8", "714.16"} for c in data["candidates"])
        )

    def test_resolve_unknown_source_is_not_found(self):
        resp = self.client.get(
            "/api/browse/resolve", {"source": "nope", "cite": "714.16"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["found"])

    def test_node_detail_exposes_path_and_cross_refs(self):
        resp = self.client.get(f"/api/browse/nodes/{self.section.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["path"], "714.16")
        refs = data["cross_refs"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["text"], "section 714.8")
        self.assertEqual(refs[0]["path"], "714.8")
        self.assertEqual(refs[0]["node_id"], self.s8.id)

    def test_chapter_detail_exposes_path(self):
        resp = self.client.get(f"/api/browse/chapters/{self.chapter.id}")
        self.assertEqual(resp.json()["path"], "714")
