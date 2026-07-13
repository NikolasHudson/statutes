"""Rendering tests: citation linkification, HTML alternative, and the
express-request-only official-PDF attachments."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.api.tests._factories import make_caselaw_case, make_iowa_corpus_minimal
from apps.corpus.models import ReporterCitation
from apps.mail import render

BASE = "https://app.hudsonlegal.tech"


class LinkifyTests(TestCase):
    def test_statute_cite_links_and_official_pdf(self):
        _, section, _ = make_iowa_corpus_minimal()
        answer = "Consumer fraud is governed by Iowa Code § 714.16, which..."
        linked = render.linkify(answer, base_url=BASE)

        self.assertIn(f"[Iowa Code § 714.16]({BASE}/section/{section.id})", linked.markdown)
        (src,) = linked.sources
        self.assertEqual(src.url, f"{BASE}/section/{section.id}")
        self.assertIn("legis.iowa.gov", src.official_url)
        self.assertIn("714.16.pdf", src.official_url)

    def test_unresolvable_cite_stays_plain(self):
        make_iowa_corpus_minimal()
        answer = "See Iowa Code § 999.99 for details."
        linked = render.linkify(answer, base_url=BASE)
        self.assertEqual(linked.markdown, answer)
        self.assertEqual(linked.sources, [])

    def test_case_cite_links_via_reporter_resolver(self):
        decision, _, _ = make_caselaw_case(cl_cluster_id=1, cl_opinion_id=1)
        ReporterCitation.objects.create(
            cl_citation_id=1, cl_cluster_id=1,
            reporter="N.W.2d", volume="759", page="3", to_node=decision,
        )
        answer = "State v. Example, 759 N.W.2d 3 (Iowa 2009), held..."
        linked = render.linkify(answer, base_url=BASE)
        self.assertIn(f"[759 N.W.2d 3]({BASE}/case/{decision.id})", linked.markdown)

    def test_ambiguous_reporter_triple_not_linked(self):
        d1, _, _ = make_caselaw_case(cl_cluster_id=1, cl_opinion_id=1)
        d2, _, _ = make_caselaw_case(cl_cluster_id=2, cl_opinion_id=2)
        for i, node in enumerate((d1, d2), start=1):
            ReporterCitation.objects.create(
                cl_citation_id=i, cl_cluster_id=i,
                reporter="N.W.2d", volume="100", page="1", to_node=node,
            )
        answer = "See 100 N.W.2d 1."
        linked = render.linkify(answer, base_url=BASE)
        self.assertEqual(linked.markdown, answer)

    def test_existing_markdown_link_not_double_wrapped(self):
        _, section, _ = make_iowa_corpus_minimal()
        answer = "See [Iowa Code § 714.16](https://example.com/x)."
        linked = render.linkify(answer, base_url=BASE)
        self.assertEqual(linked.markdown, answer)

    def test_iowa_code_not_mistaken_for_iowa_reporter(self):
        # "2026 Iowa Code 714" must not hit the "<vol> Iowa <page>" pattern.
        linked = render.linkify("the 2026 Iowa Code 714 edition", base_url=BASE)
        self.assertEqual(linked.markdown, "the 2026 Iowa Code 714 edition")


class HtmlTests(TestCase):
    def test_markdown_renders_and_raw_html_is_escaped(self):
        html_body = render.render_html_body(
            "**Bold** and <script>alert(1)</script>", ["footer line"]
        )
        self.assertIn("<strong>Bold</strong>", html_body)
        self.assertNotIn("<script>", html_body)
        self.assertIn("&lt;script&gt;", html_body)
        self.assertIn("footer line", html_body)


class PdfAttachmentTests(TestCase):
    def test_wants_pdf(self):
        self.assertTrue(render.wants_pdf("Can you send the PDF of § 714.16?"))
        self.assertTrue(render.wants_pdf("attach the PDFs please"))
        self.assertFalse(render.wants_pdf("What does § 714.16 say?"))

    @mock.patch("apps.mail.render.requests.get")
    def test_attaches_official_pdf_for_cited_section(self, get):
        make_iowa_corpus_minimal()
        get.return_value = mock.Mock(status_code=200, content=b"%PDF-1.7 fake")
        out = render.official_pdf_attachments(
            "Please send me the pdf of Iowa Code § 714.16."
        )
        self.assertEqual([name for name, _ in out], ["Iowa Code 714.16.pdf"])
        (url,) = get.call_args.args
        self.assertIn("714.16.pdf", url)

    @mock.patch("apps.mail.render.requests.get")
    def test_non_pdf_response_is_skipped(self, get):
        make_iowa_corpus_minimal()
        get.return_value = mock.Mock(status_code=200, content=b"<html>error page")
        out = render.official_pdf_attachments("pdf of Iowa Code § 714.16 please")
        self.assertEqual(out, [])
