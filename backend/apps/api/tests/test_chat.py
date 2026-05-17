"""Regression tests for the chat grounding behaviour.

These guard the specific failure mode found in the Smith/Sarah conflicts
scenario: the chat told an attorney a screening cure was available when
Iowa Ct. R. 32:1.10(a)(2) scopes it to lateral-hire ("prior firm")
conflicts only. Root causes on our end were (a) every search hit truncated
at 2000 chars, cutting off the official Comments that bound the exception,
and (b) system-prompt guidance that mis-resolved Court Rule citations.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.api.chat import (
    SEARCH_BODY_MAX_CHARS,
    SEARCH_BODY_MAX_CHARS_TOP,
    SYSTEM_PROMPT,
    _excerpt,
)

# A faithful slice of Iowa Ct. R. 32:1.10 (node 31327): the black-letter
# (a)(2) screening exception with its dispositive "prior firm" condition,
# padded to the real structure so "Comment" lands past the old 2000-char
# cap (in the live corpus it starts ~char 2272), then Comment [7] which is
# what actually scopes the screening cure.
RULE_32_1_10 = (
    "(a) While lawyers are associated in a firm, none of them shall "
    "knowingly represent a client when any one of them practicing alone "
    "would be prohibited from doing so by rule 32:1.7 or 32:1.9, unless "
    "(1) the prohibition is based on a personal interest of the "
    "disqualified lawyer and does not present a significant risk of "
    "materially limiting the representation of the client by the "
    "remaining lawyers in the firm; or (2) the prohibition is based upon "
    "rule 32:1.9(a) or (b) and arises out of the disqualified lawyer's "
    "association with a prior firm, and (i) the disqualified lawyer is "
    "timely screened from any participation in the matter and is "
    "apportioned no part of the fee therefrom; "
    + ("(filler to mirror the real (a)(2)(ii)-(iii), (b)-(d) length) " * 22)
    + "Comment "
    "[7] Rule 32:1.10(a)(2) similarly removes the imputation otherwise "
    "required by rule 32:1.10(a), but unlike section (c), it does so "
    "without requiring that there be informed consent by the former "
    "client. Instead, it requires that the procedures laid out in "
    "sections (a)(2)(i)-(iii) be followed."
)


class ExcerptBudgetTests(SimpleTestCase):
    """The fix: the top reranked hit must keep enough text to reach the
    Comments that scope an exception, while non-top hits stay compact."""

    def setUp(self):
        # Guard the premise of the regression: the Comment block really is
        # beyond the old per-hit cap, so the old behaviour did lose it.
        self.comment_at = RULE_32_1_10.index("Comment ")
        self.assertGreater(self.comment_at, SEARCH_BODY_MAX_CHARS)
        self.assertLess(len(RULE_32_1_10), SEARCH_BODY_MAX_CHARS_TOP)

    def test_old_cap_would_drop_the_disambiguating_comment(self):
        # Documents the bug: at the non-top budget the model never sees the
        # Comment that limits screening to "prior firm" conflicts.
        clipped = _excerpt(RULE_32_1_10, SEARCH_BODY_MAX_CHARS)
        self.assertTrue(clipped.endswith("…"))
        self.assertNotIn("Comment", clipped)

    def test_top_hit_retains_prior_firm_clause_and_comment(self):
        excerpt = _excerpt(RULE_32_1_10, SEARCH_BODY_MAX_CHARS_TOP)
        # The black-letter condition that the screening cure is limited to
        # lateral-hire conflicts...
        self.assertIn("arises out of the disqualified lawyer's "
                       "association with a prior firm", excerpt)
        # ...and the official Comment that nails it down both survive.
        self.assertIn("Comment", excerpt)
        self.assertIn("without requiring that there be informed consent",
                      excerpt)
        # Whole thing fits the top budget, so no ellipsis.
        self.assertFalse(excerpt.endswith("…"))

    def test_excerpt_breaks_on_word_boundary_and_flags_cut(self):
        out = _excerpt("alpha beta gamma delta", 12)
        self.assertTrue(out.endswith("…"))
        self.assertNotIn("gamm…", out)  # no mid-word slice

    def test_short_text_returned_verbatim(self):
        self.assertEqual(_excerpt("short rule.", 2000), "short rule.")


class SystemPromptGuidanceTests(SimpleTestCase):
    """The prompt-side fixes that make the full-text recovery path work and
    stop the over-generalization of exceptions."""

    def test_court_rule_citation_keeps_chapter_prefix(self):
        # Stripping '32:1.10' to '1.10' mis-resolves to the Iowa Code.
        self.assertIn("32:1.10", SYSTEM_PROMPT)
        self.assertIn("INCLUDING any chapter prefix", SYSTEM_PROMPT)

    def test_prompt_warns_dispositive_limits_live_in_comments(self):
        self.assertIn("Comments", SYSTEM_PROMPT)

    def test_prompt_requires_checking_exception_conditions(self):
        self.assertIn("Recognizing that an exception exists is not", SYSTEM_PROMPT)
        self.assertIn("prior firm", SYSTEM_PROMPT)
