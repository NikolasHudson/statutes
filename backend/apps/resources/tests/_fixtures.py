"""Fixture helpers for the resources tests. No network, ever.

``sos_sample.csv`` / ``.zip`` are 12 loadable rows plus one with a blank
``corp_number``, written with the same quoting the real extract uses (the
``THE WOOD DOCTOR, L. C.`` row really does arrive wrapped in doubled quotes).
Variants are derived in a temp directory so the checked-in fixture stays the
single description of the source's shape.
"""

from __future__ import annotations

import csv
import io
import pathlib
import zipfile

DATA = pathlib.Path(__file__).parent / "data"
SAMPLE_CSV = DATA / "sos_sample.csv"
SAMPLE_ZIP = DATA / "sos_sample.zip"

# Rows in the fixture that a load actually writes (the 13th has no key).
SAMPLE_ROWS = 12


def read_sample() -> tuple[list[str], list[dict[str, str]]]:
    with SAMPLE_CSV.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path, header: list[str], rows: list[dict[str, str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    pathlib.Path(path).write_text("﻿" + buf.getvalue(), encoding="utf-8")
    return str(path)


def write_zip(path, header: list[str], rows: list[dict[str, str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("rows.csv", "﻿" + buf.getvalue())
    return str(path)
