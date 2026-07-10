"""PR9 web-currency tests: the durable research-note lifecycle (check once,
read forever), the reliance/budget/citator-skip gates in verify_answer, and
the review-queue suppression rules."""

from __future__ import annotations

import datetime as dt
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.api.tests._factories import make_caselaw_case
from apps.corpus.models import CaseResearchNote, ReporterCitation
from apps.corpus.services import web_currency
from apps.corpus.services.answer import render_advisory, verify_answer
from apps.corpus.services.retrieval import (
    RetrievedContext,
    RetrievedPassage,
    TreatmentFlag,
)

ADVERSE = {
    "adverse": True,
    "kind": "overruled",
    "by": "Doe v. Western Dubuque Community School District, 20 N.W.3d 798 (Iowa 2025)",
    "evidence": "To the extent Nahas said something different, we overrule it.",
    "source_url": "https://example.org/doe",
}
CLEAR = {"adverse": False, "kind": "none", "by": "", "evidence": "", "source_url": ""}


class FakeChecker:
    model = "fake"

    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0
        self.topics: list[str] = []

    def check(self, heading, citation, topic=""):
        self.calls += 1
        self.topics.append(topic)
        return self.verdict


def passage(decision, *, citation="Nahas v. Polk County, 991 N.W.2d 770 (Iowa 2023)",
            treatment=None):
    return RetrievedPassage(
        node_version_id=decision.id, node_id=decision.id, cluster_id=decision.id,
        path=decision.path, heading="Supreme Court of Iowa, 2023",
        citation=citation, source_slug="iowa-caselaw", chunk_id=None,
        char_start=None, char_end=None, excerpt="", snippet="",
        effective_from=None, is_repealed=False, score=1.0, component_scores={},
        treatment=treatment or TreatmentFlag(), node_dict={},
    )


def ctx(*passages):
    return RetrievedContext(query="q", passages=list(passages), as_of_date="2026-07-10")


RELYING_ANSWER = (
    "Under Nahas v. Polk County, 991 N.W.2d 770, the heightened pleading "
    "standard applies."
)


class NoteLifecycleTests(TestCase):
    def setUp(self):
        self.decision, _, _ = make_caselaw_case(cl_cluster_id=1, cl_opinion_id=1)
        # Make the claimed overruling authority corpus-resolvable by name.
        make_caselaw_case(
            cl_cluster_id=2, cl_opinion_id=2,
            case_name="Doe v. Western Dubuque Community School District",
        )

    def test_adverse_verdict_persists_and_is_corpus_verified(self):
        checker = FakeChecker(ADVERSE)
        note = web_currency.check_and_store(
            self.decision.id, "Supreme Court of Iowa, 2023",
            "Nahas v. Polk County, 991 N.W.2d 770", checker,
        )
        self.assertEqual(note.status, CaseResearchNote.Status.ADVERSE)
        self.assertEqual(note.adverse_kind, "overruled")
        self.assertTrue(note.corpus_verified)
        self.assertIn("Doe", note.claimed_by)
        self.assertEqual(note.review_status, CaseResearchNote.Review.PENDING)
        self.assertTrue(web_currency.advisory_worthy(note))

    def test_clear_verdict_fresh_note_needs_no_recheck(self):
        note = web_currency.check_and_store(
            self.decision.id, "h", "c", FakeChecker(CLEAR)
        )
        self.assertEqual(note.status, CaseResearchNote.Status.CLEAR)
        self.assertTrue(web_currency.note_is_current(note))
        self.assertFalse(web_currency.advisory_worthy(note))

    def test_stale_clear_note_is_not_current(self):
        note = web_currency.check_and_store(
            self.decision.id, "h", "c", FakeChecker(CLEAR)
        )
        CaseResearchNote.objects.filter(pk=note.pk).update(
            checked_at=timezone.now() - dt.timedelta(days=45)
        )
        note.refresh_from_db()
        self.assertFalse(web_currency.note_is_current(note))

    def test_adverse_note_is_always_current(self):
        note = web_currency.check_and_store(
            self.decision.id, "h", "c", FakeChecker(ADVERSE)
        )
        CaseResearchNote.objects.filter(pk=note.pk).update(
            checked_at=timezone.now() - dt.timedelta(days=400)
        )
        note.refresh_from_db()
        self.assertTrue(web_currency.note_is_current(note))

    def test_rejection_sticks_across_recheck_of_same_claim(self):
        note = web_currency.check_and_store(
            self.decision.id, "h", "c", FakeChecker(ADVERSE)
        )
        note.review_status = CaseResearchNote.Review.REJECTED
        note.save(update_fields=["review_status"])
        note = web_currency.check_and_store(
            self.decision.id, "h", "c", FakeChecker(ADVERSE)
        )
        self.assertEqual(note.review_status, CaseResearchNote.Review.REJECTED)
        self.assertFalse(web_currency.advisory_worthy(note))

    def test_unverifiable_claim_stored_but_not_advisory_worthy(self):
        bogus = dict(ADVERSE, by="Totally Fabricated v. Nonexistent, 1 X.Y.Z. 1")
        note = web_currency.check_and_store(
            self.decision.id, "h", "c", FakeChecker(bogus)
        )
        self.assertEqual(note.status, CaseResearchNote.Status.ADVERSE)
        self.assertFalse(note.corpus_verified)
        self.assertFalse(web_currency.advisory_worthy(note))

    def test_checker_failure_returns_existing_note(self):
        first = web_currency.check_and_store(
            self.decision.id, "h", "c", FakeChecker(CLEAR)
        )
        broken = FakeChecker(None)
        note = web_currency.check_and_store(self.decision.id, "h", "c", broken)
        self.assertEqual(note.pk, first.pk)

    def test_corpus_verify_statute_and_reporter_paths(self):
        ReporterCitation.objects.create(
            cl_citation_id=9, cl_cluster_id=9, reporter="N.W.2d",
            volume="991", page="770", to_node=self.decision,
        )
        ok, matches = web_currency.corpus_verify("991 N.W.2d 770")
        self.assertTrue(ok)
        self.assertIn("case cite 991 N.W.2d 770", matches)


