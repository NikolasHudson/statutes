"""End-to-end tests for the authed /api/research/search endpoint.

Network isolation: the query embedder is patched to the deterministic fake
(via the embedding-cache module) and the reranker to Noop, so assertions
turn on routing/contract behavior, not on live Voyage scores. The public
/api/browse/search contract is covered by test_routes and is untouched.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, tag

from apps.api.models import SearchLog
from apps.corpus.services.rerank import NoopReranker
from apps.corpus.services.voyage import FakeEmbeddingClient

from ._factories import (
    make_caselaw_case,
    make_iowa_corpus_minimal,
    make_user,
)


@tag("postgres")
class ResearchSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()
        # Three cases matching landlord+deposit, one landlord-only, with a
        # phrase that appears in exactly one body.
        cls.dec1, _, _ = make_caselaw_case(
            cl_cluster_id=1, cl_opinion_id=11, case_name="Tenant v. Landlord",
            body="The landlord withheld the security deposit without cause.",
            date_filed="2021-05-01",
        )
        cls.dec2, _, _ = make_caselaw_case(
            cl_cluster_id=2, cl_opinion_id=21, case_name="Renter v. Owner",
            body=(
                "The landlord retained the deposit after the constructive "
                "eviction of the tenant."
            ),
            date_filed="2023-08-15", court_id="iowactapp",
        )
        cls.dec3, _, _ = make_caselaw_case(
            cl_cluster_id=3, cl_opinion_id=31, case_name="Lessee v. Lessor",
            body="A deposit dispute between the landlord and the lessee.",
            date_filed="2019-02-10",
        )
        cls.dec_other, _, _ = make_caselaw_case(
            cl_cluster_id=4, cl_opinion_id=41, case_name="State v. Unrelated",
            body="The landlord appeared as a witness only.",
            date_filed="2022-01-01",
        )
        cls.user = make_user("research@example.com")

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        for target, value in (
            (
                "apps.corpus.services.embedding_cache.default_client",
                lambda: FakeEmbeddingClient(),
            ),
            (
                "apps.corpus.services.retrieval.default_reranker",
                lambda: NoopReranker(),
            ),
        ):
            patcher = mock.patch(target, side_effect=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = Client()
        self.client.force_login(self.user)

    def _get(self, **params):
        return self.client.get("/api/research/search", params)

    # -- auth / headers ----------------------------------------------------

    def test_anonymous_is_rejected(self):
        resp = Client().get("/api/research/search", {"q": "landlord"})
        self.assertEqual(resp.status_code, 401)

    def test_responses_are_never_cached(self):
        resp = self._get(q="landlord deposit dispute")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Cache-Control"], "private, no-store")

    # -- intent routing ------------------------------------------------------

    def test_natural_query_reports_mode(self):
        # Terms chosen to FTS-match dec1 (fixtures carry no embeddings, so
        # natural mode's recall here comes from the keyword retrievers).
        resp = self._get(q="landlord withheld the security deposit")
        body = resp.json()
        self.assertEqual(body["mode"], "natural")
        self.assertEqual(body["mode_source"], "auto")
        self.assertFalse(body["total_exact"])
        self.assertGreaterEqual(body["count"], 1)

    def test_boolean_query_gets_exact_total_and_pagination(self):
        resp = self._get(q="landlord AND deposit", limit=2)
        body = resp.json()
        self.assertEqual(body["mode"], "boolean")
        self.assertTrue(body["total_exact"])
        self.assertEqual(body["total"], 3)  # dec1..dec3, not the witness case
        self.assertEqual(body["count"], 2)
        self.assertTrue(body["has_more"])

        page2 = self._get(q="landlord AND deposit", limit=2, offset=2).json()
        self.assertEqual(page2["total"], 3)
        self.assertEqual(page2["count"], 1)
        self.assertFalse(page2["has_more"])
        ids = {r["case_id"] for r in body["results"]} | {
            r["case_id"] for r in page2["results"]
        }
        self.assertEqual(len(ids), 3)

    def test_unsupported_connector_is_flagged_not_silent(self):
        body = self._get(q="landlord w/5 deposit").json()
        self.assertEqual(body["mode"], "boolean")
        tokens = [u["token"] for u in body["detection"]["unsupported"]]
        self.assertEqual(tokens, ["w/5"])
        self.assertEqual(body["detection"]["unsupported"][0]["treated_as"], "AND")
        # Treated as AND: same match set as the AND query.
        self.assertEqual(body["total"], 3)

    def test_mode_override_wins_and_is_reported(self):
        body = self._get(q="landlord AND deposit", mode="natural").json()
        self.assertEqual(body["mode"], "natural")
        self.assertEqual(body["mode_source"], "user")
        tc = self._get(q="ordinary prose words", mode="tc").json()
        self.assertEqual(tc["mode"], "boolean")
        self.assertEqual(tc["mode_source"], "user")

    def test_citation_query_pins_exact_row(self):
        body = self._get(q="714.16").json()
        self.assertEqual(body["mode"], "citation")
        self.assertTrue(body["results"][0]["exact"])
        self.assertEqual(body["results"][0]["node_id"], self.section.id)

    def test_phrase_inside_natural_query_hard_filters(self):
        body = self._get(
            q='landlord deposit "constructive eviction"'
        ).json()
        self.assertEqual(body["mode"], "natural")
        self.assertGreaterEqual(body["count"], 1)
        for row in body["results"]:
            self.assertEqual(row["case_id"], self.dec2.id)

    def test_empty_boolean_group_degrades_gracefully(self):
        resp = self._get(q="()", mode="tc")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 0)

    # -- filters -------------------------------------------------------------

    def test_boolean_date_and_court_filters_shrink_honest_total(self):
        body = self._get(
            q="landlord AND deposit", date_from="2020-01-01"
        ).json()
        self.assertEqual(body["total"], 2)  # dec3 (2019) excluded
        body = self._get(q="landlord AND deposit", court="iowactapp").json()
        self.assertEqual(body["total"], 1)  # only dec2

    # -- logging -------------------------------------------------------------

    def test_search_is_logged_unattributed(self):
        self._get(q="landlord AND deposit", court="iowa")
        log = SearchLog.objects.latest("id")
        self.assertIsNone(log.user_id)  # never attributed, even when signed in
        self.assertEqual(log.mode, "boolean")
        self.assertEqual(log.query, "landlord AND deposit")
        self.assertEqual(log.filters.get("court"), "iowa")
        self.assertTrue(log.total_exact)
        self.assertIsNotNone(log.latency_ms)

    # -- Phase 2: facets / sort / segments / treatment / cited-by -------------

    def test_boolean_facets_are_exact_and_consistent(self):
        body = self._get(q="landlord AND deposit", facets="true").json()
        f = body["facets"]
        self.assertEqual(f["basis"], "all_matches")
        self.assertEqual(sum(d["count"] for d in f["doc_types"]), body["total"])
        courts = {c["court_id"]: c for c in f["courts"]}
        self.assertEqual(courts["iowactapp"]["count"], 1)  # dec2
        self.assertEqual(
            courts["iowactapp"]["court_name"], "Court of Appeals of Iowa"
        )
        decades = {d["decade"]: d["count"] for d in f["decades"]}
        self.assertEqual(decades, {"2010": 1, "2020": 2})

    def test_natural_facets_are_pool_based(self):
        body = self._get(
            q="landlord withheld the security deposit", facets="true"
        ).json()
        self.assertEqual(body["facets"]["basis"], "top_results")

    def test_date_sort_orders_and_switches_natural_to_keyword(self):
        body = self._get(q="landlord AND deposit", sort="date_desc").json()
        dates = [r["date_filed"] for r in body["results"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        nat = self._get(q="landlord deposit dispute", sort="date_desc").json()
        self.assertEqual(nat["mode"], "natural")
        self.assertEqual(nat["sort_path"], "keyword")
        self.assertTrue(nat["total_exact"])

    def test_boolean_snippet_segments_mark_hits_without_markup(self):
        body = self._get(q="landlord AND deposit").json()
        segs = body["results"][0].get("snippet_segments")
        self.assertTrue(segs)
        joined = "".join(s["text"] for s in segs)
        self.assertNotIn("\x02", joined)
        self.assertNotIn("\x03", joined)
        self.assertNotIn("<", joined)
        hit_terms = {s["text"].lower() for s in segs if s["hit"]}
        self.assertTrue(hit_terms & {"landlord", "deposit", "deposits"})

    def test_treatment_badge_only_when_flag_exists(self):
        md = dict(self.dec3.source_metadata)
        md["treatment"] = {
            "status": "negative",
            "severity": 5,
            "label": "overruled",
            "by_citation": "Later v. Case",
            "excerpt": "overruled by Later v. Case",
            "source": "graph_phrase",
            "confidence": 0.9,
        }
        self.dec3.source_metadata = md
        self.dec3.save(update_fields=["source_metadata"])
        body = self._get(q="landlord AND deposit").json()
        by_case = {r["case_id"]: r for r in body["results"]}
        self.assertEqual(by_case[self.dec3.id]["treatment"]["label"], "overruled")
        self.assertIsNone(by_case[self.dec1.id]["treatment"])

    def test_cited_by_counts_distinct_citing_decisions(self):
        from apps.corpus.models import (
            CrossReference,
            CrossReferenceKind,
            CrossReferenceSource,
            NodeVersion,
        )

        # dec2's and dec3's opinions both cite dec1's opinion.
        target_opinion = self.dec1.children.first()
        for citing_dec in (self.dec2, self.dec3):
            citing_version = NodeVersion.objects.get(
                node__parent=citing_dec, effective_to__isnull=True
            )
            CrossReference.objects.create(
                from_version=citing_version,
                to_node=target_opinion,
                kind=CrossReferenceKind.INTERNAL,
                source=CrossReferenceSource.CASELAW_GRAPH,
            )
        body = self._get(q="landlord AND deposit").json()
        by_case = {r["case_id"]: r for r in body["results"]}
        self.assertEqual(by_case[self.dec1.id]["cited_by"], 2)
        self.assertIsNone(by_case[self.dec2.id]["cited_by"])

    # -- embedding cache -------------------------------------------------------

    def test_repeat_natural_query_skips_the_embedder(self):
        calls = []
        counting = FakeEmbeddingClient()
        original = counting.embed_texts

        def counted(texts, **kw):
            calls.append(texts)
            return original(texts, **kw)

        counting.embed_texts = counted
        with mock.patch(
            "apps.corpus.services.embedding_cache.default_client",
            return_value=counting,
        ):
            self._get(q="unique repeated query about deposits")
            self._get(q="unique repeated query about deposits")
        self.assertEqual(len(calls), 1)
