"""Chunking algorithm + case-meta header behavior.

The pure tests use a word-count token proxy (``_wc``) so they don't need the
voyage tokenizer; the invariants (budget, contiguity, overlap, exact offsets)
hold regardless of the counter.
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase, tag

from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    Source,
)
from apps.corpus.services.chunking import (
    build_chunks,
    chunk_body,
    format_header,
    header_for_version,
)


def _wc(text: str) -> int:
    return len(text.split())


def _para(word: str, n: int) -> str:
    return " ".join([word] * n)


class ChunkBodyTests(TestCase):
    def test_empty_or_whitespace_yields_no_chunks(self):
        self.assertEqual(chunk_body("", count_tokens=_wc), [])
        self.assertEqual(chunk_body("   \n\n  ", count_tokens=_wc), [])

    def test_short_body_is_one_chunk_with_exact_offsets(self):
        body = "alpha beta gamma delta"
        spans = chunk_body(body, count_tokens=_wc, target_tokens=100)
        self.assertEqual(len(spans), 1)
        s = spans[0]
        self.assertEqual(s.ordinal, 0)
        self.assertEqual(s.text, body)
        self.assertEqual(body[s.char_start : s.char_end], s.text)

    def test_offsets_always_reconstruct_the_text(self):
        body = "\n\n".join(_para(f"p{i}", 30) for i in range(8))
        spans = chunk_body(body, count_tokens=_wc, target_tokens=50, overlap_tokens=10)
        self.assertGreater(len(spans), 1)
        for s in spans:
            self.assertEqual(body[s.char_start : s.char_end], s.text)

    def test_ordinals_are_sequential(self):
        body = "\n\n".join(_para(f"p{i}", 30) for i in range(8))
        spans = chunk_body(body, count_tokens=_wc, target_tokens=50, overlap_tokens=10)
        self.assertEqual([s.ordinal for s in spans], list(range(len(spans))))

    def test_chunks_respect_token_budget_when_units_fit(self):
        # Each paragraph is 30 words < target 50, so no chunk should exceed 50.
        body = "\n\n".join(_para(f"p{i}", 30) for i in range(10))
        spans = chunk_body(body, count_tokens=_wc, target_tokens=50, overlap_tokens=0)
        for s in spans:
            self.assertLessEqual(_wc(s.text), 50)

    def test_chunks_are_contiguous_no_gaps(self):
        body = "\n\n".join(_para(f"p{i}", 30) for i in range(10))
        spans = chunk_body(body, count_tokens=_wc, target_tokens=50, overlap_tokens=10)
        for a, b in zip(spans, spans[1:]):
            # Whatever sits between consecutive chunks is only the paragraph
            # separator — never dropped content (overlaps give an empty slice).
            self.assertEqual(body[a.char_end : b.char_start].strip(), "")

    def test_overlap_actually_overlaps(self):
        body = "\n\n".join(_para(f"p{i}", 20) for i in range(12))
        with_ov = chunk_body(body, count_tokens=_wc, target_tokens=60, overlap_tokens=25)
        # At least one consecutive pair shares characters.
        self.assertTrue(
            any(b.char_start < a.char_end for a, b in zip(with_ov, with_ov[1:]))
        )

    def test_no_overlap_is_strictly_partitioned(self):
        body = "\n\n".join(_para(f"p{i}", 20) for i in range(12))
        spans = chunk_body(body, count_tokens=_wc, target_tokens=60, overlap_tokens=0)
        for a, b in zip(spans, spans[1:]):
            self.assertGreaterEqual(b.char_start, a.char_end)

    def test_oversized_single_paragraph_is_split(self):
        # One giant paragraph (no blank lines), no sentence punctuation → forces
        # the hard char-split fallback. Every chunk must stay within budget.
        body = _para("word", 500)
        spans = chunk_body(body, count_tokens=_wc, target_tokens=50, overlap_tokens=0)
        self.assertGreater(len(spans), 1)
        for s in spans:
            self.assertLessEqual(_wc(s.text), 50)

    def test_oversized_paragraph_splits_on_sentences(self):
        # A long paragraph with sentence boundaries should break on them.
        sentences = " ".join(f"This is sentence number {i} here." for i in range(40))
        spans = chunk_body(sentences, count_tokens=_wc, target_tokens=30, overlap_tokens=0)
        self.assertGreater(len(spans), 1)
        for s in spans:
            self.assertLessEqual(_wc(s.text), 30)


class FormatHeaderTests(TestCase):
    def test_full_header(self):
        self.assertEqual(
            format_header(
                case_name="State v. Smith",
                citation="987 N.W.2d 123",
                court_name="Supreme Court of Iowa",
                year="2019",
                opinion_label="Lead Opinion (Cady, C.J.)",
            ),
            "State v. Smith, 987 N.W.2d 123 (Supreme Court of Iowa 2019) "
            "— Lead Opinion (Cady, C.J.)",
        )

    def test_missing_citation_and_court(self):
        self.assertEqual(
            format_header(
                case_name="In re Marriage of Doe",
                citation="",
                court_name="",
                year="2005",
                opinion_label="Opinion",
            ),
            "In re Marriage of Doe (2005) — Opinion",
        )

    def test_only_case_name(self):
        self.assertEqual(
            format_header(
                case_name="Doe v. Roe", citation="", court_name="", year="", opinion_label=""
            ),
            "Doe v. Roe",
        )


@tag("postgres")
class BuildChunksTests(TestCase):
    def setUp(self):
        # The seed migrations already create the "iowa" jurisdiction.
        j, _ = Jurisdiction.objects.get_or_create(
            slug="iowa", defaults={"name": "Iowa", "abbreviation": "IA"}
        )
        # Own slug so the test is isolated from the seeded iowa-caselaw source.
        self.source = Source.objects.create(
            jurisdiction=j, slug="test-caselaw", name="Test Caselaw", citation_abbreviation="IA"
        )
        self.decision_t = NodeType.objects.create(
            source=self.source, key="decision", label_singular="Decision", level=1
        )
        self.opinion_t = NodeType.objects.create(
            source=self.source, key="opinion", label_singular="Opinion", level=2
        )

    def _decision(self) -> Node:
        return Node.objects.create(
            source=self.source,
            node_type=self.decision_t,
            ordinal="1",
            path="cl-cluster-1",
            heading="State v. Smith",
            source_metadata={
                "case_name": "State v. Smith",
                "court_name": "Supreme Court of Iowa",
                "date_filed": "2019-04-05",
                "citations": ["987 N.W.2d 123"],
            },
        )

    def _opinion(self, decision: Node, body: str) -> NodeVersion:
        node = Node.objects.create(
            source=self.source,
            node_type=self.opinion_t,
            parent=decision,
            ordinal="020",
            path="cl-cluster-1/op-1",
            heading="Lead Opinion (Cady, C.J.)",
        )
        return NodeVersion.objects.create(
            node=node,
            body_text=body,
            effective_from=dt.date(2019, 4, 5),
            content_hash="h",
        )

    def test_opinion_chunks_carry_parent_case_header(self):
        decision = self._decision()
        body = "\n\n".join(_para(f"p{i}", 40) for i in range(6))
        v = NodeVersion.objects.select_related("node", "node__parent").get(
            pk=self._opinion(decision, body).pk
        )
        chunks = build_chunks(v, count_tokens=_wc, target_tokens=80, overlap_tokens=15)

        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertEqual(
                c.context_header,
                "State v. Smith, 987 N.W.2d 123 (Supreme Court of Iowa 2019) "
                "— Lead Opinion (Cady, C.J.)",
            )
            # body_text is the raw span; offsets index the version body.
            self.assertEqual(v.body_text[c.char_start : c.char_end], c.body_text)
            self.assertTrue(c.content_hash)
            self.assertEqual(c.embedding_source_hash, "")

    def test_head_matter_version_uses_own_node_metadata(self):
        decision = self._decision()
        hv = NodeVersion.objects.create(
            node=decision,
            body_text="Syllabus. " + _para("text", 100),
            effective_from=dt.date(2019, 4, 5),
            content_hash="hm",
        )
        hv = NodeVersion.objects.select_related("node", "node__parent").get(pk=hv.pk)
        self.assertIn("State v. Smith", header_for_version(hv))
        self.assertIn("Head Matter", header_for_version(hv))
