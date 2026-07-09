"""PR8 domain-applicability tests: a real, accurately-quoted, current citation
from the WRONG body of law must surface in the report and advisory — and the
whole layer must be a strict no-op when neither a checker nor the flag is on."""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.api.tests._factories import make_iowa_corpus_minimal
from apps.corpus.services.answer import render_advisory, verify_answer
from apps.corpus.services.applicability import _parse_verdicts


class FakeChecker:
    """Deterministic stand-in for the LLM checker; records what it was asked."""

    def __init__(self, fits: dict[str, str]):
        self.fits = fits  # raw-cite substring -> fit
        self.calls: list[tuple[str, list[dict]]] = []

    def check(self, question, authorities):
        self.calls.append((question, authorities))
        out = []
        for a in authorities:
            for needle, fit in self.fits.items():
                if needle in a["raw"]:
                    out.append({**a, "fit": fit, "reason": f"fake: {fit}"})
        return out


ANSWER = (
    "Under Iowa Code § 714.16, a deceptive practice in the sale of "
    "merchandise is unlawful."
)
QUESTION = "Can my client keep a residential tenant's deposit as liquidated damages?"


class ApplicabilityGateTests(TestCase):
    def setUp(self):
        make_iowa_corpus_minimal()  # resolvable § 714.16 ("Consumer fraud")

    def test_inapplicable_verdict_flags_report_and_advisory(self):
        checker = FakeChecker({"714.16": "inapplicable"})
        report = verify_answer(
            ANSWER, question=QUESTION, applicability_checker=checker
        )
        self.assertFalse(report["ok"])
        (problem,) = report["domain_problems"]
        self.assertEqual(problem["fit"], "inapplicable")
        self.assertIn("714.16", problem["raw"])
        self.assertEqual(problem["heading"], "Consumer fraud")

        advisory = render_advisory(report)
        self.assertIn("may not govern this fact pattern", advisory)
        self.assertIn("714.16", advisory)

        # The checker was asked about the resolved authority with its heading.
        (question, authorities) = checker.calls[0]
        self.assertEqual(question, QUESTION)
        self.assertEqual(authorities[0]["heading"], "Consumer fraud")

    def test_governs_and_analogy_are_not_problems(self):
        for fit in ("governs", "analogy"):
            report = verify_answer(
                ANSWER,
                question=QUESTION,
                applicability_checker=FakeChecker({"714.16": fit}),
            )
            self.assertEqual(report["domain_problems"], [])
            self.assertTrue(report["ok"], fit)

    def test_no_checker_and_flag_off_is_a_noop(self):
        report = verify_answer(ANSWER, question=QUESTION)
        self.assertEqual(report["domain_problems"], [])
        self.assertTrue(report["ok"])

    @override_settings(RAG_APPLICABILITY_CHECK=True, OPENAI_API_KEY="")
    def test_flag_on_without_key_stays_silent(self):
        # default_checker() is None without a key: no crash, no problems.
        report = verify_answer(ANSWER, question=QUESTION)
        self.assertEqual(report["domain_problems"], [])

    def test_no_question_skips_the_check(self):
        checker = FakeChecker({"714.16": "inapplicable"})
        report = verify_answer(ANSWER, applicability_checker=checker)
        self.assertEqual(report["domain_problems"], [])
        self.assertEqual(checker.calls, [])


class ParseVerdictTests(TestCase):
    AUTH = [{"raw": "Iowa Code § 714.16", "heading": "Consumer fraud"}]

    def test_malformed_verdicts_dropped(self):
        data = {
            "verdicts": [
                {"i": 0, "fit": "inapplicable", "reason": "wrong domain"},
                {"i": 0, "fit": "governs"},  # duplicate index: dropped
                {"i": 7, "fit": "inapplicable"},  # out of range
                {"i": "x", "fit": "inapplicable"},  # bad index
                {"i": 0, "fit": "maybe"},  # unknown category
                "not-a-dict",
            ]
        }
        out = _parse_verdicts(data, self.AUTH)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["fit"], "inapplicable")

    def test_non_dict_payload_is_empty(self):
        self.assertEqual(_parse_verdicts(["nope"], self.AUTH), [])
        self.assertEqual(_parse_verdicts(None, self.AUTH), [])
