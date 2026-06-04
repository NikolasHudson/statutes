"""Tests for subsection-level grounding (``provision_slice``).

Bodies mirror the corpus's real outline format: markers are line-anchored,
indented with non-breaking spaces, with "1."/"a." dotted at the top two levels
and "(1)"/"(a)" parenthesized below. The key correctness property is that a
``(2)`` *subparagraph* nested inside subsection 1 is never mistaken for
subsection ``2.`` — slicing is keyed to depth, not to "first marker that
matches".
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.corpus.services.provision_slice import slice_provision

NB = "\xa0\xa0"  # the corpus indents and separates markers with nbsp pairs

# Subsection 1 contains a "(2)" subparagraph; there is also a real subsection 2.
TRAP_BODY = (
    f"1.{NB}Definitions:\n"
    f"{NB}a.{NB}First paragraph mentioning item one.\n"
    f"{NB}b.{NB}Second paragraph with a list:\n"
    f"{NB}(1){NB}inner subparagraph one.\n"
    f"{NB}(2){NB}inner subparagraph two.\n"
    f"2.{NB}The second subsection proper.\n"
    f"3.{NB}The third subsection.\n"
)

# Two-level body with a trailing paragraph after the cited one.
WARRANTY_BODY = (
    f"1.{NB}Express warranties are created as follows:\n"
    f"{NB}a.{NB}Any affirmation of fact creates an express warranty.\n"
    f"{NB}b.{NB}Any description of the goods creates an express warranty.\n"
    f"2.{NB}Formal words are not necessary.\n"
)


class SliceProvisionTests(SimpleTestCase):
    def test_subsection_slice(self):
        out = slice_provision(TRAP_BODY, ("2",))
        self.assertIsNotNone(out)
        self.assertTrue(out.startswith("2."))
        self.assertIn("second subsection proper", out)
        self.assertNotIn("third subsection", out)

    def test_subsection_does_not_match_inner_subparagraph(self):
        # The "(2)" inside subsection 1 must not shadow subsection "2.".
        out = slice_provision(TRAP_BODY, ("2",))
        self.assertIn("second subsection proper", out)
        self.assertNotIn("inner subparagraph two", out)

    def test_first_subsection_bounded_by_next_sibling(self):
        out = slice_provision(TRAP_BODY, ("1",))
        self.assertIn("Definitions", out)
        self.assertIn("inner subparagraph two", out)  # children stay in the block
        self.assertNotIn("second subsection proper", out)  # sibling ends it

    def test_paragraph_slice(self):
        out = slice_provision(WARRANTY_BODY, ("1", "a"))
        self.assertTrue(out.startswith("a."))
        self.assertIn("affirmation of fact", out)
        self.assertNotIn("description of the goods", out)  # next paragraph excluded

    def test_paragraph_slice_second(self):
        out = slice_provision(WARRANTY_BODY, ("1", "b"))
        self.assertIn("description of the goods", out)
        self.assertNotIn("affirmation of fact", out)
        self.assertNotIn("Formal words", out)  # doesn't bleed into subsection 2

    def test_subparagraph_slice_line_anchored(self):
        out = slice_provision(TRAP_BODY, ("1", "b", "1"))
        self.assertTrue(out.startswith("(1)"))
        self.assertIn("inner subparagraph one", out)
        self.assertNotIn("inner subparagraph two", out)

    def test_missing_token_returns_none(self):
        self.assertIsNone(slice_provision(WARRANTY_BODY, ("9",)))
        self.assertIsNone(slice_provision(WARRANTY_BODY, ("1", "z")))

    def test_token_type_mismatch_returns_none(self):
        # Alpha where a number is expected (depth 1) → convention doesn't hold.
        self.assertIsNone(slice_provision(WARRANTY_BODY, ("a",)))

    def test_depth_beyond_outline_returns_none(self):
        self.assertIsNone(slice_provision(TRAP_BODY, ("1", "b", "1", "a", "i")))

    def test_empty_inputs_return_none(self):
        self.assertIsNone(slice_provision("", ("1",)))
        self.assertIsNone(slice_provision(WARRANTY_BODY, ()))

    def test_decimal_at_line_start_not_mistaken_for_marker(self):
        body = f"1.{NB}See section 554.2202 for details.\n2.{NB}Next.\n"
        # Citation (2) must land on subsection "2.", not the "2202" decimal.
        out = slice_provision(body, ("2",))
        self.assertIn("Next.", out)
        self.assertNotIn("554.2202", out)
