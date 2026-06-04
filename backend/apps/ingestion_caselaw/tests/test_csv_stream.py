"""Golden tests for the CourtListener bulk CSV streaming reader.

Fixtures are written as RAW bytes in CourtListener's real dialect — quotes
escaped with a backslash (``\\"``), not doubled — because that is what the live
2026-03-31 export uses. (Do NOT use ``csv.writer`` here: it emits doubled
quotes, the wrong dialect, which is exactly the bug that slipped through before.)
"""

from __future__ import annotations

import bz2
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from ..csv_stream import open_bulk_csv

# Raw file content in the CL dialect. Note the embedded newline (row 1), the
# backslash-escaped quotes (row 2), the embedded comma (row 3), the empty quoted
# field (row 4), a 200k-char field (row 5, past the 131072 default), and an
# escaped literal backslash ``\\`` -> ``\`` (row 6).
CONTENT = (
    "a,b,c\n"
    '1,"line one\nline two",x\n'
    '2,"she said \\"hi\\"",y\n'
    '3,"a, b",z\n'
    '4,"",w\n'
    f'5,"{"A" * 200000}",v\n'
    '6,"C:\\\\d",u\n'
)


class OpenBulkCsvTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_parses_cl_dialect_keyed_by_header(self):
        path = self.tmp / "plain.csv"
        path.write_text(CONTENT, encoding="utf-8")
        out = list(open_bulk_csv(path))

        self.assertEqual(len(out), 6)
        self.assertEqual(out[0]["b"], "line one\nline two")   # embedded newline
        self.assertEqual(out[1]["b"], 'she said "hi"')        # \" -> "
        self.assertEqual(out[2]["b"], "a, b")                 # embedded comma
        self.assertEqual(out[3]["b"], "")                     # empty quoted field
        self.assertEqual(len(out[4]["b"]), 200000)            # oversized field
        self.assertEqual(out[5]["b"], "C:\\d")               # \\ -> \
        self.assertEqual(set(out[0]), {"a", "b", "c"})

    def test_bz2_round_trips(self):
        path = self.tmp / "data.csv.bz2"
        path.write_bytes(bz2.compress(CONTENT.encode("utf-8")))
        out = list(open_bulk_csv(path))
        self.assertEqual(len(out), 6)
        self.assertEqual(out[1]["b"], 'she said "hi"')

    def test_width_mismatch_is_skipped_not_fatal(self):
        # A malformed physical row (extra field) is skipped; good rows survive.
        path = self.tmp / "bad.csv"
        path.write_text("a,b,c\n1,2,3,4\n5,6,7\n", encoding="utf-8")
        out = list(open_bulk_csv(path))
        self.assertEqual(out, [{"a": "5", "b": "6", "c": "7"}])

    def test_empty_file_yields_nothing(self):
        path = self.tmp / "empty.csv"
        path.write_text("", encoding="utf-8")
        self.assertEqual(list(open_bulk_csv(path)), [])
