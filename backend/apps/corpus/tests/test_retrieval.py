"""PR2 shared-pipeline tests for ``apps.corpus.services.retrieval``.

Two layers:

* Pure-function tests (no DB) pin the algorithms that the surface tests can only
  observe indirectly — MMR selection, U-curve ordering, and the chunk-centered
  excerpt. They assert the load-bearing invariants: the rank-1 hit always stays
  at position 0 (so every ``hits[0]`` assertion across the suite holds), MMR
  demotes a near-duplicate for a diverse lower-ranked hit, and the excerpt window
  is robust to offsets that don't reconstruct.

* DB integration tests drive ``retrieve_context`` end-to-end over a tiny caselaw +
  statute corpus to prove the wiring: the winning ``chunk_id`` threads from the
  vector retriever to the passage, decision-cluster dedup collapses a case's
  opinions, caselaw passages carry the matched chunk's offsets + a holding-
  centered excerpt while statutes keep their prefix, and the exact-citation lane
  survives a reranker that would otherwise demote it.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, tag

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
from apps.corpus.services.rerank import NoopReranker
from apps.corpus.services.retrieval import (
    TreatmentFlag,
    _chunk_excerpt,
    _jaccard,
    _mmr_select,
    _token_set,
    _u_order,
    retrieve_context,
    treatment_payload,
)
from apps.corpus.services.voyage import FakeEmbeddingClient


def _hit(heading: str, body: str):
    """A stand-in for a SearchHit carrying only what MMR reads."""
    return SimpleNamespace(heading=heading, body_text=body)


class UOrderTests(SimpleTestCase):
    def test_u_curve_places_strongest_at_the_ends(self):
        # best-first [1,2,3,4,5] -> 1 first, 2 last, weakest (5) dead center.
        self.assertEqual(_u_order([1, 2, 3, 4, 5]), [1, 3, 5, 4, 2])

    def test_position_zero_is_always_the_top_ranked(self):
        for items in ([10], [10, 20], [10, 20, 30], list(range(9))):
            self.assertEqual(_u_order(items)[0], items[0])

    def test_short_lists_unchanged(self):
        self.assertEqual(_u_order([]), [])
        self.assertEqual(_u_order(["a"]), ["a"])
        self.assertEqual(_u_order(["a", "b"]), ["a", "b"])


class MMRTests(SimpleTestCase):
    def test_first_pick_is_the_top_ranked_hit(self):
        # The invariant the surface tests depend on: rank-1 never moves.
        items = [_hit(f"h{i}", f"body number {i} alpha beta") for i in range(5)]
        out = _mmr_select(items, k=3, lambda_=0.6)
        self.assertIs(out[0], items[0])

    def test_diversity_demotes_a_near_duplicate(self):
        a = _hit("warrantless search fourth amendment blood draw",
                 "warrantless search fourth amendment blood draw probable cause")
        a_dup = _hit("warrantless search fourth amendment blood draw",
                     "warrantless search fourth amendment blood draw probable cause")
        c = _hit("contract breach damages remedy mitigation",
                 "contract breach damages remedy mitigation foreseeability")
        # ranks: a (0, best), a_dup (1), c (2). MMR should keep a, then prefer the
        # diverse c over the near-identical a_dup despite a_dup ranking higher.
        out = _mmr_select([a, a_dup, c], k=3, lambda_=0.6)
        self.assertEqual([id(x) for x in out], [id(a), id(c), id(a_dup)])

    def test_lambda_one_is_pure_relevance_order(self):
        items = [_hit(f"h{i}", "same tokens everywhere alpha beta") for i in range(4)]
        self.assertEqual(_mmr_select(items, k=3, lambda_=1.0), items[:3])

    def test_k_caps_the_output(self):
        items = [_hit(f"h{i}", f"distinct body {i}") for i in range(5)]
        self.assertEqual(len(_mmr_select(items, k=2, lambda_=0.6)), 2)

    def test_token_overlap_helpers(self):
        self.assertEqual(_token_set("The Fourth Amendment, 4th!"), frozenset({"the", "fourth", "amendment", "4th"}))
        self.assertEqual(_jaccard(frozenset(), frozenset()), 0.0)
        self.assertEqual(_jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})), 1.0)
        self.assertEqual(_jaccard(frozenset({"a", "b"}), frozenset({"a", "c"})), 1 / 3)


class ChunkExcerptTests(SimpleTestCase):
    def test_centers_on_the_chunk_with_neighbor_context(self):
        body = "PROCEDURAL HISTORY. " * 600 + "HOLDING here." + " tail tail tail"
        start = body.index("HOLDING here.")
        end = start + len("HOLDING here.")
        out = _chunk_excerpt(body, body[start:end], start, end, budget=200)
        self.assertIn("HOLDING here.", out)
        self.assertTrue(out.startswith("…"))  # cut from the long procedural head
        self.assertLessEqual(len(out), 200)  # ellipses reserved → never over budget

    def test_falls_back_to_chunk_body_when_offsets_do_not_reconstruct(self):
        # Placeholder offsets (as some fixtures use) must not corrupt the excerpt.
        out = _chunk_excerpt("short version body", "the real chunk text", 0, 4, budget=500)
        self.assertEqual(out, "the real chunk text")

    def test_span_larger_than_budget_is_truncated(self):
        body = "x" * 500
        out = _chunk_excerpt(body, body[0:300], 0, 300, budget=50)
        self.assertLessEqual(len(out), 51)
        self.assertTrue(out.endswith("…"))

    def test_no_neighbor_ellipsis_when_span_is_the_whole_body(self):
        body = "the entire opinion fits in one chunk"
        out = _chunk_excerpt(body, body, 0, len(body), budget=9000)
        self.assertEqual(out, body)

    def test_never_exceeds_budget_even_with_both_ellipses(self):
        # Span just under budget, sitting mid-document so both ellipses apply —
        # the worst case for the reserved-room contract.
        body = "L" * 400 + "M" * 99 + "R" * 400
        out = _chunk_excerpt(body, body[400:499], 400, 499, budget=100)
        self.assertLessEqual(len(out), 100)
        self.assertTrue(out.startswith("…") and out.endswith("…"))


@tag("postgres")
class RetrievePipelineTests(TestCase):
    """End-to-end ``retrieve_context`` over a controlled caselaw + statute corpus.

    The vector retriever embeds via the FAKE client (patched into the search
    module, since ``retrieve_context`` does not take a client), and the reranker
    is the deterministic Noop unless a test supplies its own — so assertions turn
    on the pipeline's structure, not on opaque embedding/cross-encoder scores."""

    def setUp(self):
        # retrieve_context -> hybrid_search -> vector_search ->
        # embed_query_cached -> default_client(). The query-embedding cache
        # is cleared so no vector leaks between tests.
        patcher = mock.patch(
            "apps.corpus.services.embedding_cache.default_client",
            return_value=FakeEmbeddingClient(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.clear()
        self.addCleanup(cache.clear)

        j = Jurisdiction.objects.create(slug="ia", name="Iowa", abbreviation="IA")
        self.caselaw = Source.objects.create(
            jurisdiction=j, slug="iowa-caselaw", name="Iowa Caselaw",
            citation_abbreviation="IA",
        )
        self.code = Source.objects.create(
            jurisdiction=j, slug="iowa-code", name="Iowa Code",
            citation_abbreviation="Iowa Code",
        )
        dt_t = NodeType.objects.create(
            source=self.caselaw, key="decision", label_singular="Decision", level=1
        )
        op_t = NodeType.objects.create(
            source=self.caselaw, key="opinion", label_singular="Opinion", level=2
        )
        sec_t = NodeType.objects.create(
            source=self.code, key="section", label_singular="Section", level=1
        )

        # Decision cl-9: a holding-centered lead opinion + a dissent (two opinions
        # of ONE decision — the dedup target). The lead's holding sits AFTER a long
        # procedural head so a whole-version prefix would miss it.
        self.decision = Node.objects.create(
            source=self.caselaw, node_type=dt_t, ordinal="1", path="cl-9",
            heading="State v. Holder",
            source_metadata={
                "court_id": "iowa", "precedential_status": "Published",
                "case_name": "State v. Holder", "citations": ["999 N.W.2d 111"],
                "date_filed": "2020-01-01",
            },
        )
        self.op_lead = Node.objects.create(
            source=self.caselaw, node_type=op_t, parent=self.decision,
            ordinal="010", path="cl-9/op-1", heading="Lead Opinion",
        )
        self.op_diss = Node.objects.create(
            source=self.caselaw, node_type=op_t, parent=self.decision,
            ordinal="020", path="cl-9/op-2", heading="Dissent",
        )
        head = "PROCEDURAL HISTORY. " * 600  # ~12k chars before the holding
        holding = "THE HOLDING: a warrantless blood draw violates the Fourth Amendment."
        lead_body = head + holding + " Further analysis follows here."
        self._add_opinion(self.op_lead, lead_body, holding)
        diss_body = "DISSENT: I would hold the warrantless blood draw permissible under exigency."
        self._add_opinion(self.op_diss, diss_body, diss_body)

        # A second, citation-LESS decision that also matches "blood draw" by FTS —
        # the foil for the citation-bypass test.
        self.decision2 = Node.objects.create(
            source=self.caselaw, node_type=dt_t, ordinal="2", path="cl-10",
            heading="In re Other",
            source_metadata={"court_id": "iowa", "precedential_status": "Published",
                             "case_name": "In re Other", "citations": []},
        )
        self.op_other = Node.objects.create(
            source=self.caselaw, node_type=op_t, parent=self.decision2,
            ordinal="010", path="cl-10/op-1", heading="Opinion",
        )
        # Body carries the full query text (incl. the citation tokens) so it
        # FTS-matches — but the cite lives only in cl-9's metadata, so the
        # citation retriever never claims this foil.
        other_body = "Discussing 999 N.W.2d 111 and a warrantless blood draw at length."
        self._add_opinion(self.op_other, other_body, other_body)

        # A statute (version-embedded, no chunks) — keeps the prefix excerpt.
        self.statute = Node.objects.create(
            source=self.code, node_type=sec_t, ordinal="16", path="714.16",
            heading="Consumer fraud",
        )
        NodeVersion.objects.create(
            node=self.statute,
            body_text="A merchant who commits a consumer fraud is liable to the state.",
            effective_from=dt.date(2020, 1, 1), content_hash="s1",
            review_status=ReviewStatus.APPROVED,
        )

        # Embed: chunks for caselaw, version-level for the statute ONLY (so the
        # caselaw versions stay chunk-retrieved and thread a winning chunk_id).
        run_chunk_embedding_job(client=FakeEmbeddingClient())
        run_embedding_job(client=FakeEmbeddingClient(), source_slugs=["iowa-code"])

    def _add_opinion(self, node, body, chunk_span):
        v = NodeVersion.objects.create(
            node=node, body_text=body, effective_from=dt.date(2020, 1, 1),
            content_hash=f"v{node.id}", review_status=ReviewStatus.APPROVED,
        )  # deliberately NO version-level embedding
        start = body.index(chunk_span)
        NodeChunk.objects.create(
            version=v, ordinal=0, body_text=body[start:start + len(chunk_span)],
            context_header="State v. Holder (Iowa)",
            char_start=start, char_end=start + len(chunk_span),
            token_count=10, content_hash=f"c{node.id}",
        )
        return v

    # -- chunk_id threading (search level) ---------------------------------

    def test_chunk_id_threads_to_caselaw_searchhit_only(self):
        from apps.corpus.services.search import hybrid_search

        hits = hybrid_search(
            "warrantless blood draw holding", source_slug="iowa-caselaw",
            client=FakeEmbeddingClient(),
        )
        cas = [h for h in hits if h.node_id == self.op_lead.id]
        self.assertTrue(cas, "lead opinion should be retrieved via its chunk")
        chunk = NodeChunk.objects.get(id=cas[0].chunk_id)
        self.assertEqual(chunk.version_id, cas[0].node_version_id)

        stat = hybrid_search(
            "merchant consumer fraud", source_slug="iowa-code",
            client=FakeEmbeddingClient(),
        )
        srow = [h for h in stat if h.node_id == self.statute.id]
        self.assertTrue(srow)
        self.assertIsNone(srow[0].chunk_id)  # statute embeds whole, no chunk

    # -- decision-cluster dedup --------------------------------------------

    def test_dedup_collapses_a_decisions_opinions(self):
        ctx = retrieve_context(
            "warrantless blood draw holding", source_slug="iowa-caselaw",
            reranker=NoopReranker(),
        )
        cl9 = [p for p in ctx.passages if p.cluster_id == self.decision.id]
        self.assertEqual(len(cl9), 1, "lead + dissent must collapse to one passage")
        self.assertEqual(ctx.diagnostics.get("deduped_out"), 1)

    def test_dedup_off_keeps_both_opinions(self):
        ctx = retrieve_context(
            "warrantless blood draw holding", source_slug="iowa-caselaw",
            reranker=NoopReranker(), dedup_clusters=False,
        )
        cl9 = [p for p in ctx.passages if p.cluster_id == self.decision.id]
        self.assertEqual(len(cl9), 2)

    # -- chunk-aware offsets + excerpts ------------------------------------

    def test_caselaw_passage_carries_chunk_offsets_statute_does_not(self):
        ctx = retrieve_context(
            "warrantless blood draw holding THE HOLDING", source_slug="iowa-caselaw",
            reranker=NoopReranker(), dedup_clusters=False,
        )
        lead = next(p for p in ctx.passages if p.node_id == self.op_lead.id)
        chunk = NodeChunk.objects.get(id=lead.chunk_id)
        self.assertEqual((lead.char_start, lead.char_end),
                         (chunk.char_start, chunk.char_end))
        self.assertIn("THE HOLDING", lead.snippet)  # snippet from the chunk, not head

        sctx = retrieve_context(
            "merchant consumer fraud", source_slug="iowa-code",
            reranker=NoopReranker(),
        )
        srow = next(p for p in sctx.passages if p.node_id == self.statute.id)
        self.assertIsNone(srow.char_start)
        self.assertIsNone(srow.chunk_id)

    def test_chunk_excerpt_surfaces_the_holding_a_prefix_would_miss(self):
        ctx = retrieve_context(
            "warrantless blood draw holding THE HOLDING", source_slug="iowa-caselaw",
            reranker=NoopReranker(), enrich_bodies=True, dedup_clusters=False,
        )
        lead = next(p for p in ctx.passages if p.node_id == self.op_lead.id)
        # The holding sits ~12k chars in; any whole-version prefix (<=9k budget)
        # is pure procedural history. Finding it proves chunk-centering.
        self.assertIn("THE HOLDING", lead.excerpt)

    def test_chunk_excerpts_off_falls_back_to_prefix(self):
        ctx = retrieve_context(
            "warrantless blood draw holding", source_slug="iowa-caselaw",
            reranker=NoopReranker(), dedup_clusters=False, chunk_excerpts=False,
        )
        lead = next(p for p in ctx.passages if p.node_id == self.op_lead.id)
        self.assertIsNone(lead.char_start)
        self.assertIn("PROCEDURAL HISTORY", lead.snippet)  # opinion-head prefix

    # -- PR3: treatment flag flows from the decision's cached metadata -----

    def test_treatment_flag_flows_to_caselaw_passage(self):
        self.decision.source_metadata["treatment"] = {
            "status": "negative", "severity": 5, "label": "overruled",
            "by_citation": "State v. Later", "excerpt": "We overrule Holder.",
            "source": "graph_phrase", "confidence": 0.65,
        }
        self.decision.save(update_fields=["source_metadata"])
        ctx = retrieve_context(
            "warrantless blood draw holding", source_slug="iowa-caselaw",
            reranker=NoopReranker(), dedup_clusters=False,
        )
        p = next(p for p in ctx.passages if p.cluster_id == self.decision.id)
        self.assertEqual(p.treatment.status, "negative")
        self.assertEqual(p.treatment.severity, 5)
        self.assertEqual(p.treatment.by_citation, "State v. Later")
        # serializer payload carries every field
        self.assertEqual(treatment_payload(p.treatment)["label"], "overruled")

    def test_unflagged_caselaw_and_statute_get_unknown_default(self):
        ctx = retrieve_context(
            "warrantless blood draw holding", source_slug="iowa-caselaw",
            reranker=NoopReranker(),
        )
        self.assertTrue(all(p.treatment.status == "unknown" for p in ctx.passages))
        sctx = retrieve_context(
            "merchant consumer fraud", source_slug="iowa-code", reranker=NoopReranker()
        )
        self.assertTrue(all(p.treatment.status == "unknown" for p in sctx.passages))

    # -- citation lane bypasses the reranker -------------------------------

    def test_citation_hit_survives_a_demoting_reranker(self):
        class _Reverse:
            def rerank(self, query, candidates, *, top_k):
                return [cid for cid, _ in candidates][::-1][:top_k]

        kw = dict(
            source_slug="iowa-caselaw", use_vector=False, reranker=_Reverse(),
            dedup_clusters=False, mmr_lambda=None, u_order=False,
        )
        # Protected (default): the exact-cite decision stays at the front even
        # though the reranker reverses everything else.
        ctx = retrieve_context("999 N.W.2d 111 blood draw", **kw)
        self.assertEqual(ctx.passages[0].cluster_id, self.decision.id)
        self.assertIn("citation", ctx.passages[0].component_scores)
        self.assertEqual(ctx.diagnostics.get("cite_protected", 0), 2)

        # Unprotected: the reranker is free to demote the cite hit, so the
        # citation-less foil reaches the top instead.
        ctx2 = retrieve_context(
            "999 N.W.2d 111 blood draw", protect_citations=False, **kw
        )
        self.assertEqual(ctx2.passages[0].cluster_id, self.decision2.id)
