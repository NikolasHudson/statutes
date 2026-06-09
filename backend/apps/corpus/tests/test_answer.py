"""Tests for the shared answer gate (``apps.corpus.services.answer``, PR4).

Covers: behavior-preservation of the moved verify gate, stale-use detection
(silent vs acknowledged reliance on a negatively-treated case), the abstain
signal, the block policy behind ``RAG_ABSTAIN_BLOCKING``, and the advisory
rendering. Pure-logic tests use ``SimpleTestCase`` (no DB); the ``verify_answer``
integration + chat-finalizer tests need the minimal corpus.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase, override_settings

from apps.api.tests._factories import make_iowa_corpus_minimal
from apps.corpus.services.answer import (
    _acknowledged_near,
    _misgrounded_claims,
    _normalize_for_match,
    _passage_anchors,
    _split_sentences,
    _stale_used,
    abstain_decision,
    render_advisory,
    should_abstain,
    verify_answer,
)
from apps.corpus.services.semantic_support import (
    CONTRADICTED,
    SUPPORTED,
    SemanticVerdict,
)
from apps.corpus.services.lookups import reset_default_source_cache
from apps.corpus.services.retrieval import (
    RetrievedContext,
    RetrievedPassage,
    TreatmentFlag,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _passage(
    *,
    # Real caselaw shape (corpus_tools._annotate_caselaw): the case NAME lives in
    # ``citation``; ``heading`` is the court+year line, NOT the case name.
    heading="Supreme Court of Iowa, 2009",
    citation="State v. Holder, 763 N.W.2d 862 (Iowa 2009)",
    cluster_id=1,
    treatment=None,
    source_slug="iowa-caselaw",
) -> RetrievedPassage:
    return RetrievedPassage(
        node_version_id=cluster_id,
        node_id=cluster_id,
        cluster_id=cluster_id,
        path="",
        heading=heading,
        citation=citation,
        source_slug=source_slug,
        chunk_id=None,
        char_start=None,
        char_end=None,
        excerpt="",
        snippet="",
        effective_from=None,
        is_repealed=False,
        score=1.0,
        component_scores={},
        treatment=treatment or TreatmentFlag(),
        node_dict={"source_slug": source_slug},
    )


def _neg(
    *,
    label="overruled",
    severity=5,
    by="State v. Later",
    excerpt="We overrule Holder.",
) -> TreatmentFlag:
    return TreatmentFlag(
        status="negative",
        severity=severity,
        label=label,
        by_citation=by,
        excerpt=excerpt,
        source="graph_phrase",
        confidence=0.65,
    )


def _ctx(passages, query="q") -> RetrievedContext:
    return RetrievedContext(query=query, passages=passages, as_of_date="2026-06-09")


class _FakeChecker:
    """Scripted semantic_support checker: CONTRADICTED for any claim containing
    ``mark``, SUPPORTED otherwise. Records its calls."""

    def __init__(self, mark: str):
        self.mark = mark
        self.calls: list = []

    def check_claims(self, claims, source_text):
        self.calls.append((list(claims), source_text))
        return [
            SemanticVerdict(CONTRADICTED if self.mark in c else SUPPORTED, "ev")
            for c in claims
        ]


# ---------------------------------------------------------------------------
# Stale-use detection
# ---------------------------------------------------------------------------


class StaleUseTests(SimpleTestCase):
    def test_named_negative_case_used_silently_is_flagged(self):
        ctx = _ctx([_passage(treatment=_neg())])
        used = _stale_used("The controlling rule comes from State v. Holder.", ctx)
        self.assertEqual(len(used), 1)
        self.assertFalse(used[0]["acknowledged"])
        self.assertEqual(used[0]["label"], "overruled")
        self.assertEqual(used[0]["by_citation"], "State v. Later")

    def test_acknowledged_treatment_is_not_silent(self):
        ctx = _ctx([_passage(treatment=_neg())])
        content = (
            "State v. Holder was overruled by State v. Later, so the current "
            "rule is different."
        )
        used = _stale_used(content, ctx)
        self.assertEqual(len(used), 1)
        self.assertTrue(used[0]["acknowledged"])

    def test_acknowledged_via_named_treating_case_same_sentence(self):
        ctx = _ctx([_passage(treatment=_neg(by="State v. Later"))])
        # No treatment cue word, but the same sentence names the case that did
        # the treating — that counts as acknowledging the history.
        content = "State v. Holder was limited by State v. Later on this point."
        used = _stale_used(content, ctx)
        self.assertEqual(len(used), 1)
        self.assertTrue(used[0]["acknowledged"])

    def test_name_only_citation_no_reporter_is_detected(self):
        # The COA-opinion shape the review caught: name-only citation (no
        # reporter), court+year heading. Must still be matched by name.
        ctx = _ctx([
            _passage(
                heading="Court of Appeals of Iowa, 2024",
                citation="State of Iowa v. Tre Evans Worden",
                treatment=_neg(by="State v. Newer"),
            )
        ])
        used = _stale_used(
            "As the court held in State of Iowa v. Tre Evans Worden, the "
            "search was valid.",
            ctx,
        )
        self.assertEqual(len(used), 1)
        self.assertFalse(used[0]["acknowledged"])

    def test_reporter_cite_match_without_name(self):
        ctx = _ctx([_passage(treatment=_neg())])
        used = _stale_used("That principle appears at 763 N.W.2d 862.", ctx)
        self.assertEqual(len(used), 1)
        self.assertFalse(used[0]["acknowledged"])

    def test_unmentioned_negative_case_is_not_flagged(self):
        ctx = _ctx([_passage(treatment=_neg())])
        self.assertEqual(_stale_used("An unrelated answer about taxes.", ctx), [])

    def test_non_negative_passage_is_ignored_even_if_named(self):
        for flag in (TreatmentFlag(), TreatmentFlag(status="caution", severity=4)):
            ctx = _ctx([_passage(treatment=flag)])
            self.assertEqual(
                _stale_used("Relying on State v. Holder here.", ctx), []
            )

    def test_dedup_by_cluster(self):
        # Two opinions of the same decision, both negative, both named.
        ctx = _ctx(
            [
                _passage(cluster_id=7, treatment=_neg()),
                _passage(cluster_id=7, treatment=_neg()),
            ]
        )
        used = _stale_used("See State v. Holder.", ctx)
        self.assertEqual(len(used), 1)

    def test_context_none_is_empty(self):
        self.assertEqual(_stale_used("anything", None), [])

    def test_cue_about_a_different_case_does_not_excuse_silent_use(self):
        # One negative case named with no nearby acknowledgment; a treatment cue
        # ("overruled") sits far away, attached to a different discussion.
        ctx = _ctx([_passage(treatment=_neg())])
        content = (
            "An unrelated precedent was overruled in 1990. "
            + "Filler. " * 60
            + "Separately, the rule we apply comes from State v. Holder."
        )
        used = _stale_used(content, ctx)
        self.assertEqual(len(used), 1)
        self.assertFalse(used[0]["acknowledged"])


class PassageAnchorTests(SimpleTestCase):
    def test_anchors_include_case_name_and_reporter_core(self):
        anchors = _passage_anchors(_passage())
        self.assertIn("state v. holder", anchors)
        self.assertIn("763 n.w.2d 862", anchors)

    def test_in_re_caption_is_an_anchor(self):
        p = _passage(
            heading="Supreme Court of Iowa, 2017",
            citation="In re Marriage of Smith, 900 N.W.2d 1",
        )
        anchors = _passage_anchors(p)
        self.assertIn("in re marriage of smith", anchors)
        self.assertIn("900 n.w.2d 1", anchors)

    def test_short_or_generic_heading_yields_no_name_anchor(self):
        # A bare statute-style heading is not a case caption.
        anchors = _passage_anchors(
            _passage(heading="Consumer fraud", citation="714.16", source_slug="iowa-code")
        )
        self.assertEqual(anchors, [])


# ---------------------------------------------------------------------------
# Abstain
# ---------------------------------------------------------------------------


class ShouldAbstainTests(SimpleTestCase):
    def test_none_context_abstains(self):
        ab, reason = should_abstain(None)
        self.assertTrue(ab)
        self.assertTrue(reason)

    def test_empty_passages_abstains(self):
        self.assertTrue(should_abstain(_ctx([]))[0])

    def test_all_negative_abstains(self):
        ctx = _ctx([_passage(cluster_id=1, treatment=_neg()),
                    _passage(cluster_id=2, treatment=_neg())])
        self.assertTrue(should_abstain(ctx)[0])

    def test_one_usable_passage_does_not_abstain(self):
        ctx = _ctx([_passage(cluster_id=1, treatment=_neg()),
                    _passage(cluster_id=2, treatment=TreatmentFlag())])  # unknown
        self.assertFalse(should_abstain(ctx)[0])

    def test_unknown_treatment_is_presumed_good(self):
        # Statutes / unflagged cases default to "unknown" — never abstain on that.
        self.assertFalse(should_abstain(_ctx([_passage(treatment=TreatmentFlag())]))[0])


class AbstainDecisionTests(SimpleTestCase):
    def test_blocking_off_never_blocks(self):
        ctx = _ctx([_passage(treatment=_neg())])
        report = {"stale_used": [{"acknowledged": False, "severity": 5,
                                  "citation": "c", "heading": "h", "label": "overruled",
                                  "by_citation": "b"}]}
        block, msg = abstain_decision(report, ctx)
        self.assertFalse(block)
        self.assertEqual(msg, "")

    @override_settings(RAG_ABSTAIN_BLOCKING=True)
    def test_silent_invalid_stale_blocks_with_withheld_notice(self):
        ctx = _ctx([_passage(cluster_id=1, treatment=_neg()),
                    _passage(cluster_id=2, treatment=TreatmentFlag())])
        report = {"stale_used": [{"acknowledged": False, "severity": 5,
                                  "citation": "State v. Holder, 763 N.W.2d 862",
                                  "heading": "State v. Holder", "label": "overruled",
                                  "by_citation": "State v. Later"}]}
        block, msg = abstain_decision(report, ctx)
        self.assertTrue(block)
        self.assertIn("withheld", msg.lower())
        self.assertIn("State v. Holder", msg)

    @override_settings(RAG_ABSTAIN_BLOCKING=True)
    def test_acknowledged_stale_does_not_block(self):
        ctx = _ctx([_passage(cluster_id=1, treatment=_neg()),
                    _passage(cluster_id=2, treatment=TreatmentFlag())])
        report = {"stale_used": [{"acknowledged": True, "severity": 5,
                                  "citation": "c", "heading": "h", "label": "overruled",
                                  "by_citation": "b"}]}
        self.assertFalse(abstain_decision(report, ctx)[0])

    @override_settings(RAG_ABSTAIN_BLOCKING=True, RAG_STALE_BLOCK_SEVERITY=6)
    def test_severity_below_threshold_is_not_blocked(self):
        # A good passage present so the no-good-law branch does not fire; the
        # stale case is sev 5 but the configured block threshold is 6.
        ctx = _ctx([_passage(cluster_id=1, treatment=_neg()),
                    _passage(cluster_id=2, treatment=TreatmentFlag())])
        report = {"stale_used": [{"acknowledged": False, "severity": 5,
                                  "citation": "c", "heading": "h", "label": "overruled",
                                  "by_citation": "b"}]}
        self.assertFalse(abstain_decision(report, ctx)[0])

    @override_settings(RAG_ABSTAIN_BLOCKING=True)
    def test_no_good_law_context_blocks_with_abstain_notice(self):
        ctx = _ctx([_passage(treatment=_neg())])  # all negative
        report = {"stale_used": []}
        block, msg = abstain_decision(report, ctx, searched=True)
        self.assertTrue(block)
        self.assertIn("could not locate good-law", msg.lower())

    @override_settings(RAG_ABSTAIN_BLOCKING=True)
    def test_abstain_not_blocked_when_no_search_ran(self):
        report = {"stale_used": []}
        # searched=False (lookup-only / pinned-doc turn) — empty context must not
        # trigger the no-good-law block.
        self.assertFalse(abstain_decision(report, None, searched=False)[0])

    @override_settings(RAG_ABSTAIN_BLOCKING=True)
    def test_none_report_does_not_crash_or_block(self):
        self.assertFalse(abstain_decision(None, None, searched=False)[0])


# ---------------------------------------------------------------------------
# Advisory rendering
# ---------------------------------------------------------------------------


class RenderAdvisoryTests(SimpleTestCase):
    def _report(self, **over):
        base = {
            "ok": False,
            "source_label": "Iowa Code",
            "citation_problems": [],
            "quote_problems": [],
            "stale_used": [],
        }
        base.update(over)
        return base

    def test_clean_report_renders_nothing(self):
        self.assertEqual(render_advisory(self._report(ok=True)), "")

    def test_silent_stale_use_is_rendered(self):
        report = self._report(
            stale_used=[{
                "acknowledged": False, "severity": 5,
                "citation": "State v. Holder, 763 N.W.2d 862",
                "heading": "State v. Holder", "label": "overruled",
                "by_citation": "State v. Later", "excerpt": "We overrule Holder.",
            }]
        )
        out = render_advisory(report)
        self.assertIn("State v. Holder", out)
        self.assertIn("good law", out)
        self.assertIn("State v. Later", out)

    def test_acknowledged_stale_use_is_not_rendered(self):
        report = self._report(
            stale_used=[{
                "acknowledged": True, "severity": 5, "citation": "c",
                "heading": "h", "label": "overruled", "by_citation": "b",
                "excerpt": "",
            }]
        )
        # Only an acknowledged stale use and nothing else → no advisory lines.
        self.assertEqual(render_advisory(report), "")

    def test_citation_problem_is_rendered(self):
        report = self._report(
            citation_problems=[{"raw": "Iowa Code § 714.99", "status": "not_found"}]
        )
        out = render_advisory(report)
        self.assertIn("714.99", out)
        self.assertIn("could not be found", out)

    def test_misgrounding_is_rendered(self):
        report = self._report(misgrounded=[{
            "citation": "State v. Holder", "claim": "the court struck it down",
            "evidence": "",
        }])
        out = render_advisory(report)
        self.assertIn("State v. Holder", out)
        self.assertIn("not", out.lower())

    # --- PR7 currency axis in the premise_problems advisory branch -----------
    def test_premise_currency_negative_is_rendered(self):
        report = self._report(premise_problems=[{
            "case": "Madden v. City of Iowa City", "asserted": "...",
            "verdict": "supported", "evidence": "",
            "currency": "negative", "treating_case": "Bankers Trust Co. v. City of Des Moines",
            "treatment_label": "overruled", "treatment_evidence": "we overrule Madden",
        }])
        out = render_advisory(report)
        self.assertIn("Madden v. City of Iowa City", out)
        self.assertIn("no longer good law", out)
        self.assertIn("Bankers Trust Co. v. City of Des Moines", out)
        # a faithful (verdict 'supported') reading must NOT be labeled a misreading
        self.assertNotIn("contradicted", out.lower())
        self.assertNotIn("partially supported", out.lower())

    def test_premise_currency_caution_is_rendered(self):
        report = self._report(premise_problems=[{
            "case": "X v. Y", "asserted": "...", "verdict": "supported", "evidence": "",
            "currency": "caution", "treating_case": "Z v. W",
            "treatment_label": "overruled-on-other-grounds", "treatment_evidence": "",
        }])
        out = render_advisory(report)
        self.assertIn("X v. Y", out)
        self.assertIn("qualified on another point", out)
        self.assertNotIn("no longer good law", out)

    def test_premise_fidelity_only_renders_fidelity_line(self):
        # currency good/unknown + contradicted verdict → the fidelity line renders,
        # the currency line does NOT.
        report = self._report(premise_problems=[{
            "case": "X v. Y", "asserted": "...", "verdict": "contradicted",
            "evidence": "the opinion says otherwise", "currency": "unknown",
            "treating_case": "", "treatment_label": "", "treatment_evidence": "",
        }])
        out = render_advisory(report)
        self.assertIn("X v. Y", out)
        self.assertIn("is contradicted by", out)
        self.assertNotIn("no longer good law", out)

    def test_premise_clean_finding_renders_nothing(self):
        # A finding with neither axis bad (defensive) must not emit a spurious line.
        report = self._report(premise_problems=[{
            "case": "X v. Y", "asserted": "...", "verdict": "supported",
            "evidence": "", "currency": "good", "treating_case": "",
            "treatment_label": "", "treatment_evidence": "",
        }])
        self.assertEqual(render_advisory(report), "")


class AcknowledgmentWindowTests(SimpleTestCase):
    def test_cue_same_sentence_acknowledges(self):
        norm = _normalize_for_match("State v. Holder was later overruled.")
        self.assertTrue(_acknowledged_near(norm, "state v. holder", ""))

    def test_cue_in_a_different_sentence_does_not_acknowledge(self):
        # Sentence boundary between the mention and the cue → not acknowledged.
        far = "state v. holder controls here. a different doctrine was overruled."
        self.assertFalse(
            _acknowledged_near(_normalize_for_match(far), "state v. holder", "")
        )

    def test_abbreviation_in_citation_does_not_split_the_sentence(self):
        # Regression from the live test: the model wrote name + cue in one
        # sentence, separated only by "(Iowa App. 1991)". "App." must not be read
        # as a sentence end, or a correct answer is falsely flagged silent.
        content = _normalize_for_match(
            "Metropolitan Jacobson v. Board, 476 N.W.2d 726 (Iowa App. 1991), "
            "is no longer good law as it was overruled."
        )
        self.assertTrue(
            _acknowledged_near(content, "metropolitan jacobson v. board", "")
        )


# ---------------------------------------------------------------------------
# verify_answer — integration (needs the minimal corpus)
# ---------------------------------------------------------------------------


class VerifyAnswerIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()

    def setUp(self):
        reset_default_source_cache()

    def test_empty_content_returns_none(self):
        self.assertIsNone(verify_answer("   "))

    def test_context_none_is_behavior_preserving(self):
        report = verify_answer(
            "Under Iowa Code § 714.16 a merchant who commits a deceptive "
            "practice violates the section.",
            source_slug="iowa-code",
        )
        self.assertIsNotNone(report)
        self.assertTrue(report["ok"])
        self.assertEqual(report["stale_used"], [])
        # The legacy report keys are all still present.
        for key in (
            "citations_total", "citations_verified", "quotes_total",
            "quotes_verified", "citation_problems", "quote_problems",
        ):
            self.assertIn(key, report)

    def test_fabricated_citation_is_flagged(self):
        report = verify_answer(
            "See Iowa Code § 714.99 for the controlling rule.",
            source_slug="iowa-code",
        )
        self.assertFalse(report["ok"])
        self.assertTrue(report["citation_problems"])

    def test_silent_stale_case_flips_ok_false(self):
        ctx = _ctx([_passage(treatment=_neg())])
        report = verify_answer(
            "The governing principle is stated in State v. Holder.",
            source_slug="iowa-code",
            context=ctx,
        )
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["stale_used"]), 1)
        self.assertFalse(report["stale_used"][0]["acknowledged"])

    def test_acknowledged_stale_case_stays_ok(self):
        ctx = _ctx([_passage(treatment=_neg())])
        report = verify_answer(
            "State v. Holder was overruled by State v. Later; do not rely on it.",
            source_slug="iowa-code",
            context=ctx,
        )
        self.assertTrue(report["ok"])
        self.assertTrue(report["stale_used"][0]["acknowledged"])

    def test_misgrounded_claim_flips_ok_false(self):
        p = _passage(treatment=TreatmentFlag())
        p.excerpt = "The court held the search was lawful and affirmed the conviction."
        content = "In State v. Holder the court struck down the search as illegal."
        report = verify_answer(
            content, source_slug="iowa-caselaw", context=_ctx([p]),
            claim_checker=_FakeChecker("struck down"),
        )
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["misgrounded"]), 1)
        self.assertIn("Holder", report["misgrounded"][0]["citation"])

    def test_supported_caselaw_claim_stays_ok(self):
        p = _passage(treatment=TreatmentFlag())
        p.excerpt = "The court held the search was lawful and affirmed."
        report = verify_answer(
            "In State v. Holder the court upheld the search.",
            source_slug="iowa-caselaw", context=_ctx([p]),
            claim_checker=_FakeChecker("never-matches"),
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["misgrounded"], [])


# ---------------------------------------------------------------------------
# Chat finalizer wiring (advisory vs block)
# ---------------------------------------------------------------------------


class ChatFinalizerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()

    def setUp(self):
        reset_default_source_cache()

    def test_advisory_default_appends_warning_and_keeps_answer(self):
        from apps.api.chat import _apply_verification

        ctx = _ctx([_passage(treatment=_neg())])
        trace: list = []
        answer = "The governing principle is stated in State v. Holder."
        out = _apply_verification(answer, "iowa-code", trace, context=ctx)
        # Original answer preserved + advisory appended (not replaced).
        self.assertTrue(out.startswith(answer))
        self.assertIn("Automated verification", out)
        self.assertEqual(len(trace), 1)
        self.assertFalse(trace[0].result["blocked"])

    @override_settings(RAG_ABSTAIN_BLOCKING=True)
    def test_blocking_withholds_the_answer(self):
        from apps.api.chat import _apply_verification

        ctx = _ctx([_passage(cluster_id=1, treatment=_neg()),
                    _passage(cluster_id=2, treatment=TreatmentFlag())])
        trace: list = []
        answer = "The governing principle is stated in State v. Holder."
        out = _apply_verification(answer, "iowa-code", trace, context=ctx)
        # The original answer is gone; a withheld notice replaces it.
        self.assertNotIn("governing principle is stated", out)
        self.assertIn("withheld", out.lower())
        self.assertTrue(trace[0].result["blocked"])


# ---------------------------------------------------------------------------
# PR5: claim-level NLI (misgrounding) + sentence splitting
# ---------------------------------------------------------------------------


class ClaimNLITests(SimpleTestCase):
    def _cl(self, excerpt="The court held the search was lawful."):
        p = _passage(treatment=TreatmentFlag())
        p.excerpt = excerpt
        return p

    def test_contradicted_claim_is_misgrounded(self):
        checker = _FakeChecker("struck down")
        out = _misgrounded_claims(
            "In State v. Holder the court struck down the search.",
            _ctx([self._cl()]), checker,
        )
        self.assertEqual(len(out), 1)
        self.assertIn("Holder", out[0]["citation"])
        self.assertEqual(len(checker.calls), 1)

    def test_supported_claim_not_flagged(self):
        out = _misgrounded_claims(
            "In State v. Holder the court upheld the search.",
            _ctx([self._cl()]), _FakeChecker("never"),
        )
        self.assertEqual(out, [])

    def test_statute_passage_is_skipped(self):
        p = _passage(source_slug="iowa-code", heading="Consumer fraud",
                     citation="714.16")
        p.excerpt = "A merchant who commits a deceptive practice ..."
        checker = _FakeChecker("X")
        self.assertEqual(
            _misgrounded_claims("714.16 requires X here.", _ctx([p]), checker), [])
        self.assertEqual(checker.calls, [])

    def test_none_context_or_checker_is_empty(self):
        self.assertEqual(_misgrounded_claims("x", None, _FakeChecker("x")), [])
        self.assertEqual(
            _misgrounded_claims("State v. Holder ruled.", _ctx([self._cl()]), None), [])

    def test_unreferenced_passage_makes_no_call(self):
        checker = _FakeChecker("x")
        out = _misgrounded_claims("An unrelated answer about taxes.",
                                  _ctx([self._cl()]), checker)
        self.assertEqual(out, [])
        self.assertEqual(checker.calls, [])


class SplitSentencesTests(SimpleTestCase):
    def test_splits_on_real_boundaries(self):
        self.assertEqual(len(_split_sentences("A first point. A second point.")), 2)

    def test_does_not_split_on_legal_abbreviations(self):
        out = _split_sentences(
            "See State v. Holder, 1 N.W.2d 1 (Iowa App. 1990) for this rule.")
        self.assertEqual(len(out), 1)
