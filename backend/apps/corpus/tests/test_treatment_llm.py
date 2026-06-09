"""Tests for the PR5 LLM-assisted treatment classifier (v2) and the
``annotate_treatment --llm`` refinement pass.

The classifier-logic tests are pure (no LLM, no DB). The command tests inject a
scripted fake classifier and a minimal real-shaped caselaw fixture (a target
decision overruled by a citing opinion, joined by a CASELAW_GRAPH edge) to prove
the keep / drop / override policy.
"""

from __future__ import annotations

import json
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.core.management import call_command
from io import StringIO

from apps.api.tests._factories import make_caselaw_case
from apps.corpus.models import CrossReference, CrossReferenceSource, Node
from apps.corpus.services import treatment_llm
from apps.corpus.services.treatment_llm import (
    UNKNOWN_VERDICT,
    LLMTreatmentVerdict,
    OpenAITreatmentClassifier,
    paragraph_around,
    parse_verdict,
)
from apps.corpus.management.commands import annotate_treatment


# ---------------------------------------------------------------------------
# parse_verdict (pure)
# ---------------------------------------------------------------------------


def _json(**kw) -> str:
    return json.dumps(kw)


class ParseVerdictTests(SimpleTestCase):
    def test_confident_overrule(self):
        v = parse_verdict(_json(label="overruled", target_is_subject=True,
                                evidence="We overrule Target.", confidence=0.9))
        self.assertEqual(v.label, "overruled")
        self.assertEqual(v.severity, 5)
        self.assertEqual(v.status, "negative")
        self.assertTrue(v.is_negative)
        self.assertEqual(v.confidence, 0.9)
        self.assertEqual(v.evidence, "We overrule Target.")

    def test_limited_is_caution_severity_three(self):
        v = parse_verdict(_json(label="limited", target_is_subject=True,
                                evidence="x", confidence=0.8))
        self.assertEqual(v.severity, 3)
        self.assertEqual(v.status, "caution")
        self.assertTrue(v.is_negative)

    def test_none_label_is_not_negative(self):
        v = parse_verdict(_json(label="none", target_is_subject=True,
                                evidence="", confidence=0.9))
        self.assertFalse(v.is_negative)
        self.assertEqual(v.severity, 0)

    def test_not_subject_is_not_negative(self):
        # The classic v1 false positive: stem is about a DIFFERENT case.
        v = parse_verdict(_json(label="overruled", target_is_subject=False,
                                evidence="x", confidence=0.95))
        self.assertFalse(v.is_negative)
        # confidence is preserved so the caller can act on a confident rejection.
        self.assertEqual(v.confidence, 0.95)

    def test_quoted_string_false_subject_is_not_negative(self):
        # A non-conforming quoted boolean must still read as not-subject (a bare
        # bool("false") is truthy → would flip a confident rejection unsafely).
        for raw in ('{"label":"overruled","target_is_subject":"false","confidence":0.9}',
                    '{"label":"overruled","target_is_subject":"0","confidence":0.9}',
                    '{"label":"overruled","target_is_subject":"no","confidence":0.9}'):
            v = parse_verdict(raw)
            self.assertFalse(v.is_negative, raw)
        # …but a quoted "true" still confirms.
        self.assertTrue(parse_verdict(
            '{"label":"overruled","target_is_subject":"true","confidence":0.9}'
        ).is_negative)

    def test_unknown_label_degrades_to_unknown(self):
        v = parse_verdict(_json(label="frobnicated", target_is_subject=True,
                                confidence=0.9))
        self.assertEqual(v, UNKNOWN_VERDICT)

    def test_malformed_json_degrades_to_unknown(self):
        self.assertEqual(parse_verdict("not json at all"), UNKNOWN_VERDICT)
        self.assertEqual(parse_verdict("[1,2,3]"), UNKNOWN_VERDICT)

    def test_confidence_is_clamped(self):
        self.assertEqual(parse_verdict(_json(label="overruled",
                         target_is_subject=True, confidence=5)).confidence, 1.0)
        self.assertEqual(parse_verdict(_json(label="overruled",
                         target_is_subject=True, confidence=-1)).confidence, 0.0)

    def test_bad_confidence_type_is_zero(self):
        v = parse_verdict(_json(label="overruled", target_is_subject=True,
                                confidence="high"))
        self.assertEqual(v.confidence, 0.0)


class ParagraphAroundTests(SimpleTestCase):
    def test_centers_on_evidence(self):
        body = ("A" * 1000) + " TRIGGER SENTENCE here. " + ("B" * 1000)
        para = paragraph_around(body, "TRIGGER SENTENCE here.", window=50)
        self.assertIn("TRIGGER SENTENCE", para)
        self.assertLess(len(para), len(body))

    def test_missing_evidence_falls_back_to_evidence(self):
        self.assertEqual(paragraph_around("body text", "not present here"),
                         "not present here")

    def test_empty_body(self):
        self.assertEqual(paragraph_around("", "ev"), "ev")


