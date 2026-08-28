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
    ReporterCitation,
    ReviewStatus,
)
from apps.api.browse import _normalize_fts_query
from apps.corpus.services.lookups import reset_default_source_cache

from ._factories import (
    make_api_key,
    make_caselaw_case,
    make_iowa_corpus_minimal,
    make_user,
)


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


class CaseDetailRouteTests(TestCase):
    """The public, unauthenticated /api/browse/cases/{id} caselaw endpoint."""

    @classmethod
    def setUpTestData(cls):
        # Two cases: A cites B (internal) plus one out-of-corpus cite (external).
        cls.decision_a, cls.opinion_a, cls.version_a = make_caselaw_case(
            cl_cluster_id=100,
            cl_opinion_id=1000,
            body="HECHT, Justice. We affirm. See the other case.",
        )
        cls.decision_b, cls.opinion_b, _ = make_caselaw_case(
            cl_cluster_id=200, cl_opinion_id=2000, body="Body of the cited case."
        )
        # Head-matter lives on the decision node's own version.
        NodeVersion.objects.create(
            node=cls.decision_a,
            body_text="Syllabus\n\nThe syllabus of the case.",
            effective_from=dt.date(2020, 1, 1),
            content_hash="headmatter-a",
            review_status=ReviewStatus.APPROVED,
        )
        CrossReference.objects.create(
            from_version=cls.version_a,
            to_node=cls.opinion_b,
            kind=CrossReferenceKind.INTERNAL,
            source="caselaw_link",
        )
        CrossReference.objects.create(
            from_version=cls.version_a,
            to_node=None,
            external_text="920 N.W.2d 520",
            kind=CrossReferenceKind.EXTERNAL,
            source="caselaw_link",
        )

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def test_case_detail_is_public_and_shaped(self):
        resp = self.client.get(f"/api/browse/cases/{self.decision_a.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], self.decision_a.id)
        self.assertEqual(data["case_name"], "State v. Example")
        self.assertEqual(data["court_id"], "iowa")
        self.assertEqual(data["cl_cluster_id"], 100)
        self.assertEqual(len(data["opinions"]), 1)
        op = data["opinions"][0]
        self.assertEqual(op["heading"], "Lead Opinion")
        self.assertIn("HECHT", op["body_text"])
        self.assertTrue(op["has_content"])

    def test_case_detail_includes_head_matter(self):
        resp = self.client.get(f"/api/browse/cases/{self.decision_a.id}")
        self.assertIn("Syllabus", resp.json()["head_matter"])

    def test_case_detail_lists_cited_cases_and_external_count(self):
        data = self.client.get(f"/api/browse/cases/{self.decision_a.id}").json()
        self.assertEqual(len(data["cited_cases"]), 1)
        cited = data["cited_cases"][0]
        # Internal edge targets the cited OPINION; the panel links to its case.
        self.assertEqual(cited["case_id"], self.decision_b.id)
        self.assertEqual(cited["count"], 1)
        self.assertEqual(data["external_citation_count"], 1)

    def test_decision_with_no_head_matter_is_null(self):
        resp = self.client.get(f"/api/browse/cases/{self.decision_b.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["head_matter"])

    def test_non_decision_node_is_404(self):
        # An opinion node id must not resolve as a case (decision-keyed route).
        resp = self.client.get(f"/api/browse/cases/{self.opinion_a.id}")
        self.assertEqual(resp.status_code, 404)

    def test_combined_opinion_is_deduped_and_caption_lifted(self):
        # A 010combined opinion that duplicates the separate opinions is dropped
        # from the response; its prefatory caption is lifted into caption_block.
        src = self.decision_a.source
        dtype = self.decision_a.node_type
        otype = self.opinion_a.node_type
        decision = Node.objects.create(
            source=src, node_type=dtype, ordinal="900",
            path="cl-cluster-900", heading="State v. Combined",
            source_metadata={"cl_cluster_id": 900, "court_id": "iowa"},
        )
        caption = "IN THE SUPREME COURT OF IOWA\n\nNo. 99\n\nSTATE OF IOWA,\n\nvs.\n\nJOHN DOE,\n"
        lead_body = "HECHT, Justice.\nWe affirm."
        combined = Node.objects.create(
            source=src, node_type=otype, parent=decision, ordinal="010",
            path="cl-cluster-900/op-1", heading="Opinion",
            source_metadata={"cl_opinion_id": 1, "type": "010combined"},
        )
        NodeVersion.objects.create(
            node=combined, body_text=caption + "\n" + lead_body,
            effective_from=dt.date(2020, 1, 1), content_hash="combined-900",
            review_status=ReviewStatus.APPROVED,
        )
        lead = Node.objects.create(
            source=src, node_type=otype, parent=decision, ordinal="020",
            path="cl-cluster-900/op-2", heading="Lead Opinion (Hecht)",
            source_metadata={"cl_opinion_id": 2, "type": "020lead"},
        )
        NodeVersion.objects.create(
            node=lead, body_text=lead_body,
            effective_from=dt.date(2020, 1, 1), content_hash="lead-900",
            review_status=ReviewStatus.APPROVED,
        )
        data = self.client.get(f"/api/browse/cases/{decision.id}").json()
        self.assertEqual(
            [o["heading"] for o in data["opinions"]], ["Lead Opinion (Hecht)"]
        )
        self.assertIn("IN THE SUPREME COURT OF IOWA", data["caption_block"])
        self.assertNotIn("HECHT", data["caption_block"])

    def test_single_opinion_caption_is_lifted_and_body_trimmed(self):
        src = self.decision_b.source
        dtype = self.decision_b.node_type
        otype = self.opinion_b.node_type
        decision = Node.objects.create(
            source=src, node_type=dtype, ordinal="901",
            path="cl-cluster-901", heading="State v. Solo",
            source_metadata={"cl_cluster_id": 901, "court_id": "iowa"},
        )
        body = (
            "IN THE SUPREME COURT OF IOWA\n\nNo. 12\n\n"
            "MANSFIELD, Justice.\nThe judgment is affirmed."
        )
        op = Node.objects.create(
            source=src, node_type=otype, parent=decision, ordinal="010",
            path="cl-cluster-901/op-9", heading="Opinion",
            source_metadata={"cl_opinion_id": 9, "type": "010combined"},
        )
        NodeVersion.objects.create(
            node=op, body_text=body, effective_from=dt.date(2020, 1, 1),
            content_hash="solo-901", review_status=ReviewStatus.APPROVED,
        )
        data = self.client.get(f"/api/browse/cases/{decision.id}").json()
        self.assertIn("IN THE SUPREME COURT OF IOWA", data["caption_block"])
        self.assertEqual(len(data["opinions"]), 1)
        self.assertNotIn("IN THE SUPREME COURT", data["opinions"][0]["body_text"])
        self.assertIn("MANSFIELD, Justice.", data["opinions"][0]["body_text"])


@tag("postgres")
class CaseCitatorTests(TestCase):
    """Citator fields on /api/browse/cases/{id} and the /citing sub-route:
    incoming graph edges folded per citing decision (duplicate imports
    collapsed), the cached treatment flag passed through, hover-card fields
    on cited authorities."""

    @classmethod
    def setUpTestData(cls):
        # Target T is cited (graph edges) by C1 (2020, iowa), C2 (2023, COA)
        # and C2-dup — CourtListener's amended re-report of C2 (same court,
        # same date, same docket with a "n / " prefix, no reporter cite).
        cls.target, cls.t_op, cls.t_ver = make_caselaw_case(
            cl_cluster_id=300, cl_opinion_id=3000, case_name="Target v. Case",
            date_filed="2010-05-05", citations=["500 N.W.2d 1"],
        )
        cls.c1, cls.c1_op, cls.c1_ver = make_caselaw_case(
            cl_cluster_id=301, cl_opinion_id=3010, case_name="First v. Citer",
            date_filed="2020-01-15", docket_number="19-0001",
            citations=["900 N.W.2d 10", "2020 WL 1"],
        )
        cls.c2, cls.c2_op, cls.c2_ver = make_caselaw_case(
            cl_cluster_id=302, cl_opinion_id=3020, court_id="iowactapp",
            case_name="Second v. Citer", date_filed="2023-03-03",
            docket_number="22–0500", citations=["980 N.W.2d 5"],
        )
        cls.c2dup, cls.c2dup_op, cls.c2dup_ver = make_caselaw_case(
            cl_cluster_id=303, cl_opinion_id=3030, court_id="iowactapp",
            case_name="Amended April 1, 2023 Second v. Citer",
            date_filed="2023-03-03", docket_number="7 / 22-0500",
        )
        for ver, w in ((cls.c1_ver, 2), (cls.c2_ver, 3), (cls.c2dup_ver, 1)):
            CrossReference.objects.create(
                from_version=ver, to_node=cls.t_op, weight=w,
                kind=CrossReferenceKind.INTERNAL, source="caselaw_graph",
            )
        # T cites C1 inline (the authorities rail), and C1 is cited by T in
        # the graph too so its hover card has a cited_by count.
        CrossReference.objects.create(
            from_version=cls.t_ver, to_node=cls.c1_op,
            kind=CrossReferenceKind.INTERNAL, source="caselaw_link",
        )
        CrossReference.objects.create(
            from_version=cls.t_ver, to_node=cls.c1_op, weight=1,
            kind=CrossReferenceKind.INTERNAL, source="caselaw_graph",
        )
        cls.c1.source_metadata["treatment"] = {
            "status": "negative", "severity": 5, "label": "overruled",
            "by_citation": "Later v. Court", "excerpt": "First is overruled.",
            "source": "graph_phrase", "confidence": 0.8,
        }
        cls.c1.save(update_fields=["source_metadata"])

    def setUp(self):
        self.client = Client()

    def test_detail_folds_duplicate_imports_and_keeps_raw_count(self):
        data = self.client.get(f"/api/browse/cases/{self.target.id}").json()
        self.assertEqual(data["citing_count"], 3)  # raw, matches /results
        self.assertEqual(data["citing_folded_count"], 2)
        rows = data["citing_decisions"]
        self.assertEqual([r["case_id"] for r in rows], [self.c2.id, self.c1.id])
        c2 = rows[0]
        # Representative = the import with the reporter cite; depth summed.
        self.assertEqual(c2["citation"], "980 N.W.2d 5")
        self.assertEqual(c2["case_name"], "Second v. Citer")
        self.assertEqual(c2["depth"], 4)
        self.assertEqual(c2["folded"], 2)
        self.assertEqual(c2["court_id"], "iowactapp")
        self.assertEqual(c2["court_level"], 2)
        c1 = rows[1]
        self.assertEqual(c1["citation"], "900 N.W.2d 10")  # WL cite skipped
        self.assertEqual(c1["depth"], 2)

    def test_detail_treatment_is_null_without_flag_and_passed_through(self):
        data = self.client.get(f"/api/browse/cases/{self.target.id}").json()
        self.assertIsNone(data["treatment"])
        flagged = self.client.get(f"/api/browse/cases/{self.c1.id}").json()
        self.assertEqual(flagged["treatment"]["status"], "negative")
        self.assertEqual(flagged["treatment"]["label"], "overruled")
        self.assertEqual(flagged["treatment"]["by_citation"], "Later v. Court")

    def test_cited_cases_carry_hover_card_fields(self):
        data = self.client.get(f"/api/browse/cases/{self.target.id}").json()
        self.assertEqual(len(data["cited_cases"]), 1)
        row = data["cited_cases"][0]
        self.assertEqual(row["case_id"], self.c1.id)
        self.assertEqual(row["citation"], "900 N.W.2d 10")
        self.assertEqual(row["date_filed"], "2020-01-15")
        self.assertEqual(row["court_id"], "iowa")
        self.assertEqual(row["cited_by"], 1)  # T → C1 graph edge
        self.assertEqual(row["treatment"]["label"], "overruled")

    def test_citing_route_filters_sorts_and_pages(self):
        base = f"/api/browse/cases/{self.target.id}/citing"
        data = self.client.get(base).json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["citing_count"], 3)
        self.assertEqual(
            [(c["court_id"], c["count"]) for c in data["courts"]],
            [("iowa", 1), ("iowactapp", 1)],
        )
        self.assertEqual(data["results"][0]["case_id"], self.c2.id)

        oldest = self.client.get(base, {"sort": "oldest"}).json()
        self.assertEqual(oldest["results"][0]["case_id"], self.c1.id)

        depth = self.client.get(base, {"sort": "depth"}).json()
        self.assertEqual([r["case_id"] for r in depth["results"]],
                         [self.c2.id, self.c1.id])

        coa = self.client.get(base, {"court": "iowactapp"}).json()
        self.assertEqual([r["case_id"] for r in coa["results"]], [self.c2.id])
        self.assertEqual(coa["total"], 1)
        # Facets ignore the court filter so the chips stay stable.
        self.assertEqual(len(coa["courts"]), 2)

        page = self.client.get(base, {"limit": 1, "offset": 1}).json()
        self.assertEqual([r["case_id"] for r in page["results"]], [self.c1.id])
        self.assertFalse(page["has_more"])
        first = self.client.get(base, {"limit": 1}).json()
        self.assertTrue(first["has_more"])

    def test_citing_route_rejects_bad_sort_and_non_decisions(self):
        base = f"/api/browse/cases/{self.target.id}/citing"
        data = self.client.get(base, {"sort": "bogus"}).json()
        self.assertEqual(data["sort"], "recent")
        resp = self.client.get(f"/api/browse/cases/{self.t_op.id}/citing")
        self.assertEqual(resp.status_code, 404)

    def test_uncited_case_has_empty_citator(self):
        data = self.client.get(f"/api/browse/cases/{self.c2.id}").json()
        self.assertEqual(data["citing_count"], 0)
        self.assertEqual(data["citing_decisions"], [])
        self.assertIsNone(data["treatment"])


@tag("postgres")
class BrowseAdvancedSearchTests(TestCase):
    """The fielded /api/browse/search: caselaw hits carry a kind + decision id,
    statute hits don't; doc_type/court/date filters scope; caselaw rows dedup."""

    @classmethod
    def setUpTestData(cls):
        # Statute "Consumer fraud" (714.16) — body mentions "merchant"/"deceptive".
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()
        # Two statutes whose HEADINGS would fuzzy-match (trigram) but whose
        # bodies contain none of the query terms — used to prove trigram is
        # gated off for multi-word queries and on for single-term typos.
        sec_t, chap = cls.section.node_type, cls.section.parent
        cls.appeal = Node.objects.create(
            source=cls.source, node_type=sec_t, parent=chap,
            ordinal="33", path="450.33", heading="Appeal and notice",
        )
        NodeVersion.objects.create(
            node=cls.appeal, body_text="Service shall be made within sixty days.",
            effective_from=dt.date(2025, 1, 1), content_hash="appeal-x",
            review_status=ReviewStatus.APPROVED,
        )
        cls.incorp = Node.objects.create(
            source=cls.source, node_type=sec_t, parent=chap,
            ordinal="1", path="490.1", heading="Incorporation",
        )
        NodeVersion.objects.create(
            node=cls.incorp, body_text="A corporation is formed by filing articles.",
            effective_from=dt.date(2025, 1, 1), content_hash="incorp-x",
            review_status=ReviewStatus.APPROVED,
        )
        # Iowa Supreme Court decision sharing those terms + "fraud"/"negligence".
        cls.dec_iowa, cls.op_iowa, _ = make_caselaw_case(
            cl_cluster_id=300,
            cl_opinion_id=3000,
            court_id="iowa",
            date_filed="2020-01-01",
            case_name="State v. Merchant",
            body="The merchant defendant committed a deceptive fraud through negligence.",
        )
        # Second opinion of the SAME decision, also matching "fraud" — exercises
        # the dedup (multiple opinion hits collapse to one case row).
        op2 = Node.objects.create(
            source=cls.dec_iowa.source,
            node_type=cls.op_iowa.node_type,
            parent=cls.dec_iowa,
            ordinal="030",
            path="cl-cluster-300/op-3001",
            heading="Dissent",
            source_metadata={"cl_opinion_id": 3001},
        )
        NodeVersion.objects.create(
            node=op2,
            body_text="A separate opinion also discussing fraud at length.",
            effective_from=dt.date(2020, 1, 1),
            content_hash="op2-300",
            review_status=ReviewStatus.APPROVED,
        )
        # Court of Appeals decision (different court + later date) matching
        # "negligence" — exercises the court + date filters.
        cls.dec_app, cls.op_app, _ = make_caselaw_case(
            cl_cluster_id=400,
            cl_opinion_id=4000,
            court_id="iowactapp",
            date_filed="2021-06-15",
            case_name="Appeal v. Negligence",
            body="On appeal we address the negligence claim and reverse.",
        )
        # Decision whose HEAD-MATTER (on the decision node itself) is the only
        # place a distinctive term appears — a decision-level search hit.
        cls.dec_head, _, _ = make_caselaw_case(
            cl_cluster_id=500,
            cl_opinion_id=5000,
            court_id="iowa",
            date_filed="2020-05-05",
            case_name="In re Quokka",
            body="Opinion body about an unrelated topic.",
            head_matter="Syllabus. The court addresses quokka jurisprudence.",
        )

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def _results(self, **params):
        resp = self.client.get("/api/browse/search", params)
        self.assertEqual(resp.status_code, 200)
        return resp.json()["results"]

    def test_caselaw_opinion_hit_has_case_kind_and_decision_id(self):
        rows = self._results(q="deceptive merchant", doc_type="cases")
        self.assertTrue(rows)
        self.assertTrue(all(r["kind"] == "case" for r in rows))
        merchant = next(r for r in rows if r["case_id"] == self.dec_iowa.id)
        # case_id is the DECISION (not the opinion) and case_name is the decision
        # heading, not the opinion's "Lead Opinion".
        self.assertEqual(merchant["case_name"], "State v. Merchant")
        self.assertEqual(merchant["court_name"], "Supreme Court of Iowa")
        self.assertEqual(merchant["date_filed"], "2020-01-01")

    def test_statute_hit_has_code_kind_and_null_case_id(self):
        rows = self._results(q="deceptive merchant")  # unscoped → mixed
        statute = next(r for r in rows if r["source_slug"] == "iowa-code")
        self.assertEqual(statute["kind"], "code")
        self.assertIsNone(statute["case_id"])

    def test_doc_type_scopes_out_other_corpora(self):
        rows = self._results(q="deceptive merchant", doc_type="code")
        self.assertTrue(rows)
        self.assertTrue(all(r["kind"] == "code" for r in rows))
        self.assertFalse(any(r["kind"] == "case" for r in rows))

    def test_decision_head_matter_hit_resolves_to_self(self):
        rows = self._results(q="quokka", doc_type="cases")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["kind"], "case")
        self.assertEqual(rows[0]["case_id"], self.dec_head.id)

    def test_multiple_opinions_of_one_case_dedup(self):
        rows = self._results(q="fraud", doc_type="cases")
        hits = [r for r in rows if r["case_id"] == self.dec_iowa.id]
        self.assertEqual(len(hits), 1)

    def test_court_filter_scopes_results(self):
        rows = self._results(q="negligence", doc_type="cases", court="iowactapp")
        ids = {r["case_id"] for r in rows}
        self.assertIn(self.dec_app.id, ids)
        self.assertNotIn(self.dec_iowa.id, ids)

    def test_date_range_filter_scopes_results(self):
        rows = self._results(
            q="negligence", doc_type="cases", date_from="2021-01-01"
        )
        ids = {r["case_id"] for r in rows}
        self.assertIn(self.dec_app.id, ids)  # 2021
        self.assertNotIn(self.dec_iowa.id, ids)  # 2020

    def test_normalize_fts_query_maps_boolean_operators(self):
        self.assertEqual(_normalize_fts_query("justice AND apple"), "justice apple")
        self.assertEqual(_normalize_fts_query("a OR b"), "a or b")
        self.assertEqual(_normalize_fts_query("theft NOT vehicle"), "theft -vehicle")
        # Ordinary text (incl. a party name) is untouched.
        self.assertEqual(_normalize_fts_query("Anderson Trucking"), "Anderson Trucking")

    def test_multiword_query_skips_fuzzy_trigram_headings(self):
        # "justice apple" matches no body; the appeal/incorporation headings would
        # only surface via trigram fuzz, which must be OFF for a multi-word query.
        ids = {r["node_id"] for r in self._results(q="justice apple")}
        self.assertNotIn(self.appeal.id, ids)
        self.assertNotIn(self.incorp.id, ids)

    def test_single_term_typo_still_uses_trigram(self):
        # A one-word typo must still fuzzy-match its heading (trigram ON).
        ids = {r["node_id"] for r in self._results(q="incorporaton")}
        self.assertIn(self.incorp.id, ids)


