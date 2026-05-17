"""Hybrid search retrievers and RRF fusion.

These tests use a small synthetic corpus instead of the Iowa probe sample —
keeps assertions tight and fast."""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, tag

from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    ReviewStatus,
    Source,
)
from apps.corpus.services.embeddings import run_embedding_job
from apps.corpus.services.search import (
    fts_search,
    hybrid_search,
    reciprocal_rank_fusion,
    trigram_search,
    vector_search,
)
from apps.corpus.services.voyage import FakeEmbeddingClient


def _make_corpus(source: Source, node_type: NodeType, rows: list[tuple[str, str, str]]):
    """rows = [(path, heading, body), ...]"""
    out: list[NodeVersion] = []
    for path, heading, body in rows:
        node = Node.objects.create(
            source=source,
            node_type=node_type,
            ordinal=path.split(".", 1)[-1],
            path=path,
            heading=heading,
        )
        nv = NodeVersion.objects.create(
            node=node,
            body_text=body,
            effective_from=dt.date(2026, 1, 1),
            content_hash=f"h-{path}",
            review_status=ReviewStatus.APPROVED,
        )
        out.append(nv)
    return out


@tag("postgres")
class SearchRetrieverTests(TestCase):
    def setUp(self):
        j = Jurisdiction.objects.create(slug="j", name="J", abbreviation="J")
        self.source = Source.objects.create(
            jurisdiction=j, slug="s", name="S", citation_abbreviation="S"
        )
        self.nt = NodeType.objects.create(
            source=self.source, key="section", label_singular="Section", level=1
        )
        self.versions = _make_corpus(
            self.source,
            self.nt,
            [
                ("714.16", "Consumer fraud",
                 "A merchant who commits a deceptive practice or unfair "
                 "method of competition violates this section."),
                ("562A.21", "Tenant remedies for noncompliance",
                 "If the landlord fails to maintain the dwelling, the tenant "
                 "may give notice and terminate the rental agreement."),
                ("232.2", "Definitions of juvenile justice",
                 "As used in this chapter, 'child' means an unmarried person "
                 "under eighteen years of age."),
                ("724.4", "Carrying weapons",
                 "A person who carries a dangerous weapon concealed on the "
                 "person commits an aggravated misdemeanor."),
            ],
        )

    def test_fts_finds_keyword_match(self):
        results = fts_search("deceptive practice")
        ids = [r[0] for r in results]
        self.assertIn(self.versions[0].id, ids)

    def test_fts_orders_better_match_first(self):
        results = fts_search("tenant landlord")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0][0], self.versions[1].id)

    def test_fts_excludes_pending_by_default(self):
        v = self.versions[0]
        v.review_status = ReviewStatus.PENDING
        v.save(update_fields=["review_status"])
        ids = [r[0] for r in fts_search("deceptive practice")]
        self.assertNotIn(v.id, ids)
        ids_pending = [r[0] for r in fts_search("deceptive practice", include_pending=True)]
        self.assertIn(v.id, ids_pending)

    def test_fts_excludes_closed_versions(self):
        v = self.versions[0]
        v.effective_to = dt.date(2026, 6, 1)
        v.save(update_fields=["effective_to"])
        ids = [r[0] for r in fts_search("deceptive practice")]
        self.assertNotIn(v.id, ids)

    def test_trigram_handles_typo(self):
        # "juvenil" missing one character; pg_trgm should still match.
        results = trigram_search("juvenil")
        ids = [r[0] for r in results]
        self.assertIn(self.versions[2].id, ids)

    def test_trigram_weights_heading_over_body(self):
        # "Consumer" appears in heading of section 714.16; trigram should
        # rank it above any body-only match.
        results = trigram_search("consumer")
        self.assertEqual(results[0][0], self.versions[0].id)

    def test_vector_search_returns_results(self):
        run_embedding_job(client=FakeEmbeddingClient())
        results = vector_search("anything", client=FakeEmbeddingClient(), limit=5)
        self.assertEqual(len(results), 4)
        # Score is similarity in [0, 2] (1 - cosine_distance with values in [-1,1]).
        for _, score in results:
            self.assertLessEqual(score, 2.0)
            self.assertGreaterEqual(score, -1.0)

    def test_hybrid_search_combines_retrievers(self):
        run_embedding_job(client=FakeEmbeddingClient())
        # FakeEmbeddingClient produces hash vectors with no semantic meaning,
        # so the vector retriever is pure noise here. Use a query the two
        # meaningful retrievers agree on (heading "Consumer fraud" → both FTS
        # weight-A and heading trigram point at 714.16) so the assertion tests
        # RRF fusion, not which doc the fake vectors happened to hash near.
        hits = hybrid_search(
            "consumer fraud",
            client=FakeEmbeddingClient(),
            limit=5,
        )
        self.assertGreater(len(hits), 0)
        top = hits[0]
        self.assertEqual(top.path, "714.16")
        self.assertGreater(top.score, 0)
        self.assertIn("fts", top.component_scores)

    def test_hybrid_search_without_vector(self):
        hits = hybrid_search("tenant landlord", limit=5, use_vector=False)
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].path, "562A.21")
        for hit in hits:
            self.assertNotIn("vector", hit.component_scores)