class VerifyAnswerWiringTests(TestCase):
    def setUp(self):
        self.decision, _, _ = make_caselaw_case(cl_cluster_id=1, cl_opinion_id=1)
        make_caselaw_case(
            cl_cluster_id=2, cl_opinion_id=2,
            case_name="Doe v. Western Dubuque Community School District",
        )

    def report(self, checker, *, content=RELYING_ANSWER, passages=None):
        return verify_answer(
            content,
            context=ctx(*(passages or [passage(self.decision)])),
            web_currency_checker=checker,
        )

    def test_relied_on_case_gets_checked_and_flagged(self):
        checker = FakeChecker(ADVERSE)
        report = self.report(checker)
        self.assertEqual(checker.calls, 1)
        (problem,) = report["web_currency_problems"]
        self.assertEqual(problem["kind"], "overruled")
        self.assertFalse(report["ok"])
        advisory = render_advisory(report)
        self.assertIn("Secondary sources indicate", advisory)
        self.assertIn("pending attorney review", advisory)
        self.assertIn("Nahas", advisory)

    def test_note_is_read_not_rechecked_on_second_answer(self):
        checker = FakeChecker(ADVERSE)
        self.report(checker)
        report = self.report(checker)
        self.assertEqual(checker.calls, 1)  # second answer read the stored note
        self.assertEqual(len(report["web_currency_problems"]), 1)

    def test_unrelied_case_not_checked(self):
        checker = FakeChecker(ADVERSE)
        report = self.report(checker, content="Iowa recognizes negligence claims.")
        self.assertEqual(checker.calls, 0)
        self.assertEqual(report["web_currency_problems"], [])

    def test_negative_citator_flag_skipped(self):
        checker = FakeChecker(ADVERSE)
        flagged = passage(
            self.decision,
            treatment=TreatmentFlag(status="negative", severity=5, label="overruled"),
        )
        report = self.report(checker, passages=[flagged])
        self.assertEqual(checker.calls, 0)
        self.assertEqual(report["web_currency_problems"], [])

    def test_caution_flag_is_still_web_checked(self):
        """Phrase-derived caution labels can be wrong-sided (Frohwein carried
        'overruled-on-other-grounds' while Youngblut overruled it ON the
        relied-upon point) — so caution does NOT suppress the web check."""
        checker = FakeChecker(ADVERSE)
        cautioned = passage(
            self.decision,
            treatment=TreatmentFlag(
                status="caution", severity=3, label="overruled-on-other-grounds"
            ),
        )
        report = self.report(checker, passages=[cautioned])
        self.assertEqual(checker.calls, 1)
        self.assertEqual(len(report["web_currency_problems"]), 1)

    @override_settings(RAG_WEB_CURRENCY_BUDGET=1)
    def test_budget_caps_new_checks(self):
        d2, _, _ = make_caselaw_case(
            cl_cluster_id=3, cl_opinion_id=3, case_name="Roe v. Wade County"
        )
        checker = FakeChecker(ADVERSE)
        content = (
            "Under Nahas v. Polk County, 991 N.W.2d 770, and Roe v. Wade "
            "County, 900 N.W.2d 1, the standard applies."
        )
        p2 = passage(d2, citation="Roe v. Wade County, 900 N.W.2d 1 (Iowa 2020)")
        self.report(checker, content=content,
                    passages=[passage(self.decision), p2])
        self.assertEqual(checker.calls, 1)  # budget of 1 new check honored

    def test_flag_off_and_no_checker_is_a_noop(self):
        report = verify_answer(
            RELYING_ANSWER, context=ctx(passage(self.decision))
        )
        self.assertEqual(report["web_currency_problems"], [])

    def test_acknowledged_adverse_authority_not_flagged(self):
        """An answer that already tells the reader about the overruling has
        handled it — no redundant advisory (mirrors stale-use acknowledged).
        Found live 2026-07-10: the Godfrey answer correctly said 'overruled by
        Burnett' and still would have drawn a 'may have been overruled' note."""
        checker = FakeChecker(ADVERSE)
        acknowledging = (
            "Nahas v. Polk County, 991 N.W.2d 770, was overruled in part by "
            "Doe v. Western Dubuque Community School District, so the pleading "
            "standard no longer applies."
        )
        report = self.report(checker, content=acknowledging)
        self.assertEqual(checker.calls, 1)  # note still written for the future
        self.assertEqual(report["web_currency_problems"], [])

        # The same stored note DOES flag a later answer that relies silently.
        report = self.report(checker)
        self.assertEqual(len(report["web_currency_problems"]), 1)
        self.assertEqual(checker.calls, 1)

    def test_statute_supersession_acknowledged_by_citing_the_section(self):
        """A statute-superseded note's acknowledgment is naming the SECTION:
        an answer that already cites § 668.14A has engaged the supersession."""
        from apps.api.tests._factories import make_iowa_corpus_minimal

        make_iowa_corpus_minimal()  # so the claimed § 714.16 corpus-verifies
        statute_verdict = dict(
            ADVERSE,
            kind="superseded_by_statute",
            by="Iowa Code §714.16 (2020)",
        )
        checker = FakeChecker(statute_verdict)
        acknowledging = (
            "Nahas v. Polk County, 991 N.W.2d 770, stated the old rule, but "
            "Iowa Code § 714.16 now governs this question."
        )
        report = self.report(checker, content=acknowledging)
        self.assertEqual(report["web_currency_problems"], [])
        # Silent reliance still draws the flag from the stored note.
        report = self.report(checker)
        self.assertEqual(len(report["web_currency_problems"]), 1)

    def test_rejected_note_suppressed_in_report(self):
        checker = FakeChecker(ADVERSE)
        self.report(checker)
        CaseResearchNote.objects.update(
            review_status=CaseResearchNote.Review.REJECTED
        )
        report = self.report(checker)
        self.assertEqual(report["web_currency_problems"], [])
        self.assertEqual(checker.calls, 1)  # adverse note current: no re-check


