"""Shared sync machinery for resources datasets.

One pass over a published file, loaded through a staging table, applied to the
live table in a single transaction. The shape is the same for every dataset we
expect to add (a portal publishes a full current-state extract; we diff it
against what we hold), so the download, integrity, safety and bookkeeping
legs live here and each dataset supplies only its columns and its SQL.

The three things this file exists to get right:

* **Never hold the file in memory.** The SOS extract is ~101 MB zipped; it is
  streamed to a temp file, hashed on the way past, and streamed again through
  ``COPY`` into a staging table.
* **Never half-apply.** Staging load, safety gate and the live-table write all
  run inside one transaction, so an abort leaves the previous load standing.
* **Never delete.** Sources publish current state; rows that vanish are marked
  inactive with a date. That accumulated history is the only record of when an
  entity stopped being listed, and it cannot be rebuilt after the fact.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import hashlib
import io
import logging
import os
import tempfile
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from typing import IO

import requests
from django.db import connection, transaction
from django.utils import timezone

from .models import Dataset, Snapshot, SnapshotStatus

logger = logging.getLogger(__name__)

# Advisory-lock namespace for this app. The pair (namespace, dataset id) is the
# real mutex between two syncs of the same dataset — the "is one already
# running?" row check below only catches the tidy cases.
ADVISORY_LOCK_NAMESPACE = 7734

# A snapshot still marked `running` after this long is treated as a crashed
# process, not a live one, and does not block a new run.
STALE_RUNNING_AFTER = dt.timedelta(hours=2)

DOWNLOAD_TIMEOUT = (30, 300)  # (connect, read) seconds
DOWNLOAD_RETRIES = 3
DOWNLOAD_CHUNK = 1 << 20  # 1 MiB

# Safety gate (§4.4 step 6). A source that publishes a truncated file must not
# quietly wipe 90% of the table; --force is the deliberate override.
MIN_ROWS_FRACTION = 0.90
MAX_DEACTIVATED_FRACTION = 0.10


class SyncAborted(Exception):
    """Refused before touching the live table. Not a bug — a guard firing."""


class _Rollback(Exception):
    """Internal: unwind the apply transaction for --dry-run."""


@dataclasses.dataclass
class SyncResult:
    status: str
    snapshot_id: int
    row_count: int = 0
    inserted: int = 0
    updated: int = 0
    deactivated: int = 0
    reactivated: int = 0
    rejected: int = 0
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (SnapshotStatus.OK, SnapshotStatus.SKIPPED)


@contextmanager
def advisory_lock(dataset_id: int) -> Iterator[bool]:
    """Session-level Postgres advisory lock, released on the way out.

    Session-level rather than transaction-level on purpose: the lock has to
    span the download, which is deliberately outside any transaction.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT pg_try_advisory_lock(%s, %s)",
            [ADVISORY_LOCK_NAMESPACE, dataset_id],
        )
        acquired = bool(cur.fetchone()[0])
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_unlock(%s, %s)",
                    [ADVISORY_LOCK_NAMESPACE, dataset_id],
                )


