"""backfill_acts_code_edges: act→Code CrossReference edges + the statute-side
supersession tripwire (CaseResearchNote kind=act_supersession)."""

from __future__ import annotations

import datetime as dt
import hashlib
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.api.tests._factories import make_iowa_corpus_minimal
from apps.corpus.models import (
    CaseResearchNote,
    CrossReference,
    Node,
    NodeVersion,
    ReviewStatus,
    Source,
)


def _act_section(path, affects, *, kind="repeal", edges=None):
    src = Source.objects.get(slug="iowa-acts")
    types = {nt.key: nt for nt in src.node_types.all()}
    parts = path.split(".")
    session, _ = Node.objects.get_or_create(
        source=src, path=parts[0],
        defaults={"node_type": types["session"], "ordinal": parts[0], "heading": parts[0]},
    )
    chapter, _ = Node.objects.get_or_create(
        source=src, path=f"{parts[0]}.{parts[1]}",
        defaults={
            "node_type": types["chapter"], "parent": session,
            "ordinal": parts[1], "heading": "An act",
        },
    )
    node = Node.objects.create(
        source=src, node_type=types["section"], parent=chapter,
        ordinal=parts[2], path=path, heading="",
        source_metadata={"kind": kind, "edges": edges or [], "affects": affects},
    )
    body = "REPEAL.  Section text."
    NodeVersion.objects.create(
        node=node, body_text=body, effective_from=dt.date(2024, 7, 1),
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        review_status=ReviewStatus.APPROVED,
    )
    return node


def _repeal_row(code_ref, eff_date, bill="SF2385"):
    return {
        "bill": bill, "action": "Repeal", "code_ref": code_ref,
        "eff_date": eff_date, "gov_action": "Signed", "gov_date": "2024-05-17",
        "chapter_only": False, "new_code": False, "bill_sections": [53],
    }


class ActsCodeEdgesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # iowa-code § 714.16 with real body text, effective 2025-01-01
        cls.code_src, cls.code_section, cls.version = make_iowa_corpus_minimal()
        cls.version.effective_from = dt.date(2025, 1, 1)
        cls.version.save(update_fields=["effective_from"])

    def run_cmd(self):
        out = StringIO()
        call_command("backfill_acts_code_edges", stdout=out)
        return out.getvalue()

    def test_internal_edge_written_and_idempotent(self):
        act = _act_section("2024.1170.53", [_repeal_row("714.16", "2026-07-01")])
        self.run_cmd()
        self.run_cmd()  # idempotent: delete-and-rebuild, no dupes
        edges = CrossReference.objects.filter(source="act_affects")
        self.assertEqual(edges.count(), 1)
        edge = edges.get()
        self.assertEqual(edge.to_node, self.code_section)
        self.assertEqual(edge.from_version.node, act)

    def test_unresolved_ref_becomes_external_edge(self):
        _act_section("2024.1170.54", [_repeal_row("999.99", "2026-07-01")])
        self.run_cmd()
        edge = CrossReference.objects.filter(source="act_affects").get()
        self.assertIsNone(edge.to_node)
        self.assertEqual(edge.external_text, "Iowa Code 999.99")

    def test_postdating_repeal_writes_supersession_note(self):
        # Repeal effective AFTER our section's text (2025-01-01) → stale.
        _act_section("2024.1170.53", [_repeal_row("714.16", "2026-07-01")])
        self.run_cmd()
        note = CaseResearchNote.objects.get(
            node=self.code_section, kind="act_supersession"
        )
        self.assertEqual(note.status, "adverse")
        self.assertTrue(note.corpus_verified)
        self.assertIn("2024 Iowa Acts, ch. 1170, §53", note.evidence)
        self.assertIn("2026-07-01", note.evidence)

    def test_old_repeal_of_recreated_section_is_not_noted(self):
        # Repeal effective BEFORE our text: the section was recreated (has
        # real current text) — the § 256.9 false-alarm shape.
        _act_section("2024.1170.53", [_repeal_row("714.16", "2019-07-01")])
        self.run_cmd()
        self.assertFalse(
            CaseResearchNote.objects.filter(kind="act_supersession").exists()
        )

    def test_old_repeal_of_empty_stub_is_noted(self):
        self.version.body_text = ""
        self.version.save(update_fields=["body_text"])
        _act_section("2024.1170.53", [_repeal_row("714.16", "2019-07-01")])
        self.run_cmd()
        self.assertTrue(
            CaseResearchNote.objects.filter(
                node=self.code_section, kind="act_supersession"
            ).exists()
        )

    def test_vetoed_repeal_is_not_noted(self):
        row = _repeal_row("714.16", "2026-07-01")
        row["gov_action"] = "Vetoed"
        _act_section("2024.1170.53", [row])
        self.run_cmd()
        self.assertFalse(
            CaseResearchNote.objects.filter(kind="act_supersession").exists()
        )

    def test_note_surfaces_in_tool_results_and_outranks_construction(self):
        from django.utils import timezone as tz

        from apps.corpus.services.corpus_tools import lookup_citation_tool

        CaseResearchNote.objects.create(
            node=self.code_section, kind="construction",
            status="adverse", evidence="SCOPE: narrow reading.",
            model="manual", checked_at=tz.now(),
        )
        _act_section("2024.1170.53", [_repeal_row("714.16", "2026-07-01")])
        self.run_cmd()
        out = lookup_citation_tool("714.16")
        self.assertIn(
            "REPEALED BY SESSION LAW", out["section"]["node"]["research_note"]
        )
