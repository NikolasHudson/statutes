"""Citation parser tests — DB-free.

Table-driven so it doubles as documentation of what we accept.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.citations.parser import (
    Citation,
    CitationParseError,
    parse,
)


class ParseTableTests(SimpleTestCase):
    def _check(self, text: str, expected: Citation):
        got = parse(text)
        self.assertEqual(got.chapter, expected.chapter, text)
        self.assertEqual(got.section, expected.section, text)
        self.assertEqual(got.subdivisions, expected.subdivisions, text)

    def test_iowa_code_long_form(self):
        self._check(
            "Iowa Code § 714.16",
            Citation(chapter="714", section="714.16"),
        )

    def test_iowa_code_with_section_word(self):
        self._check(
            "Iowa Code section 714.16(2)(a)",
            Citation(
                chapter="714", section="714.16", subdivisions=("2", "a")
            ),
        )

    def test_ic_short_form(self):
        self._check("I.C. § 714.16", Citation(chapter="714", section="714.16"))

    def test_ic_chapter_only(self):
        self._check("I.C. 714", Citation(chapter="714", section=None))

    def test_section_word_only(self):
        self._check("section 1.4", Citation(chapter="1", section="1.4"))

    def test_section_sigil_with_subdivisions(self):
        self._check(
            "§ 714.16(2)(a)(1)",
            Citation(
                chapter="714",
                section="714.16",
                subdivisions=("2", "a", "1"),
            ),
        )

    def test_bare_path_with_dot_is_section(self):
        self._check("714.16", Citation(chapter="714", section="714.16"))

    def test_bare_chapter_number(self):
        # A bare chapter number is treated as chapter-only.
        self._check("714", Citation(chapter="714", section=None))

    def test_chapter_word(self):
        self._check("Chapter 232", Citation(chapter="232", section=None))

    def test_alphanumeric_chapter(self):
        self._check("12C.3", Citation(chapter="12C", section="12C.3"))

    def test_case_insensitive(self):
        self._check("iowa code § 714.16", Citation(chapter="714", section="714.16"))

    # --- Iowa rule reporter forms (court rules cited by reporter, not § ) ---

    def test_iowa_rules_civ_p(self):
        self._check(
            "Iowa R. Civ. P. 1.303", Citation(chapter="1", section="1.303")
        )

    def test_iowa_rules_civ_p_with_subdivision(self):
        self._check(
            "Iowa R. Civ. P. 1.421(4)",
            Citation(chapter="1", section="1.421", subdivisions=("4",)),
        )

    def test_iowa_rules_crim_p(self):
        self._check(
            "Iowa R. Crim. P. 2.11", Citation(chapter="2", section="2.11")
        )

    def test_iowa_rules_evid(self):
        self._check(
            "Iowa R. Evid. 5.401", Citation(chapter="5", section="5.401")
        )

    def test_rendered_court_rule_round_trips(self):
        # _render_citation emits "Iowa Ct. R. 1.303"; the model echoes that
        # back into lookup_citation, so the parser must accept it.
        self._check(
            "Iowa Ct. R. 1.303", Citation(chapter="1", section="1.303")
        )

    def test_bare_rule_word(self):
        self._check("rule 1.303", Citation(chapter="1", section="1.303"))

    def test_bare_r_abbrev(self):
        self._check("R. 1.421", Citation(chapter="1", section="1.421"))

    def test_rules_of_civil_procedure_long_form(self):
        self._check(
            "Iowa Rules of Civil Procedure 1.303",
            Citation(chapter="1", section="1.303"),
        )

    # --- Colon-form (Rules of Professional Conduct: chapter 32) ---

    def test_colon_form_professional_conduct(self):
        # Node.path stores the colon verbatim ("32:1.7") — the parsed
        # section must keep it, not normalize to "32.1.7".
        self._check(
            "Iowa Ct. R. 32:1.7", Citation(chapter="32", section="32:1.7")
        )

    def test_colon_form_with_subdivision(self):
        self._check(
            "32:1.10(a)(2)",
            Citation(chapter="32", section="32:1.10", subdivisions=("a", "2")),
        )

    def test_colon_form_bare(self):
        self._check("32:1.9", Citation(chapter="32", section="32:1.9"))

    def test_dot_form_still_normalizes_with_dot(self):
        # Regression: the separator change must not turn Iowa Code "714.16"
        # into anything else.
        self._check("Iowa Code § 714.16", Citation(chapter="714", section="714.16"))


class ParseErrorTests(SimpleTestCase):
    def test_empty(self):
        with self.assertRaises(CitationParseError):
            parse("")

    def test_whitespace_only(self):
        with self.assertRaises(CitationParseError):
            parse("   ")

    def test_no_digits(self):
        with self.assertRaises(CitationParseError):
            parse("Iowa Code §")


class RenderTests(SimpleTestCase):
    def test_long_form_section(self):
        c = Citation(chapter="714", section="714.16", subdivisions=("2", "a"))
        self.assertEqual(c.render("long"), "Iowa Code § 714.16(2)(a)")

    def test_short_form_section(self):
        c = Citation(chapter="714", section="714.16")
        self.assertEqual(c.render("short"), "I.C. § 714.16")

    def test_long_form_chapter(self):
        c = Citation(chapter="232", section=None)
        self.assertEqual(c.render("long"), "Iowa Code ch. 232")