def _parse_http_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class BaseSync:
    """Subclass per dataset. Everything below the hooks is shared."""

    # --- identity ---------------------------------------------------------
    slug: str = ""
    source_url: str = ""

    # --- file shape -------------------------------------------------------
    # The source ships UTF-8 with a BOM; utf-8-sig eats it so the first column
    # name does not arrive as "﻿corp_number".
    encoding: str = "utf-8-sig"
    expected_columns: tuple[str, ...] = ()
    # Columns we know about and deliberately do not store. Listed so that a
    # genuinely new column in the source still stands out in the run log.
    ignored_columns: tuple[str, ...] = ()

    # --- staging ----------------------------------------------------------
    staging_table: str = ""
    staging_ddl: str = ""
    staging_columns: tuple[str, ...] = ()
    staging_key: str = ""

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def map_row(self, row: dict[str, str]) -> tuple | None:
        """CSV row → one staging tuple, or None to reject the row."""
        raise NotImplementedError

    def plan_counts(self, cur, today: dt.date) -> dict[str, int]:
        """What applying staging would do, without doing it."""
        raise NotImplementedError

    def apply(self, cur, snapshot: Snapshot, today: dt.date) -> None:
        """Upsert staging into the live table and deactivate absentees."""
        raise NotImplementedError

    def live_active_count(self, cur) -> int:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        path: str | None = None,
        force: bool = False,
        dry_run: bool = False,
        log=logger.info,
    ) -> SyncResult:
        dataset = Dataset.objects.get(slug=self.slug)
        self._guard_concurrent_row(dataset)

        with advisory_lock(dataset.id) as acquired:
            if not acquired:
                raise SyncAborted(
                    f"another sync of '{self.slug}' holds the advisory lock"
                )
            snapshot = Snapshot.objects.create(dataset=dataset)
            try:
                return self._run_locked(
                    dataset, snapshot, path=path, force=force,
                    dry_run=dry_run, log=log,
                )
            except SyncAborted as exc:
                self._finish(snapshot, SnapshotStatus.ABORTED, message=str(exc))
                return SyncResult(
                    status=SnapshotStatus.ABORTED,
                    snapshot_id=snapshot.pk,
                    message=str(exc),
                )
            except Exception as exc:  # noqa: BLE001 — record, then re-raise
                self._finish(
                    snapshot, SnapshotStatus.FAILED, message=f"{type(exc).__name__}: {exc}"
                )
                raise

    def _run_locked(
        self, dataset: Dataset, snapshot: Snapshot, *, path, force, dry_run, log
    ) -> SyncResult:
        today = timezone.localdate()
        last_ok = dataset.latest_ok_snapshot()

        # 1. Cheap unchanged check, before spending 100 MB of transfer. The
        # portal regenerates the export behind a CDN, so last-modified moves
        # more often than the data does; a mismatch just means "download and
        # hash", which is the authoritative check.
        tmp_path = None
        if path is None:
            head_lm = self._head_last_modified()
            snapshot.source_last_modified = head_lm
            if (
                not force
                and head_lm is not None
                and last_ok is not None
                and last_ok.source_last_modified == head_lm
                and last_ok.file_sha256
            ):
                log(f"source unchanged since {head_lm.isoformat()} — skipping")
                self._finish(
                    snapshot,
                    SnapshotStatus.SKIPPED,
                    message="last-modified unchanged",
                    source_last_modified=head_lm,
                    file_sha256=last_ok.file_sha256,
                    file_bytes=last_ok.file_bytes,
                )
                return SyncResult(
                    status=SnapshotStatus.SKIPPED, snapshot_id=snapshot.pk
                )
            tmp_path, digest, size = self._download(log=log)
            source_file = tmp_path
        else:
            source_file = path
            digest, size = self._hash_file(path)
            snapshot.source_last_modified = dt.datetime.fromtimestamp(
                os.path.getmtime(path), tz=dt.timezone.utc
            )

        try:
            snapshot.file_sha256 = digest
            snapshot.file_bytes = size
            snapshot.save(
                update_fields=["source_last_modified", "file_sha256", "file_bytes"]
            )

            # 3. Byte-identical to the last good load — nothing to do.
            if not force and last_ok is not None and last_ok.file_sha256 == digest:
                log(f"file sha256 unchanged ({digest[:12]}…) — skipping")
                self._finish(
                    snapshot, SnapshotStatus.SKIPPED, message="file hash unchanged"
                )
                return SyncResult(
                    status=SnapshotStatus.SKIPPED, snapshot_id=snapshot.pk
                )

            return self._load_and_apply(
                source_file, snapshot, today, force=force, dry_run=dry_run, log=log
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _load_and_apply(
        self, source_file: str, snapshot: Snapshot, today: dt.date, *,
        force: bool, dry_run: bool, log,
    ) -> SyncResult:
        counts: dict[str, int] = {}
        loaded = {"rows": 0, "rejected": 0}
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {self.staging_table}")
                    cur.execute(self.staging_ddl)

                    rows, rejected = self._copy_into_staging(cur, source_file, log=log)
                    loaded["rows"], loaded["rejected"] = rows, rejected
                    if rows == 0:
                        raise SyncAborted("source file contained no usable rows")
                    cur.execute(
                        f"CREATE INDEX ON {self.staging_table} ({self.staging_key})"
                    )
                    cur.execute(f"ANALYZE {self.staging_table}")

                    counts = self.plan_counts(cur, today)
                    active_before = self.live_active_count(cur)
                    self._safety_gate(
                        active_before=active_before,
                        staged=counts["staged"],
                        deactivating=counts["deactivated"],
                        force=force,
                        log=log,
                    )

                    if dry_run:
                        log(
                            "dry run — would insert {inserted}, update {updated} "
                            "(of which {reactivated} reactivated), deactivate "
                            "{deactivated}".format(**counts)
                        )
                        raise _Rollback

                    self.apply(cur, snapshot, today)
        except _Rollback:
            self._finish(
                snapshot,
                SnapshotStatus.ABORTED,
                message="dry run — rolled back",
                row_count=loaded["rows"],
                **{k: counts.get(k, 0) for k in
                   ("inserted", "updated", "deactivated", "reactivated")},
            )
            return SyncResult(
                status=SnapshotStatus.ABORTED,
                snapshot_id=snapshot.pk,
                row_count=loaded["rows"],
                rejected=loaded["rejected"],
                message="dry run — rolled back",
                **{k: counts.get(k, 0) for k in
                   ("inserted", "updated", "deactivated", "reactivated")},
            )

        message = f"{loaded['rejected']} rows rejected" if loaded["rejected"] else ""
        self._finish(
            snapshot,
            SnapshotStatus.OK,
            message=message,
            row_count=loaded["rows"],
            **{k: counts[k] for k in
               ("inserted", "updated", "deactivated", "reactivated")},
        )
        return SyncResult(
            status=SnapshotStatus.OK,
            snapshot_id=snapshot.pk,
            row_count=loaded["rows"],
            rejected=loaded["rejected"],
            message=message,
            **{k: counts[k] for k in
               ("inserted", "updated", "deactivated", "reactivated")},
        )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _guard_concurrent_row(self, dataset: Dataset) -> None:
        cutoff = timezone.now() - STALE_RUNNING_AFTER
        if dataset.snapshots.filter(
            status=SnapshotStatus.RUNNING, started_at__gte=cutoff
        ).exists():
            raise SyncAborted(
                f"a sync of '{self.slug}' started less than "
                f"{STALE_RUNNING_AFTER} ago is still marked running"
            )

    def _head_last_modified(self) -> dt.datetime | None:
        try:
            resp = requests.head(
                self.source_url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True
            )
            resp.raise_for_status()
            return _parse_http_date(resp.headers.get("last-modified"))
        except requests.RequestException as exc:
            # Not fatal: the download below is the real check.
            logger.warning("HEAD %s failed: %s", self.source_url, exc)
            return None

    def _download(self, *, log) -> tuple[str, str, int]:
        """Stream the source to a temp file. Returns (path, sha256, bytes)."""
        last_exc: Exception | None = None
        for attempt in range(1, DOWNLOAD_RETRIES + 1):
            fd, tmp_path = tempfile.mkstemp(prefix=f"resources-{self.slug}-")
            os.close(fd)
            try:
                digest = hashlib.sha256()
                size = 0
                started = time.monotonic()
                with requests.get(
                    self.source_url, stream=True, timeout=DOWNLOAD_TIMEOUT
                ) as resp:
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as fh:
                        for chunk in resp.iter_content(DOWNLOAD_CHUNK):
                            if not chunk:
                                continue
                            fh.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                log(
                    f"downloaded {size / 1e6:.1f} MB in "
                    f"{time.monotonic() - started:.1f}s"
                )
                return tmp_path, digest.hexdigest(), size
            except requests.RequestException as exc:
                last_exc = exc
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                if attempt < DOWNLOAD_RETRIES:
                    backoff = 2**attempt
                    log(f"download attempt {attempt} failed ({exc}); retrying in {backoff}s")
                    time.sleep(backoff)
        raise RuntimeError(f"download failed after {DOWNLOAD_RETRIES} attempts: {last_exc}")

    @staticmethod
    def _hash_file(path: str) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as fh:
            while chunk := fh.read(DOWNLOAD_CHUNK):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    @contextmanager
    def _open_csv(self, path: str) -> Iterator[IO[str]]:
        """Yield a text handle over the CSV, unwrapping a ZIP if that is what
        we were handed.

        The portal's ``.csv`` URL actually serves a ZIP, so the container is
        detected by magic bytes rather than by extension or content-type — if
        it ever stops zipping, this keeps working with no deploy.
        """
        with open(path, "rb") as probe:
            magic = probe.read(2)
        if magic == b"PK":
            with zipfile.ZipFile(path) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                csvs = [n for n in names if n.lower().endswith(".csv")] or names
                if not csvs:
                    raise SyncAborted("zip archive contained no files")
                with zf.open(csvs[0]) as raw:
                    yield io.TextIOWrapper(raw, encoding=self.encoding, newline="")
        else:
            with open(path, encoding=self.encoding, newline="") as fh:
                yield fh

    def _copy_into_staging(self, cur, source_file: str, *, log) -> tuple[int, int]:
        columns = ", ".join(self.staging_columns)
        rows = 0
        rejected = 0
        started = time.monotonic()
        with self._open_csv(source_file) as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            missing = [c for c in self.expected_columns if c not in header]
            if missing:
                raise SyncAborted(
                    "source file is missing expected column(s): "
                    + ", ".join(missing)
                )
            known = set(self.expected_columns) | set(self.ignored_columns)
            extra = [c for c in header if c not in known]
            if extra:
                log(f"note: source has new column(s) we ignore: {', '.join(extra)}")

            with cur.copy(
                f"COPY {self.staging_table} ({columns}) FROM STDIN"
            ) as copy:
                for row in reader:
                    record = self.map_row(row)
                    if record is None:
                        rejected += 1
                        continue
                    copy.write_row(record)
                    rows += 1
        log(
            f"staged {rows:,} rows ({rejected} rejected) in "
            f"{time.monotonic() - started:.1f}s"
        )
        return rows, rejected

    def _safety_gate(
        self, *, active_before: int, staged: int, deactivating: int, force: bool, log
    ) -> None:
        if active_before == 0:
            log("first load — nothing to compare against, safety gate skipped")
            return
        floor = int(active_before * MIN_ROWS_FRACTION)
        churn_cap = int(active_before * MAX_DEACTIVATED_FRACTION)
        problems = []
        if staged < floor:
            problems.append(
                f"file has {staged:,} rows, under {MIN_ROWS_FRACTION:.0%} of the "
                f"{active_before:,} currently active ({floor:,})"
            )
        if deactivating > churn_cap:
            problems.append(
                f"{deactivating:,} active rows would be deactivated, over "
                f"{MAX_DEACTIVATED_FRACTION:.0%} of {active_before:,} ({churn_cap:,})"
            )
        if not problems:
            return
        detail = "; ".join(problems)
        if force:
            log(f"safety gate overridden by --force: {detail}")
            return
        raise SyncAborted(f"safety gate: {detail}. Re-run with --force to override.")

    @staticmethod
    def _finish(snapshot: Snapshot, status: str, **fields) -> None:
        snapshot.status = status
        snapshot.finished_at = timezone.now()
        for key, value in fields.items():
            setattr(snapshot, key, value)
        snapshot.save(
            update_fields=["status", "finished_at", *fields.keys()]
        )
