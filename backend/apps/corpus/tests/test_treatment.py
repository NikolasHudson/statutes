"""Deterministic v1 treatment classifier (apps.corpus.services.treatment).

Pure-function tests pinning the precision guards that the live calibration
surfaced — the difference between "[target] was overruled" (negative treatment)
and the dominant false positives: "overruled the objection", "overruled by
[target]" (target is the OVERRULER), "[target] (overruling X)", "decline to
overrule", "on other grounds", "supersedeas". A false *negative*-treatment flag
tells a lawyer a good case is dead, so these guards are load-bearing.
"""

from __future__ import annotations

import re

from django.test import SimpleTestCase

from apps.corpus.services.treatment import (
    PREFILTER_SQL_REGEX,
    _cite_anchors,
    classify_citing_text,
    classify_target,
)

A = ["778 N.W.2d"]


def sev(text, anchors=A):
    r = classify_citing_text(text, anchors)
    return r[0] if r else None


class CiteAnchorTests(SimpleTestCase):
    def test_extracts_volume_reporter_prefix(self):
        self.assertEqual(
            _cite_anchors(["778 N.W.2d 33", "641 N.W.2d 532"]),
            ["778 N.W.2d", "641 N.W.2d"],
        )

    def test_skips_vendor_cites(self):
        self.assertEqual(
            _cite_anchors(["2004 Iowa Sup. LEXIS 193", "2004 WL 1344973"]), []
        )

    def test_empty(self):
        self.assertEqual(_cite_anchors([]), [])