@tag("postgres")
class SourceScopedSearchTests(TestCase):
    """source_slug must scope every retriever to one corpus, so an ethics
    question asked against the Court Rules never bleeds into the Code."""

    def setUp(self):
        j = Jurisdiction.objects.create(slug="ia", name="Iowa", abbreviation="IA")
        self.code = Source.objects.create(
            jurisdiction=j, slug="iowa-code", name="Iowa Code",
            citation_abbreviation="Iowa Code",
        )
        self.rules = Source.objects.create(
            jurisdiction=j, slug="iowa-court-rules", name="Iowa Court Rules",
            citation_abbreviation="Iowa Ct. R.",
        )
        code_nt = NodeType.objects.create(
            source=self.code, key="section", label_singular="Section", level=1
        )
        rules_nt = NodeType.objects.create(
            source=self.rules, key="rule", label_singular="Rule", level=1
        )
        # Same load-bearing word ("conflict") in both corpora.
        [self.code_v] = _make_corpus(
            self.code, code_nt,
            [("68B.2A", "Conflict of interest in public office",
              "A public official shall not have a conflict of interest "
              "in the discharge of official duties.")],
        )
        [self.rule_v] = _make_corpus(
            self.rules, rules_nt,
            [("32:1.7", "Conflict of interest current clients",
              "A lawyer shall not represent a client if the representation "
              "involves a concurrent conflict of interest.")],
        )

    def test_fts_scoped_to_source(self):
        ids = [r[0] for r in fts_search("conflict of interest")]
        self.assertCountEqual(ids, [self.code_v.id, self.rule_v.id])
        scoped = [
            r[0]
            for r in fts_search("conflict of interest", source_slug="iowa-court-rules")
        ]
        self.assertEqual(scoped, [self.rule_v.id])

    def test_trigram_scoped_to_source(self):
        scoped = [
            r[0]
            for r in trigram_search("conflict", source_slug="iowa-code")
        ]
        self.assertEqual(scoped, [self.code_v.id])

    def test_vector_scoped_to_source(self):
        run_embedding_job(client=FakeEmbeddingClient())
        scoped = vector_search(
            "conflict",
            client=FakeEmbeddingClient(),
            source_slug="iowa-court-rules",
        )
        self.assertEqual([r[0] for r in scoped], [self.rule_v.id])

    def test_hybrid_scoped_to_source(self):
        run_embedding_job(client=FakeEmbeddingClient())
        hits = hybrid_search(
            "conflict of interest",
            client=FakeEmbeddingClient(),
            source_slug="iowa-court-rules",
        )
        self.assertEqual([h.path for h in hits], ["32:1.7"])

    def test_unknown_source_slug_yields_nothing(self):
        self.assertEqual(fts_search("conflict", source_slug="nope"), [])