@tag("postgres")
class BrowseCasesListRouteTests(TestCase):
    """The public, unauthenticated /api/browse/cases list endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.a, *_ = make_caselaw_case(
            cl_cluster_id=11, cl_opinion_id=110, court_id="iowa",
            date_filed="2020-01-01", case_name="Case A",
        )
        cls.b, *_ = make_caselaw_case(
            cl_cluster_id=12, cl_opinion_id=120, court_id="iowactapp",
            date_filed="2021-06-15", case_name="Case B",
        )
        cls.c, *_ = make_caselaw_case(
            cl_cluster_id=13, cl_opinion_id=130, court_id="iowa",
            date_filed="2019-03-03", case_name="Case C",
        )
        cls.d, *_ = make_caselaw_case(
            cl_cluster_id=14, cl_opinion_id=140, court_id="iowactapp",
            date_filed="2022-11-20", case_name="Case D",
        )

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def test_lists_decisions_newest_first(self):
        data = self.client.get("/api/browse/cases").json()
        dates = [r["date_filed"] for r in data["results"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(data["results"][0]["date_filed"], "2022-11-20")
        self.assertEqual(data["results"][0]["court_level"], 2)  # Ct. App.

    def test_court_filter(self):
        data = self.client.get(
            "/api/browse/cases", {"court": "iowactapp"}
        ).json()
        ids = {r["id"] for r in data["results"]}
        self.assertEqual(ids, {self.b.id, self.d.id})

    def test_date_range_filter(self):
        data = self.client.get(
            "/api/browse/cases",
            {"date_from": "2020-01-01", "date_to": "2021-12-31"},
        ).json()
        self.assertEqual({r["id"] for r in data["results"]}, {self.a.id, self.b.id})

    def test_year_filter(self):
        data = self.client.get("/api/browse/cases", {"year": 2021}).json()
        self.assertEqual({r["id"] for r in data["results"]}, {self.b.id})

    def test_pagination_has_more(self):
        page1 = self.client.get("/api/browse/cases", {"limit": 2}).json()
        self.assertEqual(len(page1["results"]), 2)
        self.assertTrue(page1["has_more"])
        page2 = self.client.get(
            "/api/browse/cases", {"limit": 2, "offset": 2}
        ).json()
        self.assertEqual(len(page2["results"]), 2)
        self.assertFalse(page2["has_more"])

    def test_facets_count_by_court(self):
        data = self.client.get("/api/browse/cases", {"facets": "true"}).json()
        counts = {c["court_id"]: c["count"] for c in data["facets"]["courts"]}
        self.assertEqual(counts.get("iowa"), 2)
        self.assertEqual(counts.get("iowactapp"), 2)

    def test_facets_honor_active_date_range(self):
        # Facet counts must reflect the date filter (chips match the list), but
        # NOT the court pivot. Window 2020-2021 keeps A (iowa) + B (iowactapp).
        data = self.client.get(
            "/api/browse/cases",
            {"facets": "true", "date_from": "2020-01-01", "date_to": "2021-12-31"},
        ).json()
        counts = {c["court_id"]: c["count"] for c in data["facets"]["courts"]}
        self.assertEqual(counts.get("iowa"), 1)
        self.assertEqual(counts.get("iowactapp"), 1)

    def test_public_cacheable_with_etag_and_304(self):
        first = self.client.get("/api/browse/cases")
        self.assertIn("s-maxage=60", first["Cache-Control"])
        etag = first["ETag"]
        self.assertTrue(etag)
        again = self.client.get("/api/browse/cases", HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(again.status_code, 304)


@tag("postgres")
class BrowseSourcesListTests(TestCase):
    """list_sources must not report a chapter-less source (caselaw) as having
    76k 'chapters'; it should surface kind + decision counts instead."""

    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()
        make_caselaw_case(cl_cluster_id=21, cl_opinion_id=210)
        make_caselaw_case(cl_cluster_id=22, cl_opinion_id=220)

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def test_caselaw_source_reports_decisions_not_chapters(self):
        rows = self.client.get("/api/browse/sources").json()
        by_slug = {r["slug"]: r for r in rows}
        caselaw = by_slug["iowa-caselaw"]
        self.assertEqual(caselaw["kind"], "caselaw")
        self.assertFalse(caselaw["has_chapters"])
        self.assertEqual(caselaw["chapters"], 0)
        self.assertEqual(caselaw["entry_label"], "Decisions")
        self.assertEqual(caselaw["entries"], 2)

    def test_statute_source_still_reports_chapters(self):
        rows = self.client.get("/api/browse/sources").json()
        code = {r["slug"]: r for r in rows}["iowa-code"]
        self.assertEqual(code["kind"], "statutes")
        self.assertTrue(code["has_chapters"])
        self.assertGreaterEqual(code["chapters"], 1)


@tag("postgres")
class BrowseSearchCitationTests(TestCase):
    """Reporter-citation pinning + citations on caselaw result rows."""

    @classmethod
    def setUpTestData(cls):
        cls.dec, cls.op, cls.ver = make_caselaw_case(
            cl_cluster_id=700,
            cl_opinion_id=7000,
            court_id="iowa",
            case_name="Pinned v. Citation",
            citations=["999 N.W.2d 123"],
            body="An opinion discussing widget liability at length.",
        )
        ReporterCitation.objects.create(
            cl_citation_id=999123,
            cl_cluster_id=700,
            reporter="N.W.2d",
            volume="999",
            page="123",
            to_node=cls.dec,
        )

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def test_reporter_citation_is_pinned_first(self):
        body = self.client.get(
            "/api/browse/search", {"q": "999 N.W.2d 123"}
        ).json()
        self.assertTrue(body["results"])
        top = body["results"][0]
        self.assertEqual(top["kind"], "case")
        self.assertEqual(top["case_id"], self.dec.id)
        self.assertTrue(top["exact"])

    def test_ambiguous_reporter_citation_is_not_pinned(self):
        # A second case sharing the exact triple makes it ambiguous -> no pin.
        dec2, *_ = make_caselaw_case(
            cl_cluster_id=701, cl_opinion_id=7001, body="Other body."
        )
        ReporterCitation.objects.create(
            cl_citation_id=999124, cl_cluster_id=701, reporter="N.W.2d",
            volume="999", page="123", to_node=dec2,
        )
        body = self.client.get(
            "/api/browse/search", {"q": "999 N.W.2d 123"}
        ).json()
        self.assertFalse(any(r["exact"] for r in body["results"]))

    def test_caselaw_row_includes_citations(self):
        body = self.client.get(
            "/api/browse/search", {"q": "widget liability", "doc_type": "cases"}
        ).json()
        row = next(r for r in body["results"] if r["case_id"] == self.dec.id)
        self.assertIn("999 N.W.2d 123", row["citations"])


@tag("postgres")
class BrowseSearchPaginationTests(TestCase):
    """offset/limit paging over the search results, with stable, disjoint pages."""

    @classmethod
    def setUpTestData(cls):
        cls.ids = []
        for i in range(6):
            dec, _, _ = make_caselaw_case(
                cl_cluster_id=800 + i,
                cl_opinion_id=8000 + i,
                court_id="iowa",
                case_name=f"Embez Case {i}",
                date_filed=f"20{10 + i:02d}-01-01",
                body="The defendant committed embezzlement of public funds.",
            )
            cls.ids.append(dec.id)

    def setUp(self):
        cache.clear()
        reset_default_source_cache()
        self.client = Client()

    def _page(self, offset):
        return self.client.get(
            "/api/browse/search",
            {"q": "embezzlement", "doc_type": "cases", "limit": 2, "offset": offset},
        ).json()

    def test_pages_are_disjoint_cover_all_and_signal_has_more(self):
        p0, p2, p4 = self._page(0), self._page(2), self._page(4)
        self.assertEqual(len(p0["results"]), 2)
        self.assertTrue(p0["has_more"])
        self.assertTrue(p2["has_more"])
        self.assertFalse(p4["has_more"])  # 6 cases, offset 4 is the last page
        ids0 = {r["case_id"] for r in p0["results"]}
        ids2 = {r["case_id"] for r in p2["results"]}
        ids4 = {r["case_id"] for r in p4["results"]}
        self.assertEqual(ids0 & ids2, set())
        self.assertEqual(ids0 & ids4, set())
        self.assertEqual(ids2 & ids4, set())
        self.assertEqual(ids0 | ids2 | ids4, set(self.ids))

    def test_pages_are_stable_across_requests(self):
        self.assertEqual(
            [r["case_id"] for r in self._page(2)["results"]],
            [r["case_id"] for r in self._page(2)["results"]],
        )
