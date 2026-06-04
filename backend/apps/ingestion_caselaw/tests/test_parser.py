"""Pure parser tests — text selection/cleaning, hashing, derived fields."""

from __future__ import annotations

import datetime as dt

from django.test import SimpleTestCase

from ..parser import (
    extract_citation_links,
    format_citation,
    parse_decision,
    parse_opinion,
    select_body,
)


def _op_record(**over):
    rec = {
        "cl_opinion_id": 9000, "cl_cluster_id": 1000,
        "node_path": "cl-cluster-1000/op-9000", "type": "020lead",
        "author_str": "Mansfield", "author_id": 42, "per_curiam": False,
        "joined_by_str": "", "page_count": 10, "download_url": "",
        "extracted_by_ocr": False, "sha1": "abc",
        "plain_text": "", "html": "", "html_lawbox": "", "html_columbia": "",
        "html_anon_2020": "", "xml_harvard": "", "html_with_citations": "",
    }
    rec.update(over)
    return rec


def _dec_record(**over):
    rec = {
        "cl_cluster_id": 1000, "node_path": "cl-cluster-1000", "docket_id": 100,
        "court_id": "iowa", "court_name": "Supreme Court of Iowa",
        "case_name": "State v. Smith", "case_name_short": "Smith",
        "case_name_full": "State v. John Smith", "date_filed": "2020-05-01",
        "precedential_status": "Published", "judges": "Mansfield",
        "citation_count": 3, "scdb_id": "", "slug": "s",
        "syllabus": "", "headnotes": "", "summary": "", "disposition": "affirmed",
        "posture": "", "nature_of_suit": "",
    }
    rec.update(over)
    return rec


class SelectBodyTests(SimpleTestCase):
    def test_prefers_html_with_citations_and_strips_tags(self):
        rec = _op_record(
            html_with_citations="<p>Held: <a href='#'>see</a> &amp; affirmed.</p>",
            plain_text="raw fallback",
        )
        self.assertEqual(select_body(rec), "Held: see & affirmed.")

    def test_falls_through_to_plain_text(self):
        rec = _op_record(plain_text="Just plain text.")
        self.assertEqual(select_body(rec), "Just plain text.")

    def test_empty_when_all_columns_blank(self):
        self.assertEqual(select_body(_op_record()), "")

    def test_xml_harvard_is_stripped(self):
        rec = _op_record(xml_harvard="<opinion><p>From CAP.</p></opinion>")
        self.assertEqual(select_body(rec), "From CAP.")


class ParseOpinionTests(SimpleTestCase):
    def test_fields_and_derived(self):
        op = parse_opinion(_op_record(plain_text="Body."))
        self.assertEqual(op.cl_opinion_id, 9000)
        self.assertEqual(op.path, "cl-cluster-1000/op-9000")
        self.assertEqual(op.ordinal, "020")
        self.assertEqual(op.heading, "Lead Opinion (Mansfield)")
        self.assertEqual(op.body_text, "Body.")
        self.assertEqual(op.author_id, 42)

    def test_dissent_and_per_curiam_headings(self):
        self.assertEqual(
            parse_opinion(_op_record(type="040dissent", author_str="Appel")).heading,
            "Dissent (Appel)",
        )
        self.assertEqual(
            parse_opinion(_op_record(type="010combined", per_curiam=True,
                                     author_str="")).heading,
            "Opinion (Per Curiam)",
        )

    def test_unknown_type_defaults(self):
        op = parse_opinion(_op_record(type="", author_str=""))
        self.assertEqual(op.ordinal, "999")
        self.assertEqual(op.heading, "Opinion")
        op2 = parse_opinion(_op_record(type="weird-no-prefix"))
        self.assertEqual(op2.ordinal, "999")

    def test_bare_lt_in_body_not_eaten(self):
        # A real parser must not treat "x < 5" as a tag (the old regex would).
        op = parse_opinion(_op_record(
            html_with_citations="<p>if (x < 5) then affirmed</p>"))
        self.assertIn("x < 5", op.body_text)
        self.assertIn("affirmed", op.body_text)

    def test_script_style_dropped(self):
        op = parse_opinion(_op_record(
            html="<style>p{color:red}</style><p>Body.</p><script>x()</script>"))
        self.assertEqual(op.body_text, "Body.")

    def test_content_hash_is_body_only(self):
        a = parse_opinion(_op_record(plain_text="Same body.", author_str="X"))
        b = parse_opinion(_op_record(plain_text="Same body.", author_str="Y"))
        self.assertEqual(a.content_hash, b.content_hash)  # heading excluded
        c = parse_opinion(_op_record(plain_text="Different."))
        self.assertNotEqual(a.content_hash, c.content_hash)


