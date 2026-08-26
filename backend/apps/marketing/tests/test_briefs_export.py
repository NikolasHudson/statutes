"""End-to-end export of brief 001 against a tiny synthetic corpus.

Three decisions, a handful of citation edges, and the command run for real
into a temp directory — covering the ranking queries (opinion→opinion graph
grouped by parent decision; distinct-version counting of federal cites), the
snapshot schema, determinism, and the fail-loudly path when a federal cite
has no SCOTUS_CASES entry.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.api.tests._factories import make_caselaw_case
from apps.corpus.models import CrossReference, CrossReferenceKind


def _graph_edge(from_version, to_opinion):
    return CrossReference.objects.create(
        from_version=from_version,
        to_node=to_opinion,
        kind=CrossReferenceKind.INTERNAL,
        source="caselaw_graph",
    )


def _link_edge(from_version, text):
    return CrossReference.objects.create(
        from_version=from_version,
        to_node=None,
        external_text=text,
        kind=CrossReferenceKind.EXTERNAL,
        source="caselaw_link",
    )


class ExportDataBriefTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dec_a, cls.op_a, cls.v_a = make_caselaw_case(
            cl_cluster_id=1,
            cl_opinion_id=11,
            case_name="In the Interest of T.T., Minor Child",
            date_filed="2015-03-02",
        )
        cls.dec_b, cls.op_b, cls.v_b = make_caselaw_case(
            cl_cluster_id=2,
            cl_opinion_id=22,
            court_id="iowactapp",
            case_name="State of Iowa v. John Smith Jr.",
            date_filed="2018-06-11",
        )
        cls.dec_c, cls.op_c, cls.v_c = make_caselaw_case(
            cl_cluster_id=3,
            cl_opinion_id=33,
            case_name="Hyler v. Garner",
            date_filed="1996-09-18",
        )
        # A is cited by B and C; B is cited by C; C by nobody.
        _graph_edge(cls.v_b, cls.op_a)
        _graph_edge(cls.v_c, cls.op_a)
        _graph_edge(cls.v_c, cls.op_b)
        # Strickland: two rows from B (full cite + pincite) must count B
        # once; C's pincite makes two distinct citing opinions in total.
        _link_edge(cls.v_b, "466 U.S. 668")
        _link_edge(cls.v_b, "466 U.S. 668, 687")
        _link_edge(cls.v_c, "466 U.S. 668, 700")
        # Miranda from C only.
        _link_edge(cls.v_c, "384 U.S. 436")
        # An at-cite must not count at all.
        _link_edge(cls.v_c, "466 U.S. at 687")

    def _export(self, out):
        call_command(
            "export_data_brief", "most_cited_cases", "--out", out, "--as-of", "2026-08-13"
        )
        return json.loads((Path(out) / "most-cited-cases.json").read_text())

    def test_snapshot_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = self._export(tmp)

        self.assertEqual(snap["slug"], "most-cited-cases")
        self.assertEqual(snap["brief_no"], 1)
        self.assertEqual(snap["as_of"], "2026-08-13")
        self.assertEqual(snap["totals"], {"edges": 3, "decisions": 3})

        fig1, fig2 = snap["figures"]
        self.assertEqual(fig1["id"], "iowa-fifty")
        self.assertEqual(fig1["viewbox"], [1000, 660])
        self.assertEqual(
            [(b["rank"], b["name"], b["cites"], b["cat"]) for b in fig1["bubbles"]],
            [(1, "In re T.T.", 2, "family"), (2, "State v. Smith", 1, "criminal")],
        )
        top = fig1["bubbles"][0]
        self.assertEqual(top["full"], "In the Interest of T.T., Minor Child")
        self.assertEqual(top["year"], "2015")
        self.assertEqual(top["court"], "Iowa Supreme Court")
        self.assertEqual(fig1["bubbles"][1]["court"], "Iowa Court of Appeals")
        for b in fig1["bubbles"]:
            self.assertGreater(b["r"], 0)
            self.assertIsInstance(b["label"], list)

        self.assertEqual(fig2["id"], "scotus-thirty")
        self.assertEqual(
            [(b["name"], b["full"], b["year"], b["cites"], b["cat"]) for b in fig2["bubbles"]],
            [
                ("Strickland v. Washington", "466 U.S. 668", "1984", 2, "counsel"),
                ("Miranda v. Arizona", "384 U.S. 436", "1966", 1, "police"),
            ],
        )

    def test_reruns_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._export(tmp)
            first = (Path(tmp) / "most-cited-cases.json").read_bytes()
            self._export(tmp)
            second = (Path(tmp) / "most-cited-cases.json").read_bytes()
        self.assertEqual(first, second)

    def test_unknown_scotus_cite_fails_loudly(self):
        # A refresh that promotes an unmapped case must stop the export,
        # not publish a nameless bubble.
        _link_edge(self.v_a, "999 U.S. 1")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesMessage(CommandError, "999 U.S. 1"):
                self._export(tmp)

    def test_bad_as_of_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError):
                call_command(
                    "export_data_brief", "most_cited_cases", "--out", tmp, "--as-of", "13/08/2026"
                )
