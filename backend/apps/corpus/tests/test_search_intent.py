"""Table-driven tests for the search-box intent classifier.

The fixture table lives in ``apps/corpus/data/search_intent_queries.json`` so
the same rows double as the connector regression set — extend the JSON, not
this file, when SearchLog surfaces new attorney query patterns."""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.corpus.services.search_intent import (
    FUNC_TSQUERY,
    FUNC_WEBSEARCH,
    MODE_BOOLEAN,
    MODE_CITATION,
    MODE_NATURAL,
    classify_query,
    compile_boolean_tsquery,
    looks_like_citation,
)

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "data" / "search_intent_queries.json"
)


class IntentTableTests(SimpleTestCase):
    """Every row in the JSON fixture must classify (and compile) as stated."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = json.loads(_FIXTURE.read_text())["queries"]

    def test_fixture_rows(self):
        for row in self.rows:
            with self.subTest(q=row["q"]):
                intent = classify_query(row["q"])
                self.assertEqual(intent.mode, row["mode"])
                self.assertEqual(intent.mode_source, "auto")
                if "operators" in row:
                    self.assertEqual(intent.operators, row["operators"])
                if "phrases" in row:
                    self.assertEqual(intent.phrases, row["phrases"])
                if "unsupported" in row:
                    self.assertEqual(
                        [u["token"] for u in intent.unsupported],
                        row["unsupported"],
                    )
                    for u in intent.unsupported:
                        self.assertEqual(u["treated_as"], "AND")
                        self.assertIn("isn't supported yet", u["message"])
                if "tsquery" in row:
                    self.assertEqual(intent.tsquery, row["tsquery"])
                    self.assertEqual(intent.tsquery_func, row["tsquery_func"])


class ClassifierEdgeTests(SimpleTestCase):
    def test_mode_override_forces_boolean(self):
        intent = classify_query("ordinary prose query", mode_override="boolean")
        self.assertEqual(intent.mode, MODE_BOOLEAN)
        self.assertEqual(intent.mode_source, "user")
        self.assertEqual(intent.tsquery_func, FUNC_WEBSEARCH)

    def test_mode_override_forces_natural(self):
        intent = classify_query("landlord AND deposit", mode_override="natural")
        self.assertEqual(intent.mode, MODE_NATURAL)
        self.assertEqual(intent.mode_source, "user")
        # Detection is still reported so the UI can offer the switch back.
        self.assertEqual(intent.operators, ["AND"])

    def test_citation_ok_false_reclassifies(self):
        self.assertEqual(classify_query("714.16").mode, MODE_CITATION)
        self.assertEqual(
            classify_query("714.16", citation_ok=False).mode, MODE_NATURAL
        )

    def test_whitespace_is_collapsed(self):
        intent = classify_query("  landlord    AND\tdeposit ")
        self.assertEqual(intent.raw, "landlord AND deposit")
        self.assertEqual(intent.mode, MODE_BOOLEAN)

    def test_empty_query_is_natural(self):
        self.assertEqual(classify_query("").mode, MODE_NATURAL)

    def test_looks_like_citation_rejects_prose(self):
        for q in ("negligence", "dog bite damages", "State v. Williams"):
            self.assertFalse(looks_like_citation(q), q)

    def test_detection_payload_shape(self):
        payload = classify_query("dog w/5 bite").detection_payload()
        self.assertEqual(
            set(payload), {"operators", "phrases", "unsupported"}
        )


class CompilerSafetyTests(SimpleTestCase):
    """The to_tsquery output must never be structurally invalid — trailing
    operators, unbalanced parens and empty groups are repaired or dropped."""

    def test_dangling_operator_trimmed(self):
        text, func, _ = compile_boolean_tsquery("waiver AND (estoppel OR)")
        self.assertEqual(func, FUNC_TSQUERY)
        self.assertEqual(text, "waiver & ( estoppel )")

    def test_unclosed_paren_balanced(self):
        text, _, _ = compile_boolean_tsquery("(waiver OR estoppel")
        self.assertEqual(text.count("("), text.count(")"))

    def test_empty_group_dropped(self):
        text, _, _ = compile_boolean_tsquery("waiver AND ()")
        self.assertEqual(text, "waiver")

    def test_leading_operator_trimmed(self):
        text, _, _ = compile_boolean_tsquery("AND waiver & estoppel")
        self.assertEqual(text, "waiver & estoppel")

    def test_no_unsafe_characters_leak(self):
        text, _, _ = compile_boolean_tsquery(
            "waiver'; DROP TABLE x; -- & (estoppel!)"
        )
        for ch in (";", "'", '"'):
            self.assertNotIn(ch, text)
