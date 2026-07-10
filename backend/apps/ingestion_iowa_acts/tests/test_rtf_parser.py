"""Tokenizer + enrolled-bill parser tests (Phase 0).

The strike/ul semantics and the section grammar are pinned against a real
enrolled bill (HF 2485, GA 90 — committed as a 39 KB fixture) plus synthetic
RTF snippets for the tokenizer edge cases. The 1.38 MB omnibus performance
bar (SF 2385 < 10 s; measured ~1 s) is asserted loosely so CI variance can't
flake it, and only when the local cache has the file.
"""

from __future__ import annotations

import time
from pathlib import Path

from django.test import SimpleTestCase

from apps.ingestion_iowa_acts.parser import parse_enrolled_rtf
from apps.ingestion_iowa_acts.rtf import (
    full_text_with_markers,
    resulting_text,
    tokenize,
)

FIXTURES = Path(__file__).parent / "fixtures"
CACHE = Path(__file__).resolve().parents[3] / "data" / "raw" / "acts_cache"


def rtf(body: str) -> bytes:
    return ("{\\rtf1 \\ansi " + body + "}").encode("latin-1")


class TokenizerTests(SimpleTestCase):
    def test_strike_runs_excluded_from_resulting_text(self):
        runs = tokenize(rtf(r"appointed {\strike from a list }and shall serve"))
        self.assertEqual(resulting_text(runs), "appointed and shall serve")
        self.assertEqual(
            full_text_with_markers(runs), "appointed ⟪from a list ⟫and shall serve"
        )

    def test_ul_runs_kept_and_marked_as_insertions(self):
        runs = tokenize(rtf(r"the {\ul department} decides"))
        self.assertEqual(resulting_text(runs), "the department decides")
        self.assertIn("⟦department⟧", full_text_with_markers(runs))

    def test_group_scoping_restores_state(self):
        # strike inside a group must not leak past the closing brace
        runs = tokenize(rtf(r"a{\strike b}c"))
        self.assertEqual(resulting_text(runs), "ac")
        self.assertEqual([r.text for r in runs if r.strike], ["b"])

    def test_escapes_nbsp_and_unicode(self):
        runs = tokenize(rtf("caf\\'e9 \\u8212? em"))
        self.assertEqual(resulting_text(runs), "café — em")

    def test_par_and_tab(self):
        runs = tokenize(rtf(r"one\par two\tab three"))
        self.assertEqual(resulting_text(runs), "one\ntwo\tthree")

    def test_skippable_destinations_and_star_groups(self):
        runs = tokenize(
            rtf(
                r"{\*\userprops {\propname v}{\staticval junk}}"
                r"{\fonttbl{\f1 arial;}}visible"
            )
        )
        self.assertEqual(resulting_text(runs), "visible")


class EnrolledBillParseTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.act = parse_enrolled_rtf((FIXTURES / "HF2485.rtf").read_bytes())

    def test_bill_and_title(self):
        self.assertEqual(self.act.bill, "HF2485")
        self.assertIn("REGULATION OF WATERCRAFT", self.act.title)

    def test_section_split_and_kinds(self):
        self.assertEqual(len(self.act.sections), 3)
        self.assertEqual(
            [s.kind for s in self.act.sections],
            ["new_section", "new_section", "boilerplate:EFFECTIVE DATE"],
        )
        self.assertEqual([s.number for s in self.act.sections], [1, 2, 3])

    def test_new_section_edges_and_headings(self):
        s1, s2, _ = self.act.sections
        self.assertEqual([e.code_ref for e in s1.edges], ["462A.17A"])
        self.assertEqual([e.code_ref for e in s2.edges], ["462A.17B"])
        self.assertIn("Common interest communities", s1.heading)

    def test_signature_trailer_stripped(self):
        self.assertNotIn("Speaker of the House", self.act.sections[-1].body_text)


class LeadInGrammarTests(SimpleTestCase):
    """Each lead-in form the plan grammar names, via tiny synthetic bills."""

    def parse_one(self, lead_in: str):
        body = rf"BE IT ENACTED BY THE GENERAL ASSEMBLY OF THE STATE OF IOWA:\par Section 1.  {lead_in}"
        act = parse_enrolled_rtf(rtf(body))
        self.assertEqual(len(act.sections), 1)
        return act.sections[0]

    def test_amend_singular(self):
        s = self.parse_one(
            "Section 161A.4, subsection 2, Code 2024, is amended to read as follows:"
        )
        self.assertEqual(s.kind, "amend")
        self.assertEqual(s.edges[0].code_ref, "161A.4")
        self.assertEqual(s.edges[0].code_year, "2024")

    def test_amend_plural_subsections(self):
        s = self.parse_one(
            "Section 161A.4, subsections 1, 6, and 7, Code 2024, are amended to read as follows:"
        )
        self.assertEqual(s.kind, "amend")

    def test_amend_by_adding(self):
        s = self.parse_one(
            "Section 455B.171, Code 2024, is amended by adding the following new subsection:"
        )
        self.assertEqual(s.kind, "amend_add")

    def test_amend_by_striking(self):
        s = self.parse_one(
            "Section 8.6, subsection 5, Code 2024, is amended by striking the subsection."
        )
        self.assertEqual(s.kind, "amend_strike")

    def test_repeal_with_caps_label(self):
        s = self.parse_one("REPEAL.  Sections 2.69 and 3.20, Code 2024, are repealed.")
        self.assertEqual(s.kind, "repeal")
        self.assertEqual([e.code_ref for e in s.edges], ["2.69", "3.20"])

    def test_chapter_repeal(self):
        s = self.parse_one("REPEAL.  Chapters 28B and 473A, Code 2024, are repealed.")
        self.assertEqual(s.kind, "repeal_chapter")
        self.assertEqual([e.code_ref for e in s.edges], ["28B", "473A"])

    def test_boilerplate_effective_date(self):
        s = self.parse_one(
            "EFFECTIVE DATE.  This Act, being deemed of immediate importance, takes effect upon enactment."
        )
        self.assertEqual(s.kind, "boilerplate:EFFECTIVE DATE")

    def test_study_directive_is_other(self):
        s = self.parse_one(
            "LICENSURE FEE STUDY.  The department shall conduct a study."
        )
        self.assertEqual(s.kind, "other")
        self.assertEqual(s.edges, [])


class OmnibusPerformanceTests(SimpleTestCase):
    def test_sf2385_parses_fast_when_cached(self):
        path = CACHE / "SF2385.rtf"
        if not path.exists():
            self.skipTest("SF2385.rtf not in local cache")
        t0 = time.time()
        act = parse_enrolled_rtf(path.read_bytes())
        self.assertLess(time.time() - t0, 10.0)
        self.assertGreater(len(act.sections), 500)
        edges = [e for s in act.sections for e in s.edges]
        self.assertGreater(len(edges), 550)