class ParseDecisionTests(SimpleTestCase):
    def test_basic_fields_and_date(self):
        dec = parse_decision(_dec_record(), docket_number="12-3456",
                             citations=("987 N.W.2d 123",))
        self.assertEqual(dec.path, "cl-cluster-1000")
        self.assertEqual(dec.heading, "State v. Smith")
        self.assertEqual(dec.date_filed, dt.date(2020, 5, 1))
        self.assertEqual(dec.docket_number, "12-3456")
        self.assertEqual(dec.source_metadata["citations"], ["987 N.W.2d 123"])
        self.assertEqual(dec.source_metadata["court_id"], "iowa")

    def test_bad_date_returns_none(self):
        self.assertIsNone(parse_decision(_dec_record(date_filed="")).date_filed)
        self.assertIsNone(parse_decision(_dec_record(date_filed="0000-00-00")).date_filed)

    def test_head_matter_only_when_present(self):
        self.assertFalse(parse_decision(_dec_record()).has_head_matter)
        dec = parse_decision(_dec_record(syllabus="<p>The syllabus.</p>"))
        self.assertTrue(dec.has_head_matter)
        self.assertIn("Syllabus", dec.head_matter_text)
        self.assertIn("The syllabus.", dec.head_matter_text)

    def test_format_citation(self):
        self.assertEqual(
            format_citation({"volume": "987", "reporter": "N.W.2d", "page": "123"}),
            "987 N.W.2d 123",
        )


class ExtractCitationLinksTests(SimpleTestCase):
    def test_opinion_link(self):
        (link,) = extract_citation_links(
            '<p>See <a href="/opinion/12345/state-v-jones/">State v. Jones</a>.</p>'
        )
        self.assertEqual(link.kind, "opinion")
        self.assertEqual(link.cl_opinion_id, 12345)
        self.assertEqual(link.display, "State v. Jones")

    def test_reporter_link_segments(self):
        (link,) = extract_citation_links('<a href="/c/N.W.2d/759/3/">759 N.W.2d 3</a>')
        self.assertEqual(link.kind, "reporter")
        self.assertEqual(link.reporter, "N.W.2d")
        self.assertEqual(link.volume, "759")
        self.assertEqual(link.page, "3")
        self.assertIsNone(link.cl_opinion_id)

    def test_reporter_is_url_decoded(self):
        (link,) = extract_citation_links('<a href="/c/Colo.%20App./11/177/">x</a>')
        self.assertEqual(link.reporter, "Colo. App.")

    def test_skips_fragments_and_other_hrefs(self):
        links = extract_citation_links(
            '<a href="#fn1">1</a> text <a href="#p526">p</a> '
            '<a href="https://example.com">ext</a>'
        )
        self.assertEqual(links, ())

    def test_dedupes_preserving_order(self):
        links = extract_citation_links(
            '<a href="/opinion/1/a/">A</a> <a href="/c/N.W.2d/759/3/">cite</a> '
            '<a href="/opinion/1/a-again/">A2</a>'
        )
        self.assertEqual([l.kind for l in links], ["opinion", "reporter"])
        self.assertEqual(links[0].cl_opinion_id, 1)

    def test_empty_html(self):
        self.assertEqual(extract_citation_links(""), ())
        self.assertEqual(extract_citation_links("<p>no links</p>"), ())

    def test_malformed_reporter_link_dropped(self):
        # missing the page segment → not a valid /c/ form, dropped (no crash)
        self.assertEqual(extract_citation_links('<a href="/c/N.W.2d/759/">x</a>'), ())

    def test_unclosed_anchor_display_is_capped(self):
        # A malformed/unclosed <a> must not swallow the whole document into one
        # display string (which would overflow the unique-index btree row).
        html = '<a href="/opinion/5/x/">' + ("z" * 5000)
        (link,) = extract_citation_links(html)
        self.assertEqual(link.cl_opinion_id, 5)
        self.assertLessEqual(len(link.display), 400)

    def test_links_absent_from_parsed_body(self):
        # Invariant proof: select_body strips the <a> tags, so links MUST be read
        # from raw html (extract_citation_links), not from the parsed body.
        rec = _op_record(
            html_with_citations='<p>See <a href="/opinion/9/x/">Case</a> here.</p>'
        )
        body = parse_opinion(rec).body_text
        self.assertNotIn("href", body)
        self.assertNotIn("/opinion/", body)
        self.assertEqual(
            extract_citation_links(rec["html_with_citations"])[0].cl_opinion_id, 9
        )