@tag("postgres")
class LookupCitationScopeTests(TestCase):
    """lookup_citation defaults to the Iowa Code; a Court Rule citation must
    still resolve — scoped to the rules source, or cross-source when the chat
    is unscoped. Regression for the "technical issue" on Rule 1.303."""

    def setUp(self):
        from apps.mcp_server.tools import lookup_citation_tool

        self.lookup = lookup_citation_tool
        j = Jurisdiction.objects.create(slug="ia", name="Iowa", abbreviation="IA")
        self.code = Source.objects.create(
            jurisdiction=j, slug="iowa-code", name="Iowa Code",
            citation_abbreviation="Iowa Code",
        )
        self.rules = Source.objects.create(
            jurisdiction=j, slug="iowa-court-rules", name="Iowa Court Rules",
            citation_abbreviation="Iowa Ct. R.",
        )
        code_nt = NodeType.objects.create(
            source=self.code, key="section", label_singular="Section", level=1
        )
        rule_nt = NodeType.objects.create(
            source=self.rules, key="rule", label_singular="Rule", level=1
        )
        _make_corpus(self.code, code_nt,
                     [("9.1", "Iowa Code section nine one", "Code body.")])
        _make_corpus(self.rules, rule_nt,
                     [("1.303", "Time for motion or answer to petition",
                       "The defendant shall serve a motion or answer within "
                       "20 days after service of the original notice.")])

    def test_scoped_lookup_resolves_court_rule(self):
        out = self.lookup("1.303", source_slug="iowa-court-rules")
        self.assertTrue(out["found"])
        self.assertEqual(out["section"]["node"]["source_slug"], "iowa-court-rules")
        # Citation must not be mislabeled "Iowa Code §".
        self.assertEqual(out["section"]["node"]["citation"], "Iowa Ct. R. 1.303")

    def test_unscoped_lookup_falls_through_to_rules(self):
        # No Iowa Code § 1.303 exists; unscoped lookup must still find the rule.
        out = self.lookup("1.303")
        self.assertTrue(out["found"])
        self.assertEqual(out["section"]["node"]["source_slug"], "iowa-court-rules")

    def test_scope_keeps_lookup_out_of_wrong_corpus(self):
        out = self.lookup("1.303", source_slug="iowa-code")
        self.assertFalse(out["found"])

    def test_iowa_code_lookup_still_works(self):
        out = self.lookup("9.1", source_slug="iowa-code")
        self.assertTrue(out["found"])
        self.assertEqual(out["section"]["node"]["citation"], "Iowa Code § 9.1")


class RerankerTests(TestCase):
    """Reranker is pure logic — no DB — but TestCase keeps the file uniform."""

    def test_noop_preserves_order_and_truncates(self):
        from apps.corpus.services.rerank import NoopReranker

        cands = [(10, "a"), (20, "b"), (30, "c"), (40, "d")]
        out = NoopReranker().rerank("q", cands, top_k=2)
        self.assertEqual(out, [10, 20])

    def test_noop_handles_empty(self):
        from apps.corpus.services.rerank import NoopReranker

        self.assertEqual(NoopReranker().rerank("q", [], top_k=5), [])

    def test_default_reranker_is_noop_without_key(self):
        import os
        from unittest import mock

        from apps.corpus.services.rerank import NoopReranker, default_reranker

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(default_reranker(), NoopReranker)


class RRFTests(TestCase):
    """RRF is pure logic — no DB needed, but TestCase keeps the test file
    uniform with the rest."""

    def test_rrf_combines_disjoint_lists(self):
        a = [(1, 0.9), (2, 0.5), (3, 0.1)]
        b = [(2, 0.8), (4, 0.4)]
        fused = reciprocal_rank_fusion({"a": a, "b": b})
        # Item 2 appears in both, should win.
        self.assertEqual(fused[0][0], 2)
        # All items present in result.
        ids = {row[0] for row in fused}
        self.assertEqual(ids, {1, 2, 3, 4})

    def test_rrf_preserves_per_retriever_scores(self):
        fused = reciprocal_rank_fusion(
            {"x": [(1, 0.9)], "y": [(1, 0.4)]}
        )
        item_id, score, components = fused[0]
        self.assertEqual(item_id, 1)
        self.assertEqual(components, {"x": 0.9, "y": 0.4})
        self.assertGreater(score, 0)

    def test_rrf_empty_inputs(self):
        self.assertEqual(reciprocal_rank_fusion({}), [])
        self.assertEqual(reciprocal_rank_fusion({"a": []}), [])

    def test_rrf_rank_dominates_raw_score(self):
        # A's rank-1 has a tiny raw score; B's rank-1 has a huge raw score.
        # Fused ranks should still both be 1/(60+1).
        a = [(1, 0.001)]
        b = [(2, 9999.0)]
        fused = dict((row[0], row[1]) for row in reciprocal_rank_fusion({"a": a, "b": b}))
        self.assertAlmostEqual(fused[1], fused[2])
