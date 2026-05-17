"""Validator tests — DB-free.

Build a minimal Changeset by hand and verify each rule fires (or doesn't) as
designed. These tests guard against silent regressions in the failure modes
the brief calls out: missing headings, hash drift, unannounced repeals.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.ingestion_iowa_code.differ import (
    Changeset,
    ChapterChange,
    SectionChange,
)
from apps.ingestion_iowa_code.parser import (
    ParsedChapter,
    ParsedSection,
    ParseResult,
)
from apps.ingestion_iowa_code.validators import (
    REPEAL_RATIO_LIMIT,
    ValidationError,
    validate,
)


def _section(path: str, heading: str = "h", body: str = "body") -> ParsedSection:
    chapter, _, _rest = path.partition(".")
    return ParsedSection(
        chapter=chapter,
        number=path,
        heading=heading,
        body_text=body,
        history_brackets=(),
        acts_citations=(),
        referred_to_in=(),
        citation_pdf_url="",
        citation_html_url="",
        source_rtf_url="",
    )


def _result(*sections: ParsedSection) -> ParseResult:
    by_chapter: dict[str, list[ParsedSection]] = {}
    for s in sections:
        by_chapter.setdefault(s.chapter, []).append(s)
    chapters = tuple(
        ParsedChapter(
            number=ch,
            title=f"chapter {ch}",
            chapter_html_url="",
            chapter_pdf_url="",
            sections=tuple(secs),
        )
        for ch, secs in by_chapter.items()
    )
    return ParseResult(code_year=2026, chapters=chapters)


class ValidatorTests(SimpleTestCase):
    def test_clean_input_passes(self):
        sec = _section("1.1")
        cs = Changeset(
            chapters_added=[ChapterChange(parsed=ParsedChapter("1", "", "", "", (sec,)), is_new=True)],
            sections_added=[SectionChange(parsed=sec, prior_content_hash=None)],
        )
        warnings = validate(_result(sec), cs)
        self.assertEqual(warnings, [])

    def test_unresolved_cross_reference_warns_only(self):
        sec = ParsedSection(
            chapter="1", number="1.1", heading="h", body_text="b",
            history_brackets=(), acts_citations=(),
            referred_to_in=("9999.9",),  # not in this run
            citation_pdf_url="", citation_html_url="", source_rtf_url="",
        )
        cs = Changeset(
            sections_added=[SectionChange(parsed=sec, prior_content_hash=None)],
        )
        issues = validate(_result(sec), cs)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "warning")
        self.assertEqual(issues[0].code, "unresolved_cross_reference")

    def test_repeal_wave_blocks(self):
        # 1 added, 5 repealed → 5/6 = 83% repeal — should error.
        sec = _section("1.1")
        cs = Changeset(
            sections_added=[SectionChange(parsed=sec, prior_content_hash=None)],
            sections_repealed=[f"1.{i}" for i in range(2, 7)],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate(_result(sec), cs)
        codes = {i.code for i in ctx.exception.issues if i.severity == "error"}
        self.assertIn("unannounced_repeal_wave", codes)

    def test_repeal_under_threshold_passes(self):
        # 100 added, 1 repealed → well under threshold.
        added = [_section(f"1.{i}") for i in range(1, 101)]
        cs = Changeset(
            sections_added=[
                SectionChange(parsed=s, prior_content_hash=None) for s in added
            ],
            sections_repealed=["1.999"],
        )
        warnings = validate(_result(*added), cs)
        codes = {w.code for w in warnings}
        self.assertNotIn("unannounced_repeal_wave", codes)
        self.assertGreater(REPEAL_RATIO_LIMIT, 1 / 101)  # sanity

    def test_hash_drift_unchanged_errors(self):
        sec = _section("1.1")
        cs = Changeset(
            sections_unchanged=[
                SectionChange(parsed=sec, prior_content_hash="not-the-real-hash")
            ],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate(_result(sec), cs)
        codes = {i.code for i in ctx.exception.issues if i.severity == "error"}
        self.assertIn("hash_drift_unchanged", codes)

    def test_hash_drift_amended_errors_when_hash_matches(self):
        sec = _section("1.1")
        cs = Changeset(
            sections_amended=[
                SectionChange(parsed=sec, prior_content_hash=sec.content_hash)
            ],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate(_result(sec), cs)
        codes = {i.code for i in ctx.exception.issues if i.severity == "error"}
        self.assertIn("hash_drift_amended", codes)
