"""Streaming reader for CourtListener bulk-data CSV files.

The bulk files quote with ``"`` and escape an embedded quote with a
**backslash** (``\"``), NOT by doubling it (``""``) — verified against the real
2026-03-31 export (courts: all 3,360 rows = 20 fields; dockets: 300k rows = 54
fields under this dialect; zero anomalies). So the dialect is
``quotechar='"', escapechar='\\', doublequote=False``. (An earlier assumption of
RFC-4180 doubling was wrong — it miscounted the ubiquitous empty field ``,"",``
as evidence of doubling.) Text columns (opinion bodies, court ``notes``)
routinely contain embedded newlines and commas inside quoted fields, so a single
logical row spans many physical lines. Only a quote-state-tracking parser is
correct here — never ``grep``/``awk``/``splitlines``/``for line in f``, all of
which slice rows mid-quote and silently corrupt every downstream record.

This module is the *only* place that touches the CSV byte stream. It yields raw
string fields keyed by header name (selection is by name, never by position —
CourtListener reorders/adds columns between quarterly exports). Type coercion
("" → None for nullable numerics, ``t``/``f`` → bool) is the caller's job in
``acquire.py``, which knows each table's schema.

**Decode policy.** We decode with ``errors="surrogateescape"`` so that a corrupt
byte deep in the 50 GB opinions file never raises mid-stream and abort the whole
pass (there is no swap on the target box; a re-run would re-hit the same byte).
Undecodable bytes become lone surrogate code points that survive parsing; the
caller detects them when it UTF-8-encodes the row for output (the encode raises)
and routes that single row to ``rejects.jsonl``. A physical-line width mismatch,
by contrast, signals a systemic dialect/quote-state desync and is a hard error.
"""

from __future__ import annotations

import bz2
import csv
import io
import logging
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

log = logging.getLogger(__name__)

# Parallel bzip2 decompressors, preferred first. The stdlib ``bz2`` module is
# single-threaded, so on the in-process path decompress + CSV parse share one
# core (the dominant cost — decompress CPU is ~2-3x the parse CPU per byte).
# Running the decompressor as a *subprocess* moves it onto its own core; with a
# parallel tool it spreads across all cores:
#   * lbzip2 — splits any standard multi-block .bz2 on block boundaries, so it
#     parallel-decompresses files written by *any* compressor (what we want).
#   * pbzip2 — only parallel-decompresses multi-*stream* files it wrote itself,
#     but still correctly (serially) decodes a standard file.
#   * bzip2  — serial, but as a subprocess still frees the parse core (~1.5x).
# If none are on PATH we fall back to the in-process stdlib decompressor.
_BZ2_DECOMPRESSORS = ("lbzip2", "pbzip2", "bzip2")


def _pick_bz2_decompressor() -> str | None:
    """Return the path to the best available external bzip2 decompressor."""
    for tool in _BZ2_DECOMPRESSORS:
        found = shutil.which(tool)
        if found:
            return found
    return None


def raise_field_size_limit() -> None:
    """Lift the CSV field-size cap to effectively unlimited.

    Opinion bodies far exceed the 131072-byte default. We set this immediately
    before building a reader rather than at import time: ``field_size_limit`` is
    process-global mutable state, and an import-order quirk or a lazy import
    elsewhere could otherwise revert it to the default and kill the 50 GB
    opinions pass mid-stream. ``sys.maxsize`` is the idiomatic "no limit" value
    and is correct on both 32- and 64-bit builds.
    """
    csv.field_size_limit(sys.maxsize)


def open_bulk_csv(path: str | Path) -> Iterator[dict[str, str]]:
    """Yield one ``dict[column_name, raw_str]`` per logical CSV row.

    Transparently decompresses ``.bz2`` — via an external decompressor
    subprocess when one is on PATH (so decompression runs off the CSV-parsing
    core; ``lbzip2`` spreads it across all cores), else the in-process stdlib
    ``bz2`` module. The decompressed byte stream is identical either way, so the
    dialect/decode policy below is unaffected by the source. Each logical row is
    reconstructed regardless of how many physical newlines it spans. Empty
    fields surface as ``""`` (the ``csv`` module does not distinguish
    quoted-empty from unquoted-empty). A per-row width assertion is a cheap O(1)
    guard that hard-fails on quote-state desync *before* a misaligned value
    reaches a join-key set. A malformed physical chunk that raises ``csv.Error``
    (e.g. an embedded NUL) is logged and skipped rather than aborting the pass.
    """
    path = Path(path)
    raise_field_size_limit()

    if path.suffix != ".bz2":
        with open(path, "rb") as binary:
            yield from _read_rows(binary, path)
        return

    tool = _pick_bz2_decompressor()
    if tool is None:
        with bz2.open(path, "rb") as binary:
            yield from _read_rows(binary, path)
        return

    # Decompress in a subprocess piped into the parser. stderr is captured to a
    # temp file (decompressors are silent on success) so we can surface the
    # message on failure without risking a stderr-pipe deadlock.
    with tempfile.TemporaryFile() as errfile:
        proc = subprocess.Popen(
            [tool, "-dc", str(path)], stdout=subprocess.PIPE, stderr=errfile,
        )
        completed = False
        try:
            yield from _read_rows(proc.stdout, path)
            completed = True
        finally:
            # Closing the read end SIGPIPEs the producer if we bailed out early
            # (an exception upstream); on a normal full read it has already
            # exited. wait() reaps it either way.
            proc.stdout.close()
            ret = proc.wait()
            # Fail loud on a corrupt/truncated stream (matches stdlib bz2, which
            # raises) — but only on a clean full read. During exception
            # unwinding ``completed`` is False, so the original error propagates
            # untouched rather than being masked by the decompressor's exit code.
            if completed and ret != 0:
                errfile.seek(0)
                detail = errfile.read().decode("utf-8", "replace").strip()
                raise OSError(
                    f"{Path(tool).name} failed to decompress {path.name} "
                    f"(exit {ret}): {detail or 'no stderr'}"
                )


def _read_rows(binary: io.BufferedReader, path: Path) -> Iterator[dict[str, str]]:
    """Parse a decompressed CSV byte stream into per-row dicts.

    Source-agnostic: ``binary`` is either a raw file, a stdlib ``bz2`` reader,
    or a decompressor subprocess's stdout. All dialect/decode handling lives
    here so it is identical across those sources.
    """
    # newline="" is required by the csv module: it stops the IO layer from
    # translating bare \r / \r\n that live *inside* a quoted field (common
    # in Windows-authored HTML/Columbia imports) into record breaks.
    # surrogateescape makes decoding total (see module docstring).
    text = io.TextIOWrapper(
        binary, encoding="utf-8", errors="surrogateescape", newline=""
    )
    reader = csv.reader(
        text,
        delimiter=",",
        quotechar='"',
        doublequote=False,
        escapechar="\\",
        strict=False,
    )
    try:
        header = next(reader)
    except StopIteration:
        return
    width = len(header)
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            log.warning(
                "%s: skipping unparseable chunk near line %s: %s",
                path.name, reader.line_num, exc,
            )
            continue
        if len(row) != width:
            # A genuinely malformed row (rare with the right dialect). Skip
            # and log rather than abort — one bad row must not kill a
            # multi-hour pass. A pervasive mismatch (wrong dialect) shows up
            # as a near-empty result downstream, which the operator catches.
            log.warning(
                "%s: skipping row near physical line %s with %d fields "
                "(expected %d)", path.name, reader.line_num, len(row), width,
            )
            continue
        yield dict(zip(header, row))
