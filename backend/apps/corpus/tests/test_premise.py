"""Tests for the PR6 user-premise check (``apps.corpus.services.premise``) and its
gated chat hook. Extraction is pure; check_premises uses an injected fake checker
+ fake retriever (no API, no DB). Mirrors the slip-and-fall failure that motivated
it: a user asserting a holding *Madden* does not actually support.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.corpus.services import premise
from apps.corpus.services.premise import (
    PremiseFinding,
    check_premises,
    extract_premises,
    render_premise_caution,
)
from apps.corpus.services.retrieval import (
    RetrievedContext,
    RetrievedPassage,
    TreatmentFlag,
)
from apps.corpus.services.semantic_support import (
    CONTRADICTED,
    NO_CLAIM,
    PARTIAL,
    SUPPORTED,
    SemanticVerdict,
)

MADDEN = (
    "This tracks exactly with the Iowa Supreme Court's holding in Madden v. City "
    "of Iowa City, which confirmed that these local liability-shifting ordinances "
    "are perfectly valid under state law."
)


# ---------------------------------------------------------------------------
# Extraction (pure)
# ---------------------------------------------------------------------------


class ExtractPremisesTests(SimpleTestCase):
    def test_extracts_the_madden_premise(self):
        ps = extract_premises(MADDEN)
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0].case_label, "Madden v. City of Iowa City")
        # query is the full assertion (name + topic) so retrieval pulls the
        # relevant holding chunk, not an arbitrary one.
        self.assertIn("Madden v. City of Iowa City", ps[0].query)
        self.assertIn("liability-shifting", ps[0].query)
        self.assertIn("madden v. city of iowa city", ps[0].anchors)

    def test_bare_see_cite_is_not_a_premise(self):
        # Named cases but NO holding assertion → not a premise.
        self.assertEqual(
            extract_premises("I have a Smith v. Jones matter; see Doe v. Roe, 1 N.W.2d 2."),
            [],
        )

    def test_hedged_assertion_is_skipped(self):
        self.assertEqual(
            extract_premises("Arguably Madden v. City of Iowa City held ordinances are valid."),
            [],
        )

    def test_treatment_cue_is_skipped(self):
        # User engaging with the case's status, not asserting it as good law.
        self.assertEqual(
            extract_premises("Madden v. City of Iowa City was overruled, but it held X."),
            [],
        )

    def test_verb_before_anchor_does_not_bind(self):
        # "requires" precedes the case anchor → not bound to it (statute talk).
        self.assertEqual(
            extract_premises("Section 364.12 requires maintenance; see Madden v. City of Iowa City."),
            [],
        )

    def test_reporter_cite_only_premise(self):
        ps = extract_premises("The court in 848 N.W.2d 40 held that liability cannot shift.")
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0].case_label, "848 N.W.2d 40")
        self.assertIn("848 N.W.2d 40", ps[0].query)
        self.assertIn("848 n.w.2d 40", ps[0].anchors)

    def test_discussion_verb_not_flagged(self):
        self.assertEqual(
            extract_premises("Madden v. City of Iowa City discusses municipal liability."),
            [],
        )

    def test_caps_at_max_premises(self):
        text = " ".join(
            f"Case{n} v. State{n} held that proposition {n} is true."
            for n in range(6)
        )
        self.assertLessEqual(len(extract_premises(text)), premise.MAX_PREMISES)


# ---------------------------------------------------------------------------
# check_premises (injected fake checker + retriever)
# ---------------------------------------------------------------------------


def _passage(citation="Beth A. Madden v. City of Iowa City, 848 N.W.2d 40",
             heading="Supreme Court of Iowa, 2014",
             excerpt="Shifting tort liability to an abutting owner requires express "
                     "legislative authorization; the ordinance is a tax not authorized.",
             treatment=None) -> RetrievedPassage:
    return RetrievedPassage(
        node_version_id=1, node_id=1, cluster_id=1, path="",
        heading=heading, citation=citation, source_slug="iowa-caselaw",
        chunk_id=None, char_start=None, char_end=None, excerpt=excerpt, snippet="snip",
        effective_from=None, is_repealed=False, score=1.0, component_scores={},
        treatment=treatment or TreatmentFlag(), node_dict={"source_slug": "iowa-caselaw"},
    )


def _passage_with(treatment: TreatmentFlag) -> RetrievedPassage:
    """A Madden passage carrying a specific treatment flag (currency-axis tests)."""
    return _passage(treatment=treatment)


def _retriever(passage):
    def fake(query, **kwargs):
        return RetrievedContext(query=query, passages=[passage] if passage else [],
                                as_of_date="2026-06-09")
    return fake


class _FakeChecker:
    def __init__(self, verdict, evidence="…a tax not authorized by the legislature…"):
        self.verdict = verdict
        self.evidence = evidence
        self.calls: list = []

    def check_claims(self, claims, source_text):
        self.calls.append((list(claims), source_text))
        return [SemanticVerdict(self.verdict, self.evidence) for _ in claims]


class CheckPremisesTests(SimpleTestCase):
    def test_contradicted_premise_is_flagged(self):
        checker = _FakeChecker(CONTRADICTED)
        out = check_premises(MADDEN, checker=checker, retrieve_fn=_retriever(_passage()))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].verdict, CONTRADICTED)
        self.assertEqual(out[0].case_label, "Madden v. City of Iowa City")
        self.assertIn("not authorized", out[0].evidence)
        # the NLI saw the user's premise sentence vs the opinion excerpt
        self.assertIn("perfectly valid", checker.calls[0][0][0])

    def test_partial_premise_is_flagged(self):
        out = check_premises(MADDEN, checker=_FakeChecker(PARTIAL),
                             retrieve_fn=_retriever(_passage()))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].verdict, PARTIAL)

    def test_supported_premise_is_silent(self):
        out = check_premises(MADDEN, checker=_FakeChecker(SUPPORTED),
                             retrieve_fn=_retriever(_passage()))
        self.assertEqual(out, [])

    def test_no_claim_or_unverified_is_silent(self):
        for v in (NO_CLAIM, "unverified"):
            out = check_premises(MADDEN, checker=_FakeChecker(v),
                                 retrieve_fn=_retriever(_passage()))
            self.assertEqual(out, [], v)

    def test_no_checker_runs_currency_only_silent_on_good_law(self):
        # Without a checker the fidelity (NLI) axis is skipped, but the currency
        # axis still runs. A good-law case (default TreatmentFlag → "unknown") is
        # presumed good → no finding.
        out = check_premises(MADDEN, checker=None, retrieve_fn=_retriever(_passage()))
        self.assertEqual(out, [])

    # --- Currency axis (PR7): the orthogonal good-law check ------------------
    def _overruled_passage(self):
        return _passage_with(TreatmentFlag(
            status="negative", severity=5, label="overruled",
            by_citation="Bankers Trust Co. v. City of Des Moines",
            excerpt="We respectfully believe that Madden was wrongly decided… we overrule Madden.",
            source="llm", confidence=0.9,
        ))

    def test_faithful_reading_of_overruled_case_is_flagged(self):
        # THE Bankers Trust trap: the user's reading is FAITHFUL (NLI=SUPPORTED),
        # but the case is overruled → currency axis must still flag it.
        out = check_premises(MADDEN, checker=_FakeChecker(SUPPORTED),
                             retrieve_fn=_retriever(self._overruled_passage()))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].currency, "negative")
        self.assertEqual(out[0].treatment_label, "overruled")
        self.assertIn("Bankers Trust", out[0].treating_case)
        # fidelity was checked and came back clean; the finding stands on currency.
        self.assertEqual(out[0].verdict, SUPPORTED)

    def test_overruled_case_flagged_without_a_checker(self):
        # No OpenAI key (checker=None) — currency is deterministic, so the
        # overruled case is still caught.
        out = check_premises(MADDEN, checker=None,
                             retrieve_fn=_retriever(self._overruled_passage()))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].currency, "negative")
        self.assertEqual(out[0].verdict, "unchecked")

    def test_caution_treatment_is_flagged(self):
        passage = _passage_with(TreatmentFlag(
            status="caution", severity=3, label="overruled-on-other-grounds",
            by_citation="State v. Later", excerpt="…overruled on other grounds…",
        ))
        out = check_premises(MADDEN, checker=_FakeChecker(SUPPORTED),
                             retrieve_fn=_retriever(passage))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].currency, "caution")

    def test_both_axes_bad_records_both(self):
        # Overruled AND misread → one finding carrying both signals.
        out = check_premises(MADDEN, checker=_FakeChecker(CONTRADICTED),
                             retrieve_fn=_retriever(self._overruled_passage()))
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].currency_bad)
        self.assertTrue(out[0].fidelity_bad)

    def test_currency_false_suppresses_currency_axis(self):
        # currency=False must disable the currency axis even for an overruled case
        # (so RAG_CURRENCY_CHECK is honored when fidelity is on). Fidelity still runs.
        out = check_premises(MADDEN, checker=_FakeChecker(SUPPORTED), currency=False,
                             retrieve_fn=_retriever(self._overruled_passage()))
        self.assertEqual(out, [])
        # but a fidelity problem on the same (overruled) passage still surfaces:
        out2 = check_premises(MADDEN, checker=_FakeChecker(CONTRADICTED), currency=False,
                              retrieve_fn=_retriever(self._overruled_passage()))
        self.assertEqual(len(out2), 1)
        self.assertEqual(out2[0].verdict, CONTRADICTED)

    def test_case_not_in_corpus_is_silent(self):
        out = check_premises(MADDEN, checker=_FakeChecker(CONTRADICTED),
                             retrieve_fn=_retriever(None))  # no passages
        self.assertEqual(out, [])

    def test_wrong_case_retrieved_is_silent(self):
        # The retriever returns a DIFFERENT case → anchor overlap fails → no
        # false caution (never verify the premise against the wrong opinion).
        other = _passage(citation="State v. Unrelated, 999 N.W.2d 1",
                         heading="Supreme Court of Iowa, 2000")
        checker = _FakeChecker(CONTRADICTED)
        out = check_premises(MADDEN, checker=checker, retrieve_fn=_retriever(other))
        self.assertEqual(out, [])
        self.assertEqual(checker.calls, [])  # NLI never ran against the wrong case

    def test_picks_the_asserted_case_among_topical_competitors(self):
        # rank 1 is a DIFFERENT (topically on-point) case; the named case is rank
        # 2. We must verify against the NAMED case, not rank 1 (the live bug).
        other = _passage(citation="Bankers Trust v. City of Des Moines, 1 N.W.2d 1",
                         heading="Supreme Court of Iowa, 1990")
        madden = _passage()

        def multi(query, **kwargs):
            return RetrievedContext(query=query, passages=[other, madden],
                                    as_of_date="2026-06-09")

        out = check_premises(MADDEN, checker=_FakeChecker(CONTRADICTED), retrieve_fn=multi)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].case_label, "Madden v. City of Iowa City")

    def test_retrieval_error_does_not_crash(self):
        def boom(query, **kwargs):
            raise RuntimeError("retrieval down")
        self.assertEqual(
            check_premises(MADDEN, checker=_FakeChecker(CONTRADICTED), retrieve_fn=boom),
            [],
        )


class RenderCautionTests(SimpleTestCase):
    def test_caution_names_case_evidence_and_instruction(self):
        f = PremiseFinding(case_label="Madden v. City of Iowa City", sentence=MADDEN,
                           verdict=CONTRADICTED, evidence="a tax not authorized by the legislature")
        out = render_premise_caution([f])
        self.assertIn("PREMISE CHECK", out)
        self.assertIn("Madden v. City of Iowa City", out)
        self.assertIn("CONTRADICTS", out)
        self.assertIn("not authorized", out)
        self.assertIn("search_statutes", out)  # tells the model to verify

    def test_empty_findings_render_nothing(self):
        self.assertEqual(render_premise_caution([]), "")

    def test_currency_caution_demands_correct_then_answer(self):
        f = PremiseFinding(
            case_label="Madden v. City of Iowa City", sentence=MADDEN,
            verdict="supported", evidence="",
            currency="negative", treating_case="Bankers Trust Co. v. City of Des Moines",
            treatment_label="overruled", treatment_evidence="we overrule Madden",
        )
        out = render_premise_caution([f])
        self.assertIn("PREMISE CHECK", out)
        self.assertIn("LEAD", out)           # correct-then-answer instruction (header)
        self.assertIn("search_statutes", out)
        # Tokens UNIQUE to the per-finding currency line (not the static header):
        self.assertIn("OVERRULED", out)                       # severity word
        self.assertIn("overruled by Bankers Trust Co. v. City of Des Moines", out)  # verb+who
        self.assertIn("we overrule Madden", out)              # treatment_evidence flowed through
        # a faithful-but-dead premise must not be dismissed as a misreading
        self.assertIn("FAITHFUL", out)

    def test_currency_finding_serializes_all_axis_keys(self):
        # finding_dicts must carry the currency-axis keys render_advisory reads.
        from apps.corpus.services.premise import finding_dicts
        f = PremiseFinding(
            case_label="Madden v. City of Iowa City", sentence=MADDEN,
            verdict="supported", evidence="",
            currency="negative", treating_case="Bankers Trust Co. v. City of Des Moines",
            treatment_label="overruled", treatment_evidence="we overrule Madden",
        )
        d = finding_dicts([f])[0]
        self.assertEqual(d["currency"], "negative")
        self.assertEqual(d["treating_case"], "Bankers Trust Co. v. City of Des Moines")
        self.assertEqual(d["treatment_label"], "overruled")
        self.assertEqual(d["treatment_evidence"], "we overrule Madden")
        self.assertEqual(d["verdict"], "supported")  # existing keys intact


# ---------------------------------------------------------------------------
# Chat hook gating (_premise_guard)
# ---------------------------------------------------------------------------


class PremiseGuardTests(SimpleTestCase):
    def _msgs(self):
        return [{"role": "user", "content": MADDEN}]

    @override_settings(RAG_CURRENCY_CHECK=False, RAG_PREMISE_CHECK=False)
    def test_both_axes_off_is_noop(self):
        from apps.api import chat
        # Even with a message that names a case, both axes off → no retrieval, no-op.
        with mock.patch.object(chat, "check_premises") as cp:
            self.assertEqual(chat._premise_guard(self._msgs(), None), ("", []))
            cp.assert_not_called()

    @override_settings(RAG_CURRENCY_CHECK=True, RAG_PREMISE_CHECK=False)
    def test_currency_on_by_default_runs_without_a_key(self):
        # Currency is deterministic: the guard runs check_premises with NO checker
        # (no OpenAI key needed) and surfaces an overruled-premise finding.
        from apps.api import chat
        finding = PremiseFinding(
            case_label="Madden v. City of Iowa City", sentence=MADDEN,
            verdict="unchecked", evidence="",
            currency="negative", treating_case="Bankers Trust Co. v. City of Des Moines",
            treatment_label="overruled", treatment_evidence="we overrule Madden",
        )
        with mock.patch.object(chat, "check_premises", return_value=[finding]) as cp:
            caution, problems = chat._premise_guard(self._msgs(), None)
        self.assertEqual(cp.call_args.kwargs["checker"], None)  # fidelity axis off
        self.assertEqual(cp.call_args.kwargs["currency"], True)  # currency axis on
        self.assertIn("Bankers Trust", caution)
        self.assertEqual(problems[0]["currency"], "negative")

    @override_settings(RAG_CURRENCY_CHECK=False, RAG_PREMISE_CHECK=True)
    def test_fidelity_without_key_is_noop(self):
        from apps.api import chat
        with mock.patch.object(chat.semantic_support, "default_checker", return_value=None), \
             mock.patch.object(chat, "check_premises", return_value=[]) as cp:
            self.assertEqual(chat._premise_guard(self._msgs(), None), ("", []))
            # currency explicitly off is threaded through, and no key → checker None.
            self.assertEqual(cp.call_args.kwargs["checker"], None)
            self.assertEqual(cp.call_args.kwargs["currency"], False)

    @override_settings(RAG_CURRENCY_CHECK=True, RAG_PREMISE_CHECK=True)
    def test_flagged_premise_produces_caution_and_problems(self):
        from apps.api import chat
        finding = PremiseFinding(case_label="Madden v. City of Iowa City",
                                 sentence=MADDEN, verdict=CONTRADICTED,
                                 evidence="a tax not authorized")
        sentinel = object()
        with mock.patch.object(chat.semantic_support, "default_checker",
                               return_value=sentinel), \
             mock.patch.object(chat, "check_premises", return_value=[finding]) as cp:
            caution, problems = chat._premise_guard(self._msgs(), None)
        # Both axes on: fidelity gets the real checker, currency stays on.
        self.assertIs(cp.call_args.kwargs["checker"], sentinel)
        self.assertEqual(cp.call_args.kwargs["currency"], True)
        self.assertIn("Madden v. City of Iowa City", caution)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["case"], "Madden v. City of Iowa City")
        self.assertEqual(problems[0]["verdict"], CONTRADICTED)