class TreatmentGuardTests(SimpleTestCase):
    # --- genuine negative treatment (target is the patient) ----------------
    def test_clean_overrule(self):
        self.assertEqual(sev("We overrule 778 N.W.2d 33 today."), 5)

    def test_overruling_target_gerund_before_cite(self):
        self.assertEqual(sev("expressly overruling 778 N.W.2d 33."), 5)

    def test_target_overruled_by_other(self):
        self.assertEqual(sev("778 N.W.2d 33, overruled by Smith, 9 N.W.3d 1."), 5)

    def test_abrogated(self):
        self.assertEqual(sev("We abrogate the rule of 778 N.W.2d 33."), 5)

    def test_disapproved_is_caution(self):
        self.assertEqual(sev("We disapprove of 778 N.W.2d 33 to that extent."), 4)

    # --- the dominant false positives, all must NOT flag -------------------
    def test_overruled_the_objection(self):
        self.assertIsNone(sev("The court overruled the objection. See 778 N.W.2d 33."))

    def test_overruling_objection_same_sentence(self):
        self.assertIsNone(sev("the court overruling objection in 778 N.W.2d 33, where"))

    def test_overruled_his_motion(self):
        self.assertIsNone(sev("improperly overruled his motion based on 778 N.W.2d 33"))

    def test_overruled_our_objection_possessive_determiners(self):
        # "our/your/my/counsel's" are common; the ruling-noun guard must catch them.
        self.assertIsNone(sev("We overruled our objection to discovery. 778 N.W.2d 33."))
        self.assertIsNone(sev("The court overruled counsel's objection, 778 N.W.2d 33."))

    def test_overruled_by_target_is_the_overruler(self):
        # "overruled by [target]" → the TARGET did the overruling, not vice versa.
        self.assertIsNone(sev("Smith, 1 N.W.2d 2 (1982), overruled by 778 N.W.2d 33."))

    def test_overruled_on_other_grounds_by_target(self):
        self.assertIsNone(
            sev("Lyman, overruled on the other grounds by 778 N.W.2d 33.")
        )

    def test_target_overruling_other_gerund_after_cite(self):
        # "[target] (overruling X)" → target is the agent.
        self.assertIsNone(sev("See 778 N.W.2d 33, 813 (overruling State v. Smith)."))

    def test_decline_to_overrule(self):
        self.assertIsNone(sev("We decline to overrule 778 N.W.2d 33."))

    def test_did_not_purport_to_overrule(self):
        self.assertIsNone(sev("Lelm did not purport to overrule 778 N.W.2d 33."))

    def test_not_at_liberty_to_overrule(self):
        self.assertIsNone(sev("We are not at liberty to overrule 778 N.W.2d 33."))

    def test_party_request_to_overrule(self):
        self.assertIsNone(sev("Appellant asked the court to overrule 778 N.W.2d 33."))

    def test_supersedeas_is_not_superseded(self):
        self.assertIsNone(sev("The court set a supersedeas bond. See 778 N.W.2d 33."))

    def test_distinguish_is_dropped_in_v1(self):
        self.assertIsNone(sev("We distinguish 778 N.W.2d 33 on its facts."))

    # --- qualified treatment downgraded, not dropped ----------------------
    def test_overruled_on_other_grounds_downgrades_to_caution(self):
        r = classify_citing_text("778 N.W.2d 33, overruled on other grounds, remains good.", A)
        self.assertEqual(r[0], 3)
        self.assertIn("other-grounds", r[1])

    def test_superseded_by_statute_label(self):
        r = classify_citing_text("778 N.W.2d 33 was superseded by statute in 2015.", A)
        self.assertEqual(r[0], 5)
        self.assertEqual(r[1], "superseded-by-statute")

    # --- proximity / attribution ------------------------------------------
    def test_overrule_in_separate_sentence_not_attributed(self):
        self.assertIsNone(sev("We overrule Smith. See also 778 N.W.2d 33 for background."))

    def test_far_clause_overrule_not_attributed(self):
        # The overrule is about Smith; the target cite is a distant clause.
        self.assertIsNone(sev(
            "We overrule Smith, 1 N.W.2d 2, which had relied on entirely separate "
            "reasoning unrelated to the standing question addressed in 778 N.W.2d 33."
        ))

    # --- PDF line-wrap normalization (the Bankers Trust → Madden recall bug) --
    def test_pdf_linewrap_does_not_sever_stem_from_cite(self):
        # body_text from PDF extraction injects \n\n MID-sentence between the
        # overrule stem and the reporter cite (and a hyphen line-wrap), which the
        # old newline-naive splitter tore apart → the overruling was SILENTLY
        # missed. Normalization must reunite them into one scannable sentence.
        body = (
            "The majority gives only passing lip service to stare decisis in "
            "overruling\n\nSmith v. City of Iowa City, 778 N.W.2d 33 (Iowa 2014), "
            "basing its deci-\n\nsion solely on the dissent's reasoning."
        )
        r = classify_citing_text(body, A)
        self.assertIsNotNone(r)
        self.assertEqual(r[0], 5)
        self.assertEqual(r[1], "overruled")

    def test_abbreviation_period_does_not_split_caption(self):
        # "v." between the stem and the cite must not be a sentence boundary.
        r = classify_citing_text("in overruling Smith v. Jones, 778 N.W.2d 33.", A)
        self.assertIsNotNone(r)
        self.assertEqual(r[0], 5)

    # --- normalization must NOT manufacture false positives (precision) -------
    def test_entity_suffix_period_before_capital_is_a_boundary(self):
        # Sentence 1 overrules a DIFFERENT case and ends in "Co."/"Inc."/"Bros.";
        # it must NOT merge with the next sentence that cites the target favorably,
        # else the overrule mis-attributes to the target (false "dead case" flag).
        for s in (
            "We overrule the rule of Jones Bros. We then apply 778 N.W.2d 33 with approval.",
            "We overruled Smith v. Acme, Inc. The plaintiff here relies on 778 N.W.2d 33.",
            "We overrule old Acme Co. Today we reaffirm 778 N.W.2d 33 fully.",
        ):
            self.assertIsNone(sev(s), s)

    def test_sentence_final_iowa_is_a_boundary(self):
        # "...Supreme Court of Iowa." / "...in Iowa." is a real sentence end; it
        # must not merge with the next sentence (the highest-frequency Iowa trap).
        self.assertIsNone(sev(
            "The court overruled Smith, a decision of the Supreme Court of Iowa. "
            "We reaffirm 778 N.W.2d 33 today."
        ))
        self.assertIsNone(sev(
            "The objection was overruled in Iowa. Later, 778 N.W.2d 33 was followed here."
        ))

    def test_intervening_cite_blocks_attribution(self):
        # Another reporter cite between the stem and the target → the stem belongs
        # to that other case (or this is a collapsed newline cite-stack). Not the
        # target's treatment.
        self.assertIsNone(sev(
            "cases overruling prior law include\nSmith\n9 N.W.3d 1\n\n778 N.W.2d 33\nJones\n5 N.W.2d 9"
        ))

    def test_soft_hyphen_join_does_not_corrupt_numeric_spans(self):
        # _WRAP_HYPHEN must only join lowercase soft-wraps; page ranges / date
        # spans survive (the verbatim excerpt is a precision-critical surface).
        from apps.corpus.services.treatment import _normalize_body
        # Numeric spans are NOT glued into one number (the corruption being fixed);
        # the hyphen survives and only the newline collapses to a space.
        self.assertEqual(_normalize_body("778 N.W.2d 33-\n34"), "778 N.W.2d 33- 34")
        self.assertEqual(_normalize_body("the 2014-\n2016 term"), "the 2014- 2016 term")
        # but a genuine lowercase soft-wrap IS rejoined.
        self.assertEqual(_normalize_body("the deci-\n\nsion stated"), "the decision stated")


