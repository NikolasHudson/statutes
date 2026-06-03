"""Tests for the citation-centric document verifier.

Covers the traffic-light rollup table end to end against a real fixture: a
valid cite with a verbatim quote → green, a fabricated quote → red, a
paraphrase → yellow, an unknown cite → red, a repealed cite → yellow, and the
confidence filter that keeps bare numbers out.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase, override_settings

from apps.corpus.models import Node
from apps.corpus.services import lookups
from apps.corpus.services.citation_format import (
    normalize_citation_hyphens,
    source_hint,
)


class HyphenNormalizationTests(SimpleTestCase):
    """Reporter-anchored "chapter-section" hyphens become dots so the citation
    isn't silently dropped — but ranges/dates/§§ stay hyphenated."""

    def test_named_reporter_hyphen_becomes_dot(self):
        self.assertEqual(
            normalize_citation_hyphens("Ia. Code 321-218"), "Ia. Code 321.218"
        )
        self.assertEqual(normalize_citation_hyphens("IRE 5-403"), "IRE 5.403")
        self.assertEqual(
            normalize_citation_hyphens("Ia. Code 321J-2(2)(a)"),
            "Ia. Code 321J.2(2)(a)",
        )

    def test_ranges_and_dates_untouched(self):
        for s in ("sections 1-5 apply", "§§ 1-5", "the 2020-2021 term", "pages 12-15"):
            self.assertEqual(normalize_citation_hyphens(s), s)

    def test_length_preserving(self):
        # Spans must stay aligned, so the rewrite cannot change length.
        s = "served under Ia. Code 321-218 today"
        self.assertEqual(len(normalize_citation_hyphens(s)), len(s))
from apps.corpus.services.verify_document import _claim_sentence


class SourceHintTests(SimpleTestCase):
    """The reporter the author wrote disambiguates a number that exists in more
    than one corpus (e.g. "2.19" is both Iowa Code § 2.19 and Iowa R. Crim. P.
    2.19). Pure-function test of the hint detector."""

    def _hint(self, text: str, needle: str) -> str | None:
        i = text.index(needle)
        return source_hint(text, (i, i + len(needle)))

    def test_ircrp_acronym_points_at_court_rules(self):
        self.assertEqual(
            self._hint("mechanisms set forth in IRCrP 2.19", "2.19"),
            "iowa-court-rules",
        )

    def test_iowa_code_points_at_code(self):
        self.assertEqual(
            self._hint("the contempt power in Iowa Code section 2.19", "2.19"),
            "iowa-code",
        )

    def test_no_reporter_gives_no_hint(self):
        self.assertIsNone(self._hint("governed by 2.19 generally", "2.19"))

    def test_does_not_false_match_mid_word(self):
        # "specifIC" / "requIRE" must not trip the I.C. / IRE acronyms.
        self.assertIsNone(self._hint("the specific 2.19 provision", "2.19"))
        self.assertIsNone(self._hint("statutes require 2.19 compliance", "2.19"))


