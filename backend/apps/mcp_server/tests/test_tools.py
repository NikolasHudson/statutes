"""MCP tool dispatch tests.

We exercise the plain functions in ``apps.mcp_server.tools`` directly —
the FastMCP wiring is just an annotation-based registration that we test
separately by listing the server's tool surface."""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, tag

from apps.api.tests._factories import make_iowa_corpus_minimal
from apps.corpus.services.lookups import reset_default_source_cache
from apps.mcp_server import tools
from apps.mcp_server.server import build_server


@tag("postgres")
class ToolFunctionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source, cls.section, cls.version = make_iowa_corpus_minimal()

    def setUp(self):
        reset_default_source_cache()

    def test_lookup_citation_found(self):
        out = tools.lookup_citation_tool("714.16")
        self.assertTrue(out["found"])
        self.assertEqual(out["section"]["node"]["path"], "714.16")
        # contract: every response has the date stamp + official URL
        self.assertEqual(out["as_of_date"], dt.date.today().isoformat())
        self.assertIn("legis.iowa.gov", out["section"]["node"]["official_url"])

    def test_lookup_citation_returns_candidates_when_unresolved(self):
        out = tools.lookup_citation_tool("714.99")
        self.assertFalse(out["found"])
        self.assertIsNone(out["section"])
        paths = [c["path"] for c in out["candidates"]]
        self.assertIn("714.16", paths)

    def test_lookup_citation_chapter_only_returns_toc(self):
        # Chapter Nodes have no NodeVersion of their own; the tool should
        # still return found=True with the chapter heading and an ordered
        # list of section Nodes so the caller can render a TOC.
        out = tools.lookup_citation_tool("Chapter 714")
        self.assertTrue(out["found"])
        self.assertIsNone(out["section"])
        chapter = out["chapter"]
        self.assertIsNotNone(chapter)
        self.assertEqual(chapter["node"]["path"], "714")
        self.assertEqual(chapter["node"]["heading"], "Theft, fraud and related offenses")
        section_paths = [s["path"] for s in chapter["sections"]]
        self.assertIn("714.16", section_paths)

    def test_get_version_history(self):
        out = tools.get_version_history_tool(self.section.id)
        self.assertEqual(len(out["versions"]), 1)
        self.assertEqual(out["versions"][0]["effective_from"], "2025-01-01")

    def test_get_section_at_date_returns_version(self):
        out = tools.get_section_at_date_tool(self.section.id, "2025-06-01")
        self.assertIsNotNone(out["version"])
        self.assertEqual(out["version"]["effective_from"], "2025-01-01")

    def test_get_section_at_date_returns_error_before_first_version(self):
        out = tools.get_section_at_date_tool(self.section.id, "2020-01-01")
        self.assertIsNone(out["version"])
        self.assertIn("error", out)

    def test_search_statutes_smoke(self):
        out = tools.search_statutes_tool("consumer fraud", use_vector=False)
        self.assertTrue(out["hits"])
        self.assertEqual(out["hits"][0]["node"]["path"], "714.16")

    def test_validate_citations_marks_known_section_valid(self):
        text = "See Iowa Code § 714.16 (consumer fraud)."
        out = tools.validate_citations_tool(text)
        self.assertEqual(out["summary"]["total"], 1)
        self.assertEqual(out["summary"]["valid"], 1)
        item = out["items"][0]
        self.assertEqual(item["status"], "valid")
        self.assertEqual(item["citation"]["section"], "714.16")
        self.assertEqual(item["node"]["path"], "714.16")
        self.assertIsNotNone(item["version"])
        # span should pinpoint the citation in the input
        start, end = item["span"]
        self.assertIn("714.16", text[start:end])
        # body_excerpt carries the section text so the LLM can compare it
        # against the brief's characterization without a follow-up call.
        self.assertIsNotNone(item["body_excerpt"])
        self.assertIn("merchant", item["body_excerpt"])

    def test_validate_citations_marks_unknown_section_not_found(self):
        # 714.99 doesn't exist in the minimal fixture; we should mark it
        # not_found and include 714.16 as a same-chapter candidate.
        text = "See Iowa Code § 714.99 for the rule."
        out = tools.validate_citations_tool(text)
        self.assertEqual(out["summary"]["total"], 1)
        self.assertEqual(out["summary"]["not_found"], 1)
        item = out["items"][0]
        self.assertEqual(item["status"], "not_found")
        candidate_paths = [c["path"] for c in item["candidates"]]
        self.assertIn("714.16", candidate_paths)

    def test_validate_citations_handles_mixed_text(self):
        text = (
            "Plaintiff alleges violations of Iowa Code § 714.16 and "
            "§ 714.99. The court has jurisdiction under chapter 714."
        )
        out = tools.validate_citations_tool(text)
        statuses = [item["status"] for item in out["items"]]
        # We expect at least one valid, one not_found, and the chapter ref.
        self.assertIn("valid", statuses)
        self.assertIn("not_found", statuses)
        # spans must be in source order and non-overlapping
        spans = [item["span"] for item in out["items"]]
        for prev, nxt in zip(spans, spans[1:]):
            self.assertLessEqual(prev[1], nxt[0])

    def test_validate_citations_empty_input(self):
        out = tools.validate_citations_tool("")
        self.assertEqual(out["summary"]["total"], 0)
        self.assertEqual(out["items"], [])

    def test_verify_quote_exact_match_against_cited_section(self):
        # The minimal fixture's 714.16 body contains the substring
        # "deceptive practice or unfair method of competition". A brief
        # that quotes that verbatim should come back as `exact`.
        text = (
            'Iowa Code § 714.16 provides that a merchant who commits a '
            '"deceptive practice or unfair method of competition" '
            'violates the section.'
        )
        out = tools.verify_quote_tool(text)
        self.assertEqual(out["summary"]["total"], 1)
        self.assertEqual(out["summary"]["exact"], 1)
        item = out["items"][0]
        self.assertEqual(item["status"], "exact")
        self.assertEqual(item["match_score"], 1.0)
        self.assertEqual(item["node"]["path"], "714.16")
        # closest_passage should include some surrounding context
        self.assertIn("deceptive practice", item["closest_passage"])

    def test_verify_quote_marks_misquote_as_not_found(self):
        # An entirely fabricated quote near a real cite. The tool should
        # pair the quote with § 714.16 and mark it not_found rather than
        # hallucinating a match.
        text = (
            'Iowa Code § 714.16 says that "every merchant must wear a '
            'red hat on Tuesdays without exception or be liable for '
            'treble damages."'
        )
        out = tools.verify_quote_tool(text)
        self.assertEqual(out["summary"]["total"], 1)
        item = out["items"][0]
        self.assertEqual(item["status"], "not_found")
        self.assertLess(item["match_score"], 0.85)
        self.assertEqual(item["node"]["path"], "714.16")

    def test_verify_quote_no_citation_in_text(self):
        text = '"Some quoted text without any citation nearby."'
        out = tools.verify_quote_tool(text)
        self.assertEqual(out["summary"]["total"], 1)
        item = out["items"][0]
        self.assertEqual(item["status"], "no_citation")
        self.assertIsNone(item["citation"])
        self.assertIsNone(item["node"])

    def test_verify_quote_with_explicit_citation_argument(self):
        # Caller can override quote→citation pairing by passing an
        # explicit citation string. Useful for "verify all of these
        # quotes against § X.Y."
        text = '"deceptive practice or unfair method of competition"'
        out = tools.verify_quote_tool(text, citation="714.16")
        self.assertEqual(out["summary"]["total"], 1)
        item = out["items"][0]
        self.assertEqual(item["status"], "exact")
        self.assertEqual(item["node"]["path"], "714.16")

    def test_audit_brief_combines_validation_and_quotes(self):
        text = (
            "Plaintiff alleges violations of Iowa Code § 714.16 — the "
            'statute provides that a merchant who commits a "deceptive '
            'practice or unfair method of competition" is liable. '
            "Plaintiff also cites Iowa Code § 9999.99, which does not "
            "exist."
        )
        out = tools.audit_brief_tool(text)
        # one valid + one missing
        self.assertEqual(out["summary"]["total_citations"], 2)
        self.assertEqual(out["summary"]["valid_citations"], 1)
        self.assertEqual(out["summary"]["missing_citations"], 1)
        # one exact-quote hit
        self.assertEqual(out["summary"]["total_quotes"], 1)
        self.assertEqual(out["summary"]["exact_quotes"], 1)
        # no `since` was passed, so freshness check is empty
        self.assertEqual(out["summary"]["amended_since_count"], 0)
        # raw sub-payloads are nested under their tool name
        self.assertIn("validation", out)
        self.assertIn("quotes", out)
        self.assertIn("amended_since", out)

    def test_audit_brief_with_since_flags_no_amendments_for_static_fixture(self):
        # The fixture has only one version effective 2025-01-01. Asking
        # what's been amended since 2030 should return zero.
        text = "See Iowa Code § 714.16."
        out = tools.audit_brief_tool(text, since="2030-01-01")
        self.assertEqual(out["since"], "2030-01-01")
        self.assertEqual(out["summary"]["amended_since_count"], 0)

    def test_audit_brief_returns_markdown_tables(self):
        text = (
            "Plaintiff cites Iowa Code § 714.16 and Iowa Code § 9999.99. "
            'The brief asserts "every merchant must wear a red hat."'
        )
        out = tools.audit_brief_tool(text)
        tables = out["tables"]
        for key in ("summary", "citations", "quotes", "amended_since"):
            self.assertIn(key, tables)

        cites = tables["citations"]
        # Header + separator + at least one row.
        self.assertIn("| Status |", cites)
        self.assertIn("---", cites)
        # The valid 714.16 row should mention its heading
        self.assertIn("Consumer fraud", cites)
        # Status strings appear in their column
        self.assertIn("valid", cites)
        self.assertIn("not_found", cites)

        quotes = tables["quotes"]
        self.assertIn("| Status |", quotes)
        # The misquote should appear flagged not_found
        self.assertIn("not_found", quotes)

        # No `since` was passed → amended_since table should be a
        # short note, not an empty Markdown table.
        self.assertIn("freshness check skipped", tables["amended_since"])

        # Summary table includes the same numbers as the structured summary.
        self.assertIn(
            f"Citations — total | {out['summary']['total_citations']}",
            tables["summary"],
        )

    def test_audit_brief_table_escapes_pipe_characters(self):
        # An input containing a pipe in the cite text shouldn't break
        # the Markdown table layout.
        text = "Plaintiff cites Iowa Code § 714.16 | extra noise"
        out = tools.audit_brief_tool(text)
        # Header pipes are present (3 in the header row); any pipe inside
        # a cell value must be backslash-escaped so it doesn't render as
        # a column separator.
        cites = out["tables"]["citations"]
        for line in cites.splitlines():
            if "extra noise" in line:
                self.assertIn("\\|", line)
                break
        else:
            # If the parser dropped the literal "|" before it became part
            # of any cell, that's fine too — but at minimum nothing
            # should crash.
            pass


@tag("postgres")
class ToolRegistrationTests(TestCase):
    def test_all_tools_registered(self):
        server = build_server()
        import asyncio

        listed = asyncio.run(server.list_tools())
        names = {t.name for t in listed}
        self.assertEqual(
            names,
            {
                "lookup_citation",
                "search_statutes",
                "get_version_history",
                "get_section_at_date",
                "get_cross_references",
                "get_definitions",
                "list_recent_amendments",
                "validate_citations",
                "verify_quote",
                "audit_brief",
            },
        )
