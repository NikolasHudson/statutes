"""Phase 1 — Acquire/Filter.

Reduce the ~50 GB national CourtListener bulk-data dump to a small Iowa-only
JSONL slice that Phases 2–3 turn into corpus rows. This module does the
**memory-bounded streaming join** and emits JSONL artifacts; it is read-only
relative to the corpus DB. A thin persistence helper records one
``RawIngestion`` row per payload artifact (hashing each file in chunks, never
loading a multi-GB artifact into memory) and one acquire ``IngestionRun``.

Join path (the only one — there is no court_id on opinion or cluster):

    opinion.cluster_id → opinioncluster.id
    opinioncluster.docket_id → docket.id
    docket.court_id → court.id

Only integer key-sets live in RAM. ``iowa_docket_court`` maps docket id → its
court id (one of two interned literals, so the dict is ~a set in size);
``iowa_cluster_ids`` is a plain int set. Full rows, text bodies and the
unbounded ``docket_number`` strings are streamed straight to disk and never
accumulate.

A bad row (undecodable bytes surfacing as a UTF-8 encode error, an empty
NOT-NULL integer key, a missing column) is routed to a ``rejects.jsonl`` sidecar
and the pass continues — one poison row never aborts the 50 GB opinions pass.
See ``Case Law/CASELAW_PHASE1_ACQUIRE_SPEC.md``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .csv_stream import open_bulk_csv

log = logging.getLogger(__name__)

# CourtListener search_court.id slugs for the two Iowa state appellate courts.
IOWA_COURT_IDS = ("iowa", "iowactapp")

# Bulk-file name prefixes → logical table. Files are named e.g.
# "opinion-clusters-2026-03-31.csv.bz2"; resolution is by prefix + extension.
_FILE_PREFIXES = {
    "courts": "courts",
    "dockets": "dockets",
    "clusters": "opinion-clusters",
    "citations": "citations",
    "opinions": "opinions",
}

# Payload artifacts that become RawIngestion rows (rejects.jsonl is audit-only).
_ARTIFACTS = ("clusters", "opinions", "citations", "dockets")
_ARTIFACT_SOURCE_KIND = {
    "clusters": "cl_bulk_clusters",
    "opinions": "cl_bulk_opinions",
    "citations": "cl_bulk_citations",
    "dockets": "cl_bulk_dockets",
}

# Errors that mark a single row bad → route to rejects.jsonl and continue.
#   ValueError         – empty/garbage NOT-NULL integer key (e.g. _to_int(""))
#   KeyError           – an expected column is absent from this file's header
#   UnicodeEncodeError – a field carried undecodable bytes (lone surrogates)
_ROW_ERRORS = (ValueError, KeyError, UnicodeEncodeError)


@dataclass
class AcquireResult:
    """Summary of one acquire pass."""

    out_dir: Path
    courts: tuple[str, ...]
    artifact_paths: dict[str, Path] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

def _to_bool(value: str) -> bool | None:
    """PostgreSQL COPY exports booleans as t/f (occasionally true/false)."""
    if value in ("t", "true", "True"):
        return True
    if value in ("f", "false", "False"):
        return False
    return None  # empty / unexpected → null rather than a wrong default


def _to_int_or_none(value: str) -> int | None:
    return int(value) if value != "" else None


def _to_int(value: str) -> int:
    """For NOT-NULL integer join keys; raises ValueError on empty/garbage so the
    row is routed to rejects.jsonl (an empty NOT-NULL key is a data error)."""
    return int(value)


def _dumps(obj: dict) -> str:
    """Pinned, byte-stable JSONL serialization: compact, UTF-8, and explicit
    key order. ``sort_keys=False`` is set deliberately — byte-stability comes
    from the fixed field order in each ``_*_record`` builder, NOT from sorting,
    so two runs over the same input produce byte-identical artifacts that the
    RawIngestion content-hash can dedupe across quarters."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


# ---------------------------------------------------------------------------
# Per-artifact record builders (explicit, fixed field order)
# ---------------------------------------------------------------------------

def _docket_record(row: dict[str, str]) -> dict:
    return {
        "docket_id": _to_int(row["id"]),
        "court_id": row["court_id"],
        "docket_number": row["docket_number"],
    }