class PrefilterSupersetTests(SimpleTestCase):
    """The annotate_treatment prefilter MUST match everything the classifier can
    flag — otherwise a re-run drops a real flag during the clear-stale phase."""

    def setUp(self):
        # Postgres \y word boundary == Python \b.
        self.prefilter = re.compile(PREFILTER_SQL_REGEX.replace(r"\y", r"\b"), re.I)

    def test_matches_every_stem_word(self):
        for w in [
            "overruled", "overruling", "overrule", "abrogated", "abrogation",
            "superseded", "superseding", "repudiated", "disapproved", "disapproval",
            "no longer good law", "declined to follow", "decline to extend",
        ]:
            self.assertRegex(w, self.prefilter, f"prefilter misses {w!r}")

    def test_prefilter_catches_every_sentence_the_classifier_flags(self):
        flagged = [
            "We overrule 778 N.W.2d 33.",
            "expressly overruling 778 N.W.2d 33.",
            "We abrogate the rule of 778 N.W.2d 33.",
            "778 N.W.2d 33 was superseded by statute in 2015.",
            "We disapprove of 778 N.W.2d 33 to that extent.",
        ]
        for s in flagged:
            self.assertIsNotNone(classify_citing_text(s, A), f"classifier should flag {s!r}")
            self.assertRegex(s, self.prefilter, f"prefilter must also catch {s!r}")


class ClassifyTargetTests(SimpleTestCase):
    def _op(self, body, level=1, name="Citing Case"):
        return {"body": body, "court_level": level, "name": name, "depth": 1}

    def test_no_citations_is_unknown(self):
        r = classify_target([], [self._op("We overrule 778 N.W.2d 33.")])
        self.assertEqual(r.status, "unknown")

    def test_most_severe_citing_opinion_wins(self):
        r = classify_target(
            ["778 N.W.2d 33"],
            [
                self._op("We discuss 778 N.W.2d 33 favorably."),
                self._op("We overrule 778 N.W.2d 33.", name="Killer"),
            ],
        )
        self.assertEqual(r.severity, 5)
        self.assertEqual(r.status, "negative")
        self.assertEqual(r.by_citation, "Killer")
        self.assertIn("overrule", r.excerpt.lower())
        self.assertEqual(r.source, "graph_phrase")

    def test_clean_cites_yield_good(self):
        r = classify_target(
            ["778 N.W.2d 33"], [self._op("We follow 778 N.W.2d 33 and apply it.")]
        )
        self.assertEqual(r.status, "good")
        self.assertEqual(r.severity, 0)

    def test_as_metadata_roundtrips_fields(self):
        r = classify_target(["778 N.W.2d 33"], [self._op("We overrule 778 N.W.2d 33.")])
        md = r.as_metadata()
        self.assertEqual(
            set(md),
            {"status", "severity", "label", "by_citation", "excerpt", "source", "confidence"},
        )
        self.assertEqual(md["severity"], 5)
