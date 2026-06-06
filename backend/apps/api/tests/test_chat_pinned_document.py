"""Tests for per-document chat pinning (the "/" doc-chat panel).

When a chat request carries a ``node_id``, the backend injects that document's
current text into the conversation as an authoritative system message so the
model can answer about it directly. Covers both shapes ``_pinned_document``
handles: a statute section and a caselaw decision (text spread across child
opinion nodes).
"""

from __future__ import annotations

from django.test import TestCase

from apps.api.chat import DOC_CONTEXT_MAX_CHARS, _pinned_document

from ._factories import make_caselaw_case, make_iowa_corpus_minimal


class PinnedDocumentTests(TestCase):
    def test_none_and_missing_return_none(self):
        # No pin, and a non-existent id, both yield no injected context.
        self.assertIsNone(_pinned_document(None))
        self.assertIsNone(_pinned_document(0))
        self.assertIsNone(_pinned_document(999_999_999))

    def test_statute_section_text_is_pinned(self):
        _src, section, _version = make_iowa_corpus_minimal()
        doc = _pinned_document(section.id)
        assert doc is not None
        # Framed as authoritative pinned context...
        self.assertIn("PINNED DOCUMENT", doc)
        # ...headed by the canonical citation + heading...
        self.assertIn("Iowa Code 714.16", doc)
        self.assertIn("Consumer fraud", doc)
        # ...and carrying the section's actual body text.
        self.assertIn("deceptive practice", doc)

    def test_decision_pins_caption_and_opinion_text(self):
        decision, _opinion, _version = make_caselaw_case(
            cl_cluster_id=4242,
            cl_opinion_id=99,
            case_name="State v. Pinned",
            body="The defendant's motion to suppress should have been granted.",
            citations=["999 N.W.2d 1"],
        )
        doc = _pinned_document(decision.id)
        assert doc is not None
        # Caption line: case name + court + date + reporter cite.
        self.assertIn("State v. Pinned", doc)
        self.assertIn("Supreme Court of Iowa", doc)
        self.assertIn("999 N.W.2d 1", doc)
        # The child opinion's text is concatenated in (it lives on the opinion
        # node, not the decision node).
        self.assertIn("motion to suppress", doc)

    def test_decision_without_approved_text_returns_none(self):
        # An opinion node with no approved version => nothing to ground on.
        decision, _opinion, _version = make_caselaw_case(
            cl_cluster_id=4343,
            cl_opinion_id=100,
            with_version=False,
        )
        self.assertIsNone(_pinned_document(decision.id))

    def test_long_body_is_truncated_with_marker(self):
        _src, section, version = make_iowa_corpus_minimal()
        version.body_text = "x" * (DOC_CONTEXT_MAX_CHARS + 5_000)
        version.save(update_fields=["body_text"])
        doc = _pinned_document(section.id)
        assert doc is not None
        self.assertIn("[document truncated", doc)
        # The verbatim slice is bounded; the header + framing add a little, so
        # assert the body portion didn't blow past the cap wholesale.
        self.assertLess(len(doc), DOC_CONTEXT_MAX_CHARS + 2_000)