def _cluster_record(row: dict[str, str], court_id: str, court_name: str) -> dict:
    cid = _to_int(row["id"])
    return {
        "cl_cluster_id": cid,
        "node_path": f"cl-cluster-{cid}",
        "docket_id": _to_int(row["docket_id"]),
        "court_id": court_id,
        "court_name": court_name,
        "case_name": row["case_name"],
        "case_name_short": row["case_name_short"],
        "case_name_full": row["case_name_full"],
        "date_filed": row["date_filed"],
        "precedential_status": row["precedential_status"],
        "judges": row["judges"],
        "citation_count": _to_int_or_none(row["citation_count"]),
        "scdb_id": row["scdb_id"],
        "slug": row["slug"],
        "syllabus": row["syllabus"],
        "headnotes": row["headnotes"],
        "summary": row["summary"],
        "disposition": row["disposition"],
        "posture": row["posture"],
        "nature_of_suit": row["nature_of_suit"],
    }


def _opinion_record(row: dict[str, str]) -> dict:
    cluster_id = _to_int(row["cluster_id"])
    op_id = _to_int(row["id"])
    return {
        "cl_opinion_id": op_id,
        "cl_cluster_id": cluster_id,
        "node_path": f"cl-cluster-{cluster_id}/op-{op_id}",
        "type": row["type"],
        "author_str": row["author_str"],
        "author_id": _to_int_or_none(row["author_id"]),
        "per_curiam": _to_bool(row["per_curiam"]),
        "joined_by_str": row["joined_by_str"],
        "page_count": _to_int_or_none(row["page_count"]),
        "download_url": row["download_url"],
        "extracted_by_ocr": _to_bool(row["extracted_by_ocr"]),
        "sha1": row["sha1"],
        "plain_text": row["plain_text"],
        "html": row["html"],
        "html_lawbox": row["html_lawbox"],
        "html_columbia": row["html_columbia"],
        "html_anon_2020": row["html_anon_2020"],
        "xml_harvard": row["xml_harvard"],
        "html_with_citations": row["html_with_citations"],
    }


def _citation_record(row: dict[str, str]) -> dict:
    return {
        "cl_citation_id": _to_int(row["id"]),
        "cl_cluster_id": _to_int(row["cluster_id"]),
        "volume": row["volume"],
        "reporter": row["reporter"],
        "page": row["page"],
        # search_citation.type is nullable in the real CL export (citations
        # predating the type taxonomy). Emit null rather than rejecting a valid
        # citation; Phase 2 tolerates a null type.
        "type": _to_int_or_none(row["type"]),
    }


# ---------------------------------------------------------------------------
# Input resolution + atomic JSONL writing
# ---------------------------------------------------------------------------

def _resolve_inputs(bulk_dir: Path) -> dict[str, Path]:
    """Map each logical table to its file in ``bulk_dir`` (``.csv.bz2`` or
    ``.csv``), erroring on a missing or ambiguous match."""
    resolved: dict[str, Path] = {}
    for key, prefix in _FILE_PREFIXES.items():
        matches = sorted(bulk_dir.glob(f"{prefix}*.csv.bz2")) + sorted(
            bulk_dir.glob(f"{prefix}*.csv")
        )
        if not matches:
            raise FileNotFoundError(
                f"no bulk file for '{key}' (prefix '{prefix}') in {bulk_dir}"
            )
        if len(matches) > 1:
            raise FileNotFoundError(
                f"ambiguous bulk files for '{key}' in {bulk_dir}: "
                f"{[m.name for m in matches]}"
            )
        resolved[key] = matches[0]
    return resolved


class _AtomicJsonlWriter:
    """Write JSONL to ``<name>.jsonl.partial`` then ``os.replace`` to its final
    name on clean commit — a consumer never sees a half-written artifact.

    Binary mode: each record is fully serialized and UTF-8 encoded *before* the
    single ``write`` call, so a field carrying undecodable bytes raises
    ``UnicodeEncodeError`` here (caught by the caller and routed to rejects)
    without ever leaving a partial line on disk.
    """

    def __init__(self, final_path: Path):
        self.final_path = final_path
        self.partial_path = final_path.with_suffix(final_path.suffix + ".partial")
        self.count = 0
        self._fh = None
        self._fh = self.partial_path.open("wb")

    def write(self, record: dict) -> None:
        data = (_dumps(record) + "\n").encode("utf-8")
        self._fh.write(data)
        self.count += 1

    def commit(self) -> None:
        if self._fh is None:
            return
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._fh.close()
        os.replace(self.partial_path, self.final_path)

    def abort(self) -> None:
        if self._fh is not None:
            self._fh.close()
        self.partial_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# The five-pass streaming join