class ClaimSentenceTests(SimpleTestCase):
    """The semantic layer judges the sentence around a citation, so that
    sentence must be extracted whole. Legal citations are full of dots —
    reporter abbreviations ("Iowa R. Civ. P.") and rule numbers ("1.904") —
    and a naive split on every "." chops the sentence into a useless fragment
    that fails the word-count gate (the bug that left Court Rules cites
    unchecked)."""

    def test_court_rule_citation_keeps_full_sentence(self):
        text = (
            "The appellant preserved error by filing a motion to amend and "
            "enlarge pursuant to Iowa R. Civ. P. 1.904(2). The court denied it."
        )
        # Span of the "1.904(2)" cite.
        idx = text.index("1.904(2)")
        claim = _claim_sentence(text, (idx, idx + len("1.904(2)")))
        self.assertTrue(claim.startswith("The appellant preserved error"))
        self.assertGreaterEqual(len(claim.split()), 6)
        self.assertNotIn("The court denied it", claim)

    def test_sentence_ending_in_citation_number_does_not_swallow_next(self):
        # A sentence that ENDS in a rule/section number ("...1.305.") must still
        # break — otherwise several sentences (and their distinct citations)
        # collapse into one blob fed to every cite. Regression for the
        # "paragraph slurper" bug.
        text = (
            "Service was attempted under Iowa R. Civ. P. 1.305. The Defendant "
            "objected under Iowa Code section 617.3. The appeal followed."
        )
        idx = text.index("1.305")
        claim = _claim_sentence(text, (idx, idx + len("1.305")))
        self.assertTrue(claim.startswith("Service was attempted"))
        self.assertNotIn("The Defendant objected", claim)
        # And the second citation gets its own sentence, not the first.
        idx2 = text.index("617.3")
        claim2 = _claim_sentence(text, (idx2, idx2 + len("617.3")))
        self.assertTrue(claim2.startswith("The Defendant objected"))

    def test_ia_abbreviation_does_not_split_sentence(self):
        # "Ia." (Iowa) precedes a reporter and must not be read as a sentence
        # end — otherwise a sentence citing two rules gets sliced in half and
        # the second cite loses its substance check. Regression.
        text = (
            "The statement was non-hearsay under Iowa R. Evid. 5.801(c), and "
            "the motion failed the rules in Ia. R. Civ. P. 1.413(1). The court "
            "agreed."
        )
        idx = text.index("5.801(c)")
        claim = _claim_sentence(text, (idx, idx + len("5.801(c)")))
        self.assertIn("1.413(1)", claim)  # whole sentence, through both cites
        self.assertNotIn("The court agreed", claim)

    def test_following_sentence_selected_for_second_cite(self):
        text = (
            "A motion under Iowa R. Civ. P. 1.904(2) was filed. The rule in "
            "Iowa R. App. P. 6.101(1)(b) sets a thirty-day window for appeal."
        )
        idx = text.index("6.101(1)(b)")
        claim = _claim_sentence(text, (idx, idx + len("6.101(1)(b)")))
        self.assertTrue(claim.startswith("The rule in"))
        self.assertIn("thirty-day window", claim)

    def test_dash_led_heading_breaks_from_prior_sentence(self):
        # A citation living in a dash-joined section heading must NOT inherit the
        # previous sentence's claim — otherwise the heading's cite is graded
        # against an unrelated assertion and reads as a contradiction. Regression
        # for the demand-letter "§ 554.2314 contradicted" false positive.
        text = (
            "Any disclaimer is inoperative under Iowa Code § 554.2316(1) because "
            "it cannot negate your written descriptions. - IV. Breach of Implied "
            "Warranty of Merchantability (Iowa Code § 554.2314)."
        )
        idx = text.index("554.2314")
        claim = _claim_sentence(text, (idx, idx + len("554.2314")))
        self.assertTrue(claim.startswith("IV. Breach of Implied Warranty"))
        self.assertNotIn("disclaimer is inoperative", claim)
        # And the disclaimer cite keeps its own sentence, minus the heading.
        idx2 = text.index("554.2316(1)")
        claim2 = _claim_sentence(text, (idx2, idx2 + len("554.2316(1)")))
        self.assertIn("disclaimer is inoperative", claim2)
        self.assertNotIn("Breach of Implied Warranty", claim2)
from apps.corpus.services.semantic_support import SemanticVerdict
from apps.corpus.services.verify_document import (
    GREEN,
    RED,
    YELLOW,
    verify_document,
)
from apps.api.tests._factories import make_iowa_corpus_minimal


class _FakeChecker:
    """Returns a fixed verdict for every claim, and records what it saw."""

    def __init__(self, verdict: str, evidence: str = "ev"):
        self._v = SemanticVerdict(verdict, evidence)
        self.calls: list[tuple[list[str], str]] = []

    def check_claims(self, claims, source_text):
        self.calls.append((claims, source_text))
        return [SemanticVerdict(self._v.verdict, self._v.evidence) for _ in claims]


