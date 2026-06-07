"""Hybrid search retrievers and RRF fusion.

These tests use a small synthetic corpus instead of the Iowa probe sample —
keeps assertions tight and fast."""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, tag

from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeChunk,
    NodeType,
    NodeVersion,
    ReviewStatus,
    Source,
)
from apps.corpus.services.embeddings import run_chunk_embedding_job, run_embedding_job
from apps.corpus.services.search import (
    RETRIEVER_WEIGHTS,
    case_name_search,
    citation_search,
    extract_case_names,
    extract_citations,
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
        # FakeEmbeddingClient produces hash vectors with no semantic meaning, so
        # the vector retriever is pure noise. Under weighted RRF the dense vote is
        # weighted 1.0 (it's the trusted signal in production), so that noise would
        # now dominate the down-weighted lexical retrievers and make this test
        # about which doc the fake vectors hashed near — exactly what it must not
        # test. Drop the fake vector (use_vector=False) so the assertion exercises
        # the fts+trigram fusion it intends: heading "Consumer fraud" → both FTS
        # weight-A and heading trigram point at 714.16.
        hits = hybrid_search(
            "consumer fraud",
            limit=5,
            use_vector=False,
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


class ExtractCitationsTests(TestCase):
    """The reporter-citation extractor must fire on real cites and stay quiet on
    prose / statute refs (a false positive would inject a citation retriever on
    an ordinary query)."""

    def test_extracts_standard_and_parallel_cites(self):
        self.assertEqual(extract_citations("763 N.W.2d 862"), ["763 N.W.2d 862"])
        self.assertEqual(extract_citations("1 Morris 1"), ["1 Morris 1"])
        self.assertEqual(
            extract_citations("253 Iowa 378, 111 N.W.2d 753"),
            ["253 Iowa 378", "111 N.W.2d 753"],
        )
        self.assertEqual(extract_citations("see 815 N.W.2d 1 (Iowa 2012)"), ["815 N.W.2d 1"])

    def test_ignores_prose_and_statute_refs(self):
        self.assertEqual(extract_citations("Article I Section 17"), [])
        self.assertEqual(extract_citations("joint physical care 598.41"), [])
        self.assertEqual(extract_citations("Baldwin qualified immunity Iowa"), [])


@tag("postgres")
class CitationSearchTests(TestCase):
    """Exact citation lookup against ``source_metadata.citations`` — the path the
    body-text retrievers structurally cannot serve, since the reporter cite lives
    in metadata on the decision, not in the opinion text."""

    def setUp(self):
        j = Jurisdiction.objects.create(slug="jc", name="JC", abbreviation="JC")
        self.source = Source.objects.create(
            jurisdiction=j, slug="cases", name="Cases", citation_abbreviation="C"
        )
        self.nt = NodeType.objects.create(
            source=self.source, key="case", label_singular="Case", level=1
        )
        # Decision cluster carries the citation; the embedded/returned unit is the
        # child opinion, whose body deliberately does NOT contain the cite string.
        self.cluster = Node.objects.create(
            source=self.source, node_type=self.nt, ordinal="1", path="cl-1",
            heading="Varnum v. Brien",
            source_metadata={"citations": ["763 N.W.2d 862", "2009 WL 874044"]},
        )
        self.opinion = Node.objects.create(
            source=self.source, node_type=self.nt, ordinal="1", path="cl-1/op-1",
            heading="Varnum v. Brien", parent=self.cluster,
        )
        self.op_v = NodeVersion.objects.create(
            node=self.opinion,
            body_text="CADY, Justice. We hold the marriage statute violates equal protection.",
            effective_from=dt.date(2026, 1, 1), content_hash="h-op1",
            review_status=ReviewStatus.APPROVED,
        )
        # A decoy whose body merely mentions the number 763 — must not be matched.
        self.decoy = Node.objects.create(
            source=self.source, node_type=self.nt, ordinal="2", path="cl-2/op-2",
            heading="Other v. Other",
        )
        self.decoy_v = NodeVersion.objects.create(
            node=self.decoy, body_text="There were 763 widgets at 862 Main Street.",
            effective_from=dt.date(2026, 1, 1), content_hash="h-op2",
            review_status=ReviewStatus.APPROVED,
        )

    def test_citation_search_matches_parent_metadata_returns_opinion(self):
        hits = citation_search("763 N.W.2d 862", source_slug="cases")
        ids = [i for i, _ in hits]
        self.assertEqual(ids, [self.op_v.id])  # opinion of the matched cluster only

    def test_citation_search_noop_without_citation(self):
        self.assertEqual(citation_search("equal protection marriage"), [])

    def test_hybrid_prepends_exact_citation_over_fts_noise(self):
        # FTS surfaces the decoy (it contains "763" and "862"); the exact-cite
        # case must still land at rank 1 via the prepend, not be diluted by RRF.
        hits = hybrid_search("763 N.W.2d 862", limit=5, use_vector=False)
        self.assertEqual(hits[0].path, "cl-1/op-1")
        self.assertIn("citation", hits[0].component_scores)


class ExtractCaseNamesTests(TestCase):
    """The name extractor is a permissive *candidate* generator — capitalized,
    non-stoplisted, citation-stripped tokens. The heading-frequency screen in
    ``case_name_search`` is what culls non-party candidates (Iowa, Abrogation)."""

    def test_extracts_capitalized_party_tokens(self):
        self.assertEqual(
            extract_case_names("Hansen joint physical care factors 598.41"), ["Hansen"]
        )
        self.assertEqual(
            extract_case_names("Puntenney oil pipeline eminent domain public use"),
            ["Puntenney"],
        )
        # "Constitution" is stoplisted; "Iowa" is left for the DF screen, not here.
        self.assertEqual(
            extract_case_names("Baldwin good faith standard Iowa Constitution"),
            ["Baldwin", "Iowa"],
        )

    def test_drops_stoplist_and_citation_tokens(self):
        self.assertEqual(extract_case_names("Whether Article I Section 17 applies"), [])
        self.assertEqual(extract_case_names("763 N.W.2d 862"), [])


@tag("postgres")
class CaseNameSearchTests(TestCase):
    """Party-name + concept intersection: the case whose NAME and CONCEPT both
    match wins; a same-name/wrong-concept or wrong-name/same-concept case must
    not be returned."""

    def setUp(self):
        j = Jurisdiction.objects.create(slug="jn", name="JN", abbreviation="JN")
        self.source = Source.objects.create(
            jurisdiction=j, slug="cn", name="CN", citation_abbreviation="CN"
        )
        self.nt = NodeType.objects.create(
            source=self.source, key="case", label_singular="Case", level=1
        )

    def _case(self, n, heading, body):
        cl = Node.objects.create(
            source=self.source, node_type=self.nt, ordinal=str(n),
            path=f"c{n}", heading=heading,
        )
        op = Node.objects.create(
            source=self.source, node_type=self.nt, ordinal=str(n),
            path=f"c{n}/op", heading="Opinion", parent=cl,
        )
        v = NodeVersion.objects.create(
            node=op, body_text=body, effective_from=dt.date(2026, 1, 1),
            content_hash=f"h{n}", review_status=ReviewStatus.APPROVED,
        )
        return op, v

    def test_intersects_name_on_cluster_with_concept_in_body(self):
        target, tv = self._case(
            1, "In re Marriage of Hansen",
            "We adopt a framework of factors for joint physical care under "
            "section 598.41, emphasizing historical caregiving.",
        )
        # same surname, wrong concept
        self._case(2, "State v. Hansen",
                   "The defendant carried a concealed dangerous weapon.")
        # right concept, wrong surname
        self._case(3, "In re Marriage of Smith",
                   "Joint physical care factors under section 598.41 are weighed.")

        hits = case_name_search(
            "Hansen joint physical care factors 598.41", source_slug="cn"
        )
        ids = [i for i, _ in hits]
        self.assertEqual(ids, [tv.id])  # only the Hansen marriage opinion

    def test_screens_zero_heading_frequency_candidate(self):
        # "Abrogation" is a capitalized non-stoplisted candidate but appears in no
        # heading (DF=0), so it is screened out -> no retriever firing.
        self._case(1, "Turner v. Turner", "abrogation of parental immunity doctrine")
        self.assertEqual(
            case_name_search("Abrogation of parental immunity", source_slug="cn"), []
        )

    def test_noop_without_a_name(self):
        self._case(1, "In re Marriage of Hansen", "joint physical care factors")
        self.assertEqual(case_name_search("joint physical care factors"), [])

    def test_hybrid_exposes_case_name_component(self):
        target, _ = self._case(
            1, "In re Marriage of Hansen",
            "framework of factors for joint physical care under section 598.41",
        )
        self._case(3, "In re Marriage of Smith",
                   "joint physical care factors under section 598.41")
        hits = hybrid_search(
            "Hansen joint physical care factors 598.41",
            limit=5, use_vector=False, source_slug="cn",
        )
        self.assertEqual(hits[0].path, "c1/op")
        self.assertIn("case_name", hits[0].component_scores)


@tag("postgres")
class ChunkVectorSearchTests(TestCase):
    """vector_search must surface caselaw versions through their NodeChunk
    embeddings (the version itself has no embedding) and roll multiple chunks up
    to a single version row, while still honoring source/metadata scope."""

    def setUp(self):
        j = Jurisdiction.objects.create(slug="ia", name="Iowa", abbreviation="IA")
        self.caselaw = Source.objects.create(
            jurisdiction=j, slug="iowa-caselaw", name="Iowa Caselaw",
            citation_abbreviation="IA",
        )
        dt_t = NodeType.objects.create(
            source=self.caselaw, key="decision", label_singular="Decision", level=1
        )
        op_t = NodeType.objects.create(
            source=self.caselaw, key="opinion", label_singular="Opinion", level=2
        )
        # Court/status live on the decision; the opinion is its child.
        decision = Node.objects.create(
            source=self.caselaw, node_type=dt_t, ordinal="1", path="cl-1",
            heading="State v. X",
            source_metadata={"court_id": "iowa", "precedential_status": "Published"},
        )
        opinion = Node.objects.create(
            source=self.caselaw, node_type=op_t, parent=decision, ordinal="020",
            path="cl-1/op-1", heading="Lead Opinion",
        )
        self.version = NodeVersion.objects.create(
            node=opinion, body_text="full opinion text", effective_from=dt.date(2026, 1, 1),
            content_hash="v", review_status=ReviewStatus.APPROVED,
        )  # note: no version-level embedding — retrieval must come from chunks
        for i in range(3):
            NodeChunk.objects.create(
                version=self.version, ordinal=i, body_text=f"chunk {i}",
                context_header="State v. X (Iowa) — Lead Opinion",
                char_start=0, char_end=7, token_count=2, content_hash=f"c{i}",
            )
        run_chunk_embedding_job(client=FakeEmbeddingClient())

    def test_chunked_version_is_retrievable(self):
        ids = [r[0] for r in vector_search("anything", client=FakeEmbeddingClient(), limit=5)]
        self.assertIn(self.version.id, ids)
        # Confirm it really had no version-level embedding.
        self.assertIsNone(NodeVersion.objects.get(id=self.version.id).embedding)

    def test_chunks_roll_up_to_one_row_per_version(self):
        ids = [r[0] for r in vector_search("anything", client=FakeEmbeddingClient(), limit=5)]
        self.assertEqual(ids.count(self.version.id), 1)  # 3 chunks → 1 version

    def test_chunk_vector_scoped_to_source(self):
        hit = vector_search(
            "anything", client=FakeEmbeddingClient(), source_slug="iowa-caselaw"
        )
        self.assertEqual([r[0] for r in hit], [self.version.id])
        miss = vector_search(
            "anything", client=FakeEmbeddingClient(), source_slug="iowa-code"
        )
        self.assertEqual(miss, [])

    def test_chunk_metadata_facet_filter_uses_parent_decision(self):
        # court_id lives on the parent decision; the parent-aware filter must
        # still scope the chunk-backed opinion version.
        hit = vector_search(
            "anything", client=FakeEmbeddingClient(),
            source_slug="iowa-caselaw", metadata_contains={"court_id": "iowa"},
        )
        self.assertEqual([r[0] for r in hit], [self.version.id])
        miss = vector_search(
            "anything", client=FakeEmbeddingClient(),
            source_slug="iowa-caselaw", metadata_contains={"court_id": "nope"},
        )
        self.assertEqual(miss, [])


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

    def test_weighted_rrf_keeps_dense_rank1_over_weak_agreement(self):
        # The headline regression this guards: two weak lexical retrievers (fts,
        # trigram) agree on a decoy (200) at rank 1 while the trusted dense
        # retriever alone has the right answer (100) at rank 1. Equal-weight RRF
        # gives the decoy two votes vs one and it wins — which is exactly why
        # 'hybrid' scored worse than 'vector'. The production weights must keep
        # the dense hit on top.
        rankings = {
            "vector": [(100, 0.80)],
            "fts": [(200, 0.50)],
            "trigram": [(200, 0.40)],
        }
        weighted = reciprocal_rank_fusion(rankings, weights=RETRIEVER_WEIGHTS)
        self.assertEqual(weighted[0][0], 100)
        # And prove the weighting is what flipped it: equal weight elects the decoy.
        equal = reciprocal_rank_fusion(rankings, weights={})
        self.assertEqual(equal[0][0], 200)