# ---------------------------------------------------------------------------

def run_acquire(
    bulk_dir: str | Path,
    out_dir: str | Path,
    courts: tuple[str, ...] = IOWA_COURT_IDS,
) -> AcquireResult:
    """Stream the five bulk CSVs and emit the Iowa JSONL slice into ``out_dir``.

    Read-only relative to the corpus DB; pure file I/O. Rerunnable: artifacts
    are written atomically and identical input yields byte-identical output.
    Each payload artifact is committed as soon as its pass finishes, so a crash
    during a later pass keeps the already-finished artifacts on disk.
    """
    bulk_dir = Path(bulk_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = _resolve_inputs(bulk_dir)
    court_set = set(courts)

    result = AcquireResult(out_dir=out_dir, courts=tuple(courts))

    # rejects.jsonl spans all passes; commit it last. Track still-open writers
    # so a crash aborts only the uncommitted ones (committed artifacts persist).
    rejects_w = _AtomicJsonlWriter(out_dir / "rejects.jsonl")
    open_writers: list[_AtomicJsonlWriter] = [rejects_w]

    def reject(artifact: str, row: dict, exc: BaseException) -> None:
        # repr(row) is ASCII-safe even when fields carry lone surrogates.
        rejects_w.write({
            "artifact": artifact,
            "error": f"{type(exc).__name__}: {exc}",
            "row_repr": repr(row),
        })

    def _finish(name: str, writer: _AtomicJsonlWriter) -> None:
        writer.commit()
        open_writers.remove(writer)
        result.artifact_paths[name] = writer.final_path
        result.counts[name] = writer.count

    try:
        # Pass 1 — courts (~80 kB): capture display names, assert targets exist.
        court_name_by_id: dict[str, str] = {}
        for row in open_bulk_csv(inputs["courts"]):
            if row["id"] in court_set:
                court_name_by_id[row["id"]] = row["full_name"]
        missing = court_set - court_name_by_id.keys()
        if missing:
            raise ValueError(f"court id(s) not found in courts file: {sorted(missing)}")

        # Pass 2 — dockets (~4.6 GB): keep Iowa dockets. Hold docket_id→court_id
        # (court_id interned: two distinct values) in RAM; stream docket_number
        # (unbounded free text) straight to dockets.jsonl, never into RAM.
        iowa_docket_court: dict[int, str] = {}
        dockets_w = _AtomicJsonlWriter(out_dir / "dockets.jsonl")
        open_writers.append(dockets_w)
        for row in open_bulk_csv(inputs["dockets"]):
            try:
                if row["court_id"] in court_set:
                    did = _to_int(row["id"])
                    iowa_docket_court[did] = sys.intern(row["court_id"])
                    dockets_w.write(_docket_record(row))
            except _ROW_ERRORS as exc:
                reject("dockets", row, exc)
        _finish("dockets", dockets_w)

        # Pass 3 — opinion-clusters (~2.3 GB): keep clusters on Iowa dockets.
        iowa_cluster_ids: set[int] = set()
        clusters_w = _AtomicJsonlWriter(out_dir / "clusters.jsonl")
        open_writers.append(clusters_w)
        for row in open_bulk_csv(inputs["clusters"]):
            try:
                court_id = iowa_docket_court.get(_to_int(row["docket_id"]))
                if court_id is not None:
                    clusters_w.write(
                        _cluster_record(row, court_id, court_name_by_id[court_id])
                    )
                    iowa_cluster_ids.add(_to_int(row["id"]))
            except _ROW_ERRORS as exc:
                reject("clusters", row, exc)
        _finish("clusters", clusters_w)

        # Pass 4 — citations (~120 MB): keep cites attached to Iowa clusters.
        citations_w = _AtomicJsonlWriter(out_dir / "citations.jsonl")
        open_writers.append(citations_w)
        for row in open_bulk_csv(inputs["citations"]):
            try:
                if _to_int(row["cluster_id"]) in iowa_cluster_ids:
                    citations_w.write(_citation_record(row))
            except _ROW_ERRORS as exc:
                reject("citations", row, exc)
        _finish("citations", citations_w)

        # Pass 5 — opinions (~50 GB, last): keep opinions on Iowa clusters. One
        # row at a time; text carried verbatim (Phase 2 picks the body + strips).
        opinions_w = _AtomicJsonlWriter(out_dir / "opinions.jsonl")
        open_writers.append(opinions_w)
        for row in open_bulk_csv(inputs["opinions"]):
            try:
                if _to_int(row["cluster_id"]) in iowa_cluster_ids:
                    opinions_w.write(_opinion_record(row))
            except _ROW_ERRORS as exc:
                reject("opinions", row, exc)
        _finish("opinions", opinions_w)

        _finish("rejects", rejects_w)
    except BaseException:
        for w in open_writers:
            w.abort()
        raise

    log.info("acquire complete: %s", result.counts)
    return result


# ---------------------------------------------------------------------------
# Audit persistence (DB) — chunked hashing, hard-linked <hash>.bin storage
# ---------------------------------------------------------------------------

def _sha256_file(path: Path, chunk: int = 1 << 20) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
            size += len(block)
    return h.hexdigest(), size


def persist_raw_artifact(*, path: Path, source_kind: str, export_year: int,
                         storage_dir: Path, fetched_from: str = "", notes: str = ""):
    """Record one JSONL artifact as a ``RawIngestion`` row.

    Hashes the file in 1 MiB chunks (never loading it whole) and snapshots the
    exact bytes at ``<storage_dir>/<content_hash>.bin`` via a **hard link** —
    same inode, so no disk doubling even for a multi-GB artifact, and the
    snapshot is immutable even after a later run overwrites the run-dir file
    in place. Falls back to a copy across filesystems. Dedupes by content_hash.
    """
    from .models import RawIngestion

    content_hash, byte_size = _sha256_file(path)
    existing = RawIngestion.objects.filter(content_hash=content_hash).first()
    if existing is not None:
        return existing

    storage_dir = Path(storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / f"{content_hash}.bin"
    if not target.exists():
        try:
            os.link(path, target)  # hard link (same filesystem): no copy
        except OSError:
            shutil.copyfile(path, target)  # cross-device fallback

    return RawIngestion.objects.create(
        source_kind=source_kind,
        code_year=export_year,
        fetched_from=fetched_from,
        content_hash=content_hash,
        byte_size=byte_size,
        storage_path=str(target),
        notes=notes,
    )


def persist_acquire_run(result: AcquireResult, *, export_year: int,
                        fetched_from: str = "", storage_dir: Path | None = None):
    """Persist one ``RawIngestion`` per payload artifact and a single acquire
    ``IngestionRun`` summarising the slice. ``rejects.jsonl`` is audit-only and
    is recorded in the run log, not as a RawIngestion. Returns the run."""
    from django.conf import settings
    from django.utils import timezone

    from .models import IngestionRun

    if storage_dir is None:
        storage_dir = Path(settings.BASE_DIR) / "data" / "raw"

    raws = {}
    for key in _ARTIFACTS:
        path = result.artifact_paths.get(key)
        if path is None:
            continue
        raws[key] = persist_raw_artifact(
            path=path,
            source_kind=_ARTIFACT_SOURCE_KIND[key],
            export_year=export_year,
            storage_dir=storage_dir,
            fetched_from=fetched_from,
            notes=f"acquire {key}: {result.counts.get(key, 0)} records",
        )
    run = IngestionRun.objects.create(
        raw=None,  # an acquire run spans several artifacts; hashes recorded in log
        phase="acquire",
        status="pending",
        finished_at=timezone.now(),
        log=json.dumps(
            {
                "courts": list(result.courts),
                "counts": result.counts,  # includes the rejects count
                "artifacts": {k: r.content_hash for k, r in raws.items()},
            }
        ),
    )
    return run
