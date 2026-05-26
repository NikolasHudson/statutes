"""Parser tests — DB-free.

Golden file: backend/data/samples/iowa_code_probe.json. Test asserts shape
invariants over the full sample set, then pins exact values for one section.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.ingestion_iowa_code.parser import (
    ParseError,
    _normalize_body,
    parse_probe_json,
)


SAMPLE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "samples" / "iowa_code_probe.json"
)


class ProbeShapeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with SAMPLE_PATH.open() as f:
            cls.payload = json.load(f)
        cls.parsed = parse_probe_json(cls.payload)

    def test_parses_eleven_chapters(self):
        self.assertEqual(len(self.parsed.chapters), 11)

    def test_code_year(self):
        self.assertEqual(self.parsed.code_year, 2026)

    def test_total_sections_match_summary(self):
        total = sum(len(c.sections) for c in self.parsed.chapters)
        self.assertEqual(total, self.payload["summary"]["total_sections"])

    def test_every_section_has_heading(self):
        empties = [s.path for s in self.parsed.iter_sections() if not s.heading]
        self.assertEqual(empties, [])

    def test_every_section_path_starts_with_chapter(self):
        for chapter in self.parsed.chapters:
            for section in chapter.sections:
                self.assertTrue(
                    section.path.startswith(f"{chapter.number}."),
                    f"{section.path} not under chapter {chapter.number}",
                )

    def test_section_paths_are_unique(self):
        paths = [s.path for s in self.parsed.iter_sections()]
        self.assertEqual(len(paths), len(set(paths)))

    def test_content_hash_is_deterministic(self):
        again = parse_probe_json(self.payload)
        original = {s.path: s.content_hash for s in self.parsed.iter_sections()}
        replay = {s.path: s.content_hash for s in again.iter_sections()}
        self.assertEqual(original, replay)

    def test_content_hash_changes_when_body_changes(self):
        sec = next(self.parsed.iter_sections())
        mutated = dict(self.payload)
        mutated_samples = json.loads(json.dumps(self.payload["samples"]))
        # Prepend a token so the trailing-artifact normalizer can't swallow it.
        mutated_samples[0]["sections"][0]["body_text"] = (
            "MUTATED " + mutated_samples[0]["sections"][0]["body_text"]
        )
        mutated["samples"] = mutated_samples
        mutated_parsed = parse_probe_json(mutated)
        new = next(iter(mutated_parsed.chapters)).sections[0]
        self.assertEqual(sec.path, new.path)
        self.assertNotEqual(sec.content_hash, new.content_hash)

    def test_pinned_section_1_1(self):
        chapter_1 = next(c for c in self.parsed.chapters if c.number == "1")
        section_1_1 = next(s for s in chapter_1.sections if s.path == "1.1")
        self.assertEqual(section_1_1.heading, "State boundaries")
        self.assertIn("boundaries of the state", section_1_1.body_text)
        self.assertEqual(section_1_1.referred_to_in, ("1.2",))
        self.assertTrue(
            section_1_1.citation_pdf_url.endswith("/section/2026/1.1.pdf")
        )

    def test_trailing_referred_artifact_stripped(self):
        chapter_1 = next(c for c in self.parsed.chapters if c.number == "1")
        section_1_1 = next(s for s in chapter_1.sections if s.path == "1.1")
        self.assertNotIn("eferred to in", section_1_1.body_text)


class ParseErrorTests(SimpleTestCase):
    def test_rejects_non_object(self):
        with self.assertRaises(ParseError):
            parse_probe_json([])  # type: ignore[arg-type]

    def test_requires_code_year(self):
        with self.assertRaises(ParseError):
            parse_probe_json({"samples": []})

    def test_skips_section_outside_its_chapter(self):
        # RTF scraper occasionally treats inline cross-references (e.g. court
        # rule "1.306") as section numbers. Parser should record + skip them
        # rather than aborting the whole ingest.
        payload = {
            "code_year": 2026,
            "samples": [
                {
                    "chapter": "1",
                    "chapter_title": "X",
                    "sections": [
                        {
                            "number": "1.1",
                            "heading": "Real section",
                            "body_text": "...",
                        },
                        {
                            "number": "2.1",
                            "heading": "Wrong chapter",
                            "body_text": "...",
                        },
                    ],
                }
            ],
        }
        parsed = parse_probe_json(payload)
        self.assertEqual(len(parsed.chapters), 1)
        self.assertEqual(len(parsed.chapters[0].sections), 1)
        self.assertEqual(parsed.chapters[0].sections[0].number, "1.1")
        self.assertEqual(len(parsed.skipped_sections), 1)
        self.assertEqual(parsed.skipped_sections[0].number, "2.1")
        self.assertIn("does not match", parsed.skipped_sections[0].reason)

    def test_rejects_section_without_heading(self):
        payload = {
            "code_year": 2026,
            "samples": [
                {
                    "chapter": "1",
                    "chapter_title": "X",
                    "sections": [
                        {"number": "1.1", "heading": "", "body_text": "..."}
                    ],
                }
            ],
        }
        with self.assertRaises(ParseError):
            parse_probe_json(payload)


class NormalizeBodyTests(SimpleTestCase):
    """The 'eferred to in' artifact (dropped leading R + stray '; ') shows up
    in two shapes; both must be stripped without eating real trailing text."""

    def test_strips_trailing_line_variant(self):
        body = (
            "The boundaries of the state are as defined in the preamble.\n\n"
            "eferred to in §1.2"
        )
        self.assertEqual(
            _normalize_body(body),
            "The boundaries of the state are as defined in the preamble.",
        )

    def test_strips_inline_variant_but_keeps_following_note(self):
        # As seen on §2.10: artifact spliced onto the Acts-history line, with a
        # real "See …" constitutional note on the next line that must survive.
        body = (
            "…final adjournment.\n\n"
            "83 Acts, ch 205, §20; 97 Acts, ch 204, §16; ; ; ; "
            "eferred to in §2.14, 2.32A, 2.40\n"
            "See Iowa Constitution, Art. III, §25"
        )
        self.assertEqual(
            _normalize_body(body),
            "…final adjournment.\n\n"
            "83 Acts, ch 205, §20; 97 Acts, ch 204, §16\n"
            "See Iowa Constitution, Art. III, §25",
        )

    def test_leaves_clean_body_untouched(self):
        body = "1.\xa0\xa0First.\n\xa0\xa02.\xa0\xa0Second."
        self.assertEqual(_normalize_body(body), body)