@override_settings(OPENAI_API_KEY="")
class ClassifierNoCallTests(SimpleTestCase):
    # OPENAI_API_KEY blanked so api_key="" can't fall back to a real env key and
    # reach the network.
    def test_no_key_returns_unknown_without_calling_api(self):
        clf = OpenAITreatmentClassifier(api_key="")
        v = clf.classify(target_name="T", target_citation="1 N.W.2d 1",
                         citing_name="C", citing_court_level=1, paragraph="overruled T")
        self.assertEqual(v, UNKNOWN_VERDICT)

    def test_empty_paragraph_returns_unknown(self):
        clf = OpenAITreatmentClassifier(api_key="sk-fake")
        v = clf.classify(target_name="T", target_citation="", citing_name="C",
                         citing_court_level=1, paragraph="   ")
        self.assertEqual(v, UNKNOWN_VERDICT)


# ---------------------------------------------------------------------------
# annotate_treatment --llm (command integration with a fake classifier)
# ---------------------------------------------------------------------------


class _FakeClassifier:
    """Returns a scripted verdict; records the calls it received."""

    def __init__(self, verdict: LLMTreatmentVerdict):
        self.verdict = verdict
        self.calls: list[dict] = []

    def classify(self, **kwargs) -> LLMTreatmentVerdict:
        self.calls.append(kwargs)
        return self.verdict


def _negative(label="abrogated", severity=5, status="negative", confidence=0.9,
              evidence="We abrogate the Target rule."):
    return LLMTreatmentVerdict(label=label, severity=severity, status=status,
                               target_is_subject=True, evidence=evidence,
                               confidence=confidence)


class AnnotateLLMTests(TestCase):
    def setUp(self):
        # Target decision (overruled), cited by the citing opinion.
        self.target_dec, self.target_op, _ = make_caselaw_case(
            cl_cluster_id=101, cl_opinion_id=1010,
            case_name="Target v. State", citations=["778 N.W.2d 33"],
            body="Target holding text.",
        )
        self.citing_dec, self.citing_op, self.citing_ver = make_caselaw_case(
            cl_cluster_id=202, cl_opinion_id=2020, court_id="iowa",
            case_name="Citing v. State",
            # Keep the stem and the cite in ONE sentence (no "v." between them,
            # which v1's sentence splitter would treat as a boundary).
            body="We overrule the rule of 778 N.W.2d 33; it no longer controls.",
        )
        # CASELAW_GRAPH edge: citing opinion version -> target opinion node, depth 4.
        CrossReference.objects.create(
            from_version=self.citing_ver, to_node=self.target_op,
            source=CrossReferenceSource.CASELAW_GRAPH, weight=4,
        )

    def _treatment(self):
        self.target_dec.refresh_from_db()
        return (self.target_dec.source_metadata or {}).get("treatment")

    def _run(self, classifier=None, **flags):
        with mock.patch.object(
            annotate_treatment.Command, "_get_classifier",
            return_value=classifier,
        ):
            call_command("annotate_treatment", stdout=StringIO(), **flags)

    def test_v1_only_flags_with_graph_phrase_source(self):
        self._run()  # no --llm
        t = self._treatment()
        self.assertIsNotNone(t)
        self.assertEqual(t["status"], "negative")
        self.assertEqual(t["label"], "overruled")
        self.assertEqual(t["source"], "graph_phrase")

    def test_llm_confident_negative_relabels_to_llm_source(self):
        fake = _FakeClassifier(_negative(label="abrogated"))
        self._run(classifier=fake, llm=True)
        t = self._treatment()
        self.assertEqual(t["source"], "llm")
        self.assertEqual(t["label"], "abrogated")
        self.assertEqual(t["status"], "negative")
        self.assertEqual(t["confidence"], 0.9)
        # The classifier actually saw this candidate.
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["target_name"], "Target v. State")

    def test_llm_downgrade_to_caution(self):
        fake = _FakeClassifier(_negative(label="limited", severity=3,
                                         status="caution", evidence="distinguished on facts"))
        self._run(classifier=fake, llm=True)
        t = self._treatment()
        self.assertEqual(t["source"], "llm")
        self.assertEqual(t["status"], "caution")
        self.assertEqual(t["severity"], 3)

    def test_llm_confident_rejection_drops_the_flag(self):
        # Model says the target is NOT the subject (the v1 stem was about another
        # case) at high confidence → drop the v1 false positive.
        reject = LLMTreatmentVerdict(label="none", severity=0, status="unknown",
                                     target_is_subject=False, evidence="",
                                     confidence=0.92)
        self._run(classifier=_FakeClassifier(reject), llm=True)
        self.assertIsNone(self._treatment())

    def test_llm_uncertain_keeps_v1_flag(self):
        # Low confidence → leave the v1 advisory flag untouched.
        unsure = LLMTreatmentVerdict(label="overruled", severity=5,
                                     status="negative", target_is_subject=True,
                                     evidence="x", confidence=0.3)
        self._run(classifier=_FakeClassifier(unsure), llm=True)
        t = self._treatment()
        self.assertIsNotNone(t)
        self.assertEqual(t["source"], "graph_phrase")  # unchanged

    def test_llm_below_min_depth_is_not_classified(self):
        fake = _FakeClassifier(_negative())
        self._run(classifier=fake, llm=True, llm_min_depth=99)  # edge depth is 4
        self.assertEqual(len(fake.calls), 0)
        # v1 flag survives untouched.
        self.assertEqual(self._treatment()["source"], "graph_phrase")

    def test_llm_no_classifier_keeps_v1(self):
        self._run(classifier=None, llm=True)
        self.assertEqual(self._treatment()["source"], "graph_phrase")
