"""The normalizer decides search quality, so it gets the most direct tests.

The rule it has to get right, and the reason it exists: a searcher types the
name they remember, and the registry stores the name as filed. Those differ in
punctuation and in entity form, and in nothing else that matters.
"""

from django.test import SimpleTestCase

from apps.resources.normalize import normalize_name


class NormalizeNameTests(SimpleTestCase):
    def test_uppercases_and_collapses_whitespace(self):
        self.assertEqual(normalize_name("  Acme   Widgets  "), "ACME WIDGETS")

    def test_strips_punctuation_and_quotes(self):
        self.assertEqual(
            normalize_name('" THE WOOD DOCTOR, L. C. "'), "THE WOOD DOCTOR"
        )

    def test_spaced_and_joined_forms_agree(self):
        # The whole point: "L. C." and "LC" and "L C" are one thing.
        for spelling in ("WOOD DOCTOR L. C.", "WOOD DOCTOR LC", "WOOD DOCTOR L C"):
            self.assertEqual(normalize_name(spelling), "WOOD DOCTOR", spelling)
        for spelling in ("ACME L.L.C.", "ACME LLC", "ACME L L C"):
            self.assertEqual(normalize_name(spelling), "ACME", spelling)

    def test_strips_repeated_suffixes(self):
        self.assertEqual(normalize_name("!MPACT LTD CO"), "MPACT")

    def test_strips_each_known_suffix(self):
        for suffix in ("INC", "Incorporated", "Corp", "Corporation", "Co",
                       "Company", "Ltd", "LLP", "LP", "PLLC", "P.C."):
            self.assertEqual(normalize_name(f"NORTHSTAR {suffix}"), "NORTHSTAR", suffix)

    def test_suffix_only_name_keeps_itself(self):
        # Stripping to "" would produce a row that matches every query and a
        # query that matches every row.
        self.assertEqual(normalize_name("LLC"), "LLC")
        self.assertEqual(normalize_name("CO INC"), "CO INC")

    def test_blank_and_junk(self):
        self.assertEqual(normalize_name(""), "")
        self.assertEqual(normalize_name("   "), "")
        self.assertEqual(normalize_name("---"), "")

    def test_digits_survive(self):
        self.assertEqual(normalize_name("1st Capital, L.C."), "1ST CAPITAL")

    def test_interior_suffix_token_is_kept(self):
        # Only *trailing* form tokens are noise; "CO" in the middle is a word.
        self.assertEqual(normalize_name("CO OP GARDENS"), "CO OP GARDENS")