# Disable the semantic (OpenAI) layer so these deterministic verbatim/resolution
# tests are hermetic — the semantic-specific tests inject a fake checker instead.
@override_settings(OPENAI_API_KEY="")
class VerifyDocumentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.src, cls.section, cls.version = make_iowa_corpus_minimal()
        # A repealed section in the same chapter, no current version.
        cls.repealed = Node.objects.create(
            source=cls.src,
            node_type=cls.section.node_type,
            parent=cls.section.parent,
            ordinal="99",
            path="714.99",
            heading="Old repealed provision",
            is_repealed=True,
        )

    def setUp(self):
        # The default-source cache can carry a stale row across the test DB
        # teardown of sibling TransactionTestCases.
        lookups.reset_default_source_cache()

    def _find(self, report, raw_contains):
        for f in report.findings:
            if raw_contains in f.raw:
                return f
        self.fail(f"no finding matching {raw_contains!r} in {[f.raw for f in report.findings]}")

    def test_valid_cite_with_verbatim_quote_is_green(self):
        text = (
            'Under Iowa Code § 714.16, a "merchant who commits a deceptive '
            'practice or unfair method of competition violates this section."'
        )
        report = verify_document(text, sources=[self.src])
        f = self._find(report, "714.16")
        self.assertEqual(f.status, GREEN)
        self.assertEqual(f.resolution, "valid")
        self.assertTrue(any(lc.verdict == "exact" for lc in f.language_checks))

    def test_valid_cite_with_fabricated_quote_is_red(self):
        text = (
            'Iowa Code § 714.16 provides that "every merchant must carry '
            'liability insurance of no less than one million dollars."'
        )
        report = verify_document(text, sources=[self.src])
        f = self._find(report, "714.16")
        self.assertEqual(f.status, RED)
        self.assertTrue(any(lc.verdict == "not_found" for lc in f.language_checks))

    def test_valid_cite_with_paraphrase_quote_is_yellow(self):
        # A near-verbatim quote with quiet edits — should fuzzy-match (>=0.85)
        # rather than match exactly, landing yellow.
        text = (
            'Iowa Code § 714.16 states that "a merchant which commits a '
            'deceptive practice or unfair method of competition violates this '
            'section."'
        )
        report = verify_document(text, sources=[self.src])
        f = self._find(report, "714.16")
        self.assertEqual(f.status, YELLOW)
        self.assertTrue(any(lc.verdict == "fuzzy" for lc in f.language_checks))

    def test_unknown_cite_is_red(self):
        text = "See Iowa Code § 714.404 for the controlling rule."
        report = verify_document(text, sources=[self.src])
        f = self._find(report, "714.404")
        self.assertEqual(f.status, RED)
        self.assertEqual(f.resolution, "not_found")

    def test_repealed_cite_is_yellow(self):
        text = "The defense rests on Iowa Code § 714.99."
        report = verify_document(text, sources=[self.src])
        f = self._find(report, "714.99")
        self.assertEqual(f.status, YELLOW)
        self.assertEqual(f.resolution, "repealed")

    def test_valid_cite_without_quote_is_green(self):
        text = "Liability here is governed by Iowa Code § 714.16."
        report = verify_document(text, sources=[self.src])
        f = self._find(report, "714.16")
        self.assertEqual(f.status, GREEN)
        self.assertEqual(f.language_checks, [])

    def test_bare_numbers_are_not_graded(self):
        # "within 90 days" / "$1,000" must not show up as citations.
        text = "The merchant had within 90 days to refund the $1,000 fee."
        report = verify_document(text, sources=[self.src])
        self.assertEqual(report.findings, [])

    def test_ambiguous_bare_decimal_in_prose_is_dropped(self):
        # "4.1" here is an engine size, not a cite to Iowa Code § 4.1. With no
        # citation cue near it, it must not be graded. Regression for the
        # demand-letter "4.1 contradicted" false positive.
        text = "He ordered a top of the line 4.1 motor for the pull truck."
        report = verify_document(text, sources=[self.src], semantic=None)
        self.assertEqual(report.findings, [])

    def test_short_decimal_with_cue_is_kept(self):
        # The same shape WITH a preceding cue ("rule 4.1") is a real citation
        # and must still be graded — the cue is recovered from the left context
        # even though the matched token is bare.
        text = "The motion was governed by rule 4.1 of the local procedures."
        report = verify_document(text, sources=[self.src], semantic=None)
        self._find(report, "4.1")  # fails if it was dropped

    def test_bare_unambiguous_section_still_graded(self):
        # A sigil-less but structurally unambiguous cite ("714.16", 3-digit
        # chapter) must keep grading — the bare-decimal guard targets only the
        # short N.M shape.
        text = "Liability under 714.16 controls this dispute."
        report = verify_document(text, sources=[self.src], semantic=None)
        f = self._find(report, "714.16")
        self.assertEqual(f.status, GREEN)

    def test_paraphrase_supported_is_green(self):
        text = (
            "Iowa Code § 714.16 makes deceptive practices by a merchant "
            "unlawful and a violation of the section."
        )
        checker = _FakeChecker("supported")
        report = verify_document(text, sources=[self.src], semantic=checker)
        f = self._find(report, "714.16")
        self.assertEqual(f.status, GREEN)
        self.assertTrue(any(lc.kind == "paraphrase" for lc in f.language_checks))
        # The whole sentence was handed to the checker against the rule body.
        self.assertEqual(len(checker.calls), 1)

    def test_paraphrase_contradicted_is_red(self):
        text = (
            "Iowa Code § 714.16 requires every merchant to carry one million "
            "dollars of liability insurance at all times."
        )
        checker = _FakeChecker("contradicted")
        report = verify_document(text, sources=[self.src], semantic=checker)
        f = self._find(report, "714.16")
        self.assertEqual(f.status, RED)

    def test_paraphrase_partial_is_yellow(self):
        text = "Iowa Code § 714.16 broadly governs all merchant advertising statewide."
        checker = _FakeChecker("partial")
        report = verify_document(text, sources=[self.src], semantic=checker)
        f = self._find(report, "714.16")
        self.assertEqual(f.status, YELLOW)

    def test_unverified_paraphrase_is_yellow(self):
        text = "Iowa Code § 714.16 makes certain merchant conduct unlawful here."
        checker = _FakeChecker("unverified")
        report = verify_document(text, sources=[self.src], semantic=checker)
        f = self._find(report, "714.16")
        self.assertEqual(f.status, YELLOW)

    def test_quoted_cite_skips_semantic_check(self):
        # A cite carrying a verbatim quote must NOT also be sent to the LLM.
        text = (
            'Iowa Code § 714.16 says a "merchant who commits a deceptive '
            'practice or unfair method of competition violates this section."'
        )
        checker = _FakeChecker("contradicted")
        report = verify_document(text, sources=[self.src], semantic=checker)
        f = self._find(report, "714.16")
        self.assertEqual(f.status, GREEN)
        self.assertEqual(checker.calls, [])

    def test_semantic_disabled_grades_verbatim_only(self):
        text = "Iowa Code § 714.16 makes deceptive merchant practices unlawful."
        report = verify_document(text, sources=[self.src], semantic=None)
        f = self._find(report, "714.16")
        self.assertEqual(f.status, GREEN)
        self.assertEqual(f.language_checks, [])

    def test_form_renders_canonical_for_iowa_code(self):
        text = "Liability is governed by Iowa Code section 714.16."
        report = verify_document(text, sources=[self.src], semantic=None)
        f = self._find(report, "714.16")
        self.assertEqual(f.form.status, "ok")
        self.assertEqual(f.form.canonical, "Iowa Code § 714.16")

    def test_form_flags_unresolvable_with_near_match(self):
        # A chapter-714 section that doesn't exist but is one trailing digit off
        # a real one ("714.166" -> "714.16(6)"-ish). Use 714.16 as the anchor.
        text = "See Iowa Code section 714.162 for the rule."
        report = verify_document(text, sources=[self.src], semantic=None)
        f = self._find(report, "714.162")
        self.assertEqual(f.status, RED)
        self.assertEqual(f.form.status, "unresolvable")
        self.assertEqual(f.form.canonical, "Iowa Code § 714.16(2)")

    def test_form_recovers_dropped_trailing_subdivision(self):
        # "714.16(2)a" — the bare "a" after a parenthesized subdivision is
        # dropped by the parser; the form check must recover it so the canonical
        # is (2)(a), not (2).
        text = "The merchant rule appears at Iowa Code section 714.16(2)a here."
        report = verify_document(text, sources=[self.src], semantic=None)
        f = self._find(report, "714.16")
        self.assertEqual(f.form.status, "corrected")
        self.assertEqual(f.form.canonical, "Iowa Code § 714.16(2)(a)")

    def test_dollar_amount_survives_into_claim_sentence(self):
        # The citation-scrubber blanks "$amounts" so they aren't parsed as
        # citations, but the claim sent to the semantic checker must KEEP them —
        # otherwise a "$50 vs $500" threshold error is invisible. Regression for
        # the "math leak".
        from apps.corpus.services.verify_document import _build_findings

        text = "Under Iowa Code section 714.16 a merchant owing over $50 is liable."
        findings, claim_text = _build_findings(text, [self.src], False)
        f = self._find_in(findings, "714.16")
        claim = _claim_sentence(claim_text, f.span)
        self.assertIn("$50", claim)

    def _find_in(self, findings, raw_contains):
        for f in findings:
            if raw_contains in f.raw:
                return f
        self.fail(f"no finding matching {raw_contains!r}")

    def test_summary_counts(self):
        text = (
            'Iowa Code § 714.16 says a "merchant who commits a deceptive '
            'practice or unfair method of competition violates this section." '
            "But Iowa Code § 714.404 is fictional, and § 714.99 is repealed."
        )
        report = verify_document(text, sources=[self.src])
        summary = report.summary()
        self.assertEqual(summary["green"], 1)
        self.assertEqual(summary["red"], 1)
        self.assertEqual(summary["yellow"], 1)
        self.assertEqual(summary["total"], 3)
