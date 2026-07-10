"""Scraper text-extraction tests — DB-free, network-free.

Covers the legacy-RTF fallback (a handful of live chapters — 141 ch. 5/6,
261 ch. 417 as of 07-2026 — are genuine RTF, not DOCX-in-.rtf-clothing) and
the two-digit-year century pivot in history brackets.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.ingestion_iowa_admin_code.scraper import (
    _to_iso,
    chapter_paragraphs,
    parse_chapter_docx,
)

# Minimal replica of the live legacy-RTF chapter shape: cp1252, raw 0x97 em
# dash in the rule head, rule head split across two styled groups.
_LEGACY_RTF = (
    b"{\\rtf1\\ansi\\ansicpg1252\\deff0\n"
    b"{\\fonttbl\\f4\\fnil\\fcharset0 Times new roman;}\n"
    b"\\pard\\qc{\\plain\\f4 CHAPTER 5}\\par\n"
    b"\\pard\\qc{\\plain\\f4 PETITIONS FOR RULE MAKING}\\par\n"
    b"\\pard\\qc{\\plain\\f4 [Prior to 3/30/94, see 210\x97Chapter 4]}\\par\n"
    b"\\pard{\\plain\\f4\\b 141\x975.1}{\\plain\\f4\\b (17A) Petition for rule making.}\\par\n"
    b"\\pard{\\plain\\f4 5.1(1) Definition. As used in this chapter.}\\par\n"
    b"\\pard{\\plain\\f4 [Filed 3/9/94, Notice 1/5/94\x97published 3/30/94, effective 5/1/94]}\\par\n"
    b"}"
)


class RtfFallbackTests(SimpleTestCase):
    def test_rtf_bytes_are_detected_and_split_into_paragraphs(self):
        paras = chapter_paragraphs(_LEGACY_RTF)
        self.assertIn("CHAPTER 5", paras)
        # The cp1252 0x97 em dash must survive extraction — the rule-head
        # regex keys on it.
        self.assertIn("141—5.1(17A) Petition for rule making.", paras)

    def test_parse_chapter_over_rtf(self):
        parsed = parse_chapter_docx("141", "5", _LEGACY_RTF, "07-08-2026")
        self.assertEqual(parsed["chapter_title"], "PETITIONS FOR RULE MAKING")
        self.assertEqual(parsed["parse_notes"], [])
        self.assertEqual(len(parsed["rules"]), 1)
        rule = parsed["rules"][0]
        self.assertEqual(rule["number"], "5.1")
        self.assertEqual(rule["heading"], "Petition for rule making")
        self.assertEqual(rule["enabling_statutes"], ["17A"])
        self.assertEqual(rule["subrules"], ["5.1(1)"])
        self.assertEqual(rule["effective_from"], "1994-05-01")

    def test_non_rtf_bytes_go_to_docx_path(self):
        with self.assertRaises(Exception):  # not a zip → DOCX path raises
            chapter_paragraphs(b"PK\x03\x04 not really a zip")


class RepeatedRuleHeadTests(SimpleTestCase):
    # Embedded forms re-cite their rule's number as a title block (live case:
    # the 21—45.28 affidavit). A repeated head must fold into the body, not
    # open a duplicate rule.
    _RTF = (
        b"{\\rtf1\\ansi\\ansicpg1252\\deff0\n"
        b"\\pard{\\plain 21\x9745.28(206) Emergency single purchase. The department shall issue.}\\par\n"
        b"\\pard{\\plain 21\x9745.28(206) EMERGENCY SALE OF A RESTRICTED USE}\\par\n"
        b"\\pard{\\plain PESTICIDE BY A PRIVATE APPLICATOR}\\par\n"
        b"}"
    )

    def test_repeated_head_is_body_not_new_rule(self):
        parsed = parse_chapter_docx("21", "45", self._RTF, "07-08-2026")
        self.assertEqual(len(parsed["rules"]), 1)
        rule = parsed["rules"][0]
        self.assertEqual(rule["number"], "45.28")
        self.assertEqual(rule["heading"], "Emergency single purchase")
        self.assertIn("EMERGENCY SALE OF A RESTRICTED USE", rule["body_text"])
        self.assertEqual(
            parsed["parse_notes"],
            ["repeated head for rule 45.28 kept as body text"],
        )


class ToIsoTests(SimpleTestCase):
    def test_two_digit_years_pivot_at_1950(self):
        self.assertEqual(_to_iso("5", "1", "94"), "1994-05-01")
        self.assertEqual(_to_iso("4", "3", "24"), "2024-04-03")
        self.assertEqual(_to_iso("1", "10", "50"), "1950-01-10")

    def test_four_digit_years_pass_through(self):
        self.assertEqual(_to_iso("12", "31", "1998"), "1998-12-31")

    def test_invalid_date_returns_none(self):
        self.assertIsNone(_to_iso("2", "30", "2024"))