class ConstructionNoteTests(TestCase):
    """kind=construction notes surface inside tool results (_node_dict) so the
    model reads scope guidance WITH the authority — the Eddy/§123.92 fix."""

    def test_construction_note_injected_into_node_dict(self):
        from django.utils import timezone as tz

        from apps.api.tests._factories import make_iowa_corpus_minimal
        from apps.corpus.services.corpus_tools import lookup_citation_tool

        _, section, _ = make_iowa_corpus_minimal()
        CaseResearchNote.objects.create(
            node=section, kind=CaseResearchNote.Kind.CONSTRUCTION,
            status=CaseResearchNote.Status.ADVERSE,
            adverse_kind="scope_limitation",
            claimed_by="Some v. Case, 1 N.W.2d 1 (Iowa 1990)",
            evidence="SCOPE: does not reach private one-off sales.",
            corpus_verified=True, review_status=CaseResearchNote.Review.PENDING,
            model="manual", checked_at=tz.now(),
        )
        result = lookup_citation_tool("714.16")
        node_dict = result["section"]["node"]
        self.assertIn("does not reach private one-off sales", node_dict["research_note"])
        self.assertIn("Some v. Case", node_dict["research_note"])

    def test_rejected_construction_note_never_surfaces(self):
        from django.utils import timezone as tz

        from apps.api.tests._factories import make_iowa_corpus_minimal
        from apps.corpus.services.corpus_tools import lookup_citation_tool

        _, section, _ = make_iowa_corpus_minimal()
        CaseResearchNote.objects.create(
            node=section, kind=CaseResearchNote.Kind.CONSTRUCTION,
            status=CaseResearchNote.Status.ADVERSE, evidence="bogus",
            review_status=CaseResearchNote.Review.REJECTED,
            model="manual", checked_at=tz.now(),
        )
        result = lookup_citation_tool("714.16")
        self.assertNotIn("research_note", result["section"]["node"])
