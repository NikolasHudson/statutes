"""Loader behaviour. The properties that matter are the destructive ones:
nothing is ever deleted, a truncated file is refused rather than applied, and
a run that aborts leaves the previous load exactly as it was.
"""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.resources.datasets.sos_entities.models import BusinessEntity
from apps.resources.models import Dataset, Snapshot, SnapshotStatus

from ._fixtures import SAMPLE_CSV, SAMPLE_ROWS, SAMPLE_ZIP, read_sample, write_csv, write_zip


def sync(path=SAMPLE_ZIP, **flags) -> None:
    args = ["sync_resource", "iowa-business-entities", "--file", str(path)]
    for flag, value in flags.items():
        if value:
            args.append(f"--{flag.replace('_', '-')}")
    call_command(*args, verbosity=0)


class SyncTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset.objects.get(slug="iowa-business-entities")

    def variant(self, name: str, mutate) -> str:
        """A copy of the fixture with ``mutate(rows)`` applied."""
        header, rows = read_sample()
        mutated = mutate(rows)
        return write_zip(
            Path(self.tmp.name) / name, header, rows if mutated is None else mutated
        )

    def last_snapshot(self) -> Snapshot:
        return self.dataset.snapshots.order_by("-id").first()


class FirstLoadTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        sync()

    def test_loads_every_keyed_row_and_rejects_the_rest(self):
        self.assertEqual(BusinessEntity.objects.count(), SAMPLE_ROWS)
        snap = self.last_snapshot()
        self.assertEqual(snap.status, SnapshotStatus.OK)
        self.assertEqual(snap.row_count, SAMPLE_ROWS)
        self.assertEqual(snap.inserted, SAMPLE_ROWS)
        self.assertEqual(snap.deactivated, 0)
        self.assertFalse(
            BusinessEntity.objects.filter(legal_name="NO KEY COMPANY").exists()
        )

    def test_quoted_name_is_stored_as_published_and_normalized_for_search(self):
        entity = BusinessEntity.objects.get(corp_number="100001")
        self.assertEqual(entity.legal_name, '" THE WOOD DOCTOR, L. C. "')
        self.assertEqual(entity.name_normalized, "THE WOOD DOCTOR")

    def test_future_effective_date_is_kept(self):
        # Delayed effective filings are normal; validating against today would
        # silently drop them.
        entity = BusinessEntity.objects.get(corp_number="100004")
        self.assertEqual(entity.effective_date, dt.date(2099, 1, 1))

    def test_blank_agent_and_missing_coordinates_survive(self):
        acme = BusinessEntity.objects.get(corp_number="100003")
        self.assertEqual(acme.registered_agent, "")
        self.assertEqual(acme.agent_normalized, "")
        no_coords = BusinessEntity.objects.get(corp_number="100009")
        self.assertIsNone(no_coords.ra_lat)
        self.assertIsNone(no_coords.ra_lon)

    def test_bookkeeping_columns(self):
        entity = BusinessEntity.objects.get(corp_number="100002")
        today = timezone.localdate()
        self.assertTrue(entity.is_active)
        self.assertEqual(entity.first_seen, today)
        self.assertEqual(entity.last_seen, today)
        self.assertIsNone(entity.deactivated_on)
        self.assertEqual(entity.last_snapshot_id, self.last_snapshot().pk)

    def test_dataset_as_of_comes_from_the_snapshot(self):
        self.assertIsNotNone(self.dataset.as_of())

    def test_plain_csv_loads_the_same_as_the_zip(self):
        BusinessEntity.objects.all().delete()
        sync(path=SAMPLE_CSV, force=True)
        self.assertEqual(BusinessEntity.objects.count(), SAMPLE_ROWS)


class RerunTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        sync()

    def test_identical_file_is_skipped(self):
        sync()
        snap = self.last_snapshot()
        self.assertEqual(snap.status, SnapshotStatus.SKIPPED)
        self.assertEqual(snap.row_count, 0)

    def test_force_reloads_and_changes_nothing(self):
        before = {e.corp_number: e.legal_name for e in BusinessEntity.objects.all()}
        sync(force=True)
        snap = self.last_snapshot()
        self.assertEqual(snap.status, SnapshotStatus.OK)
        self.assertEqual(snap.inserted, 0)
        self.assertEqual(snap.updated, SAMPLE_ROWS)
        self.assertEqual(snap.deactivated, 0)
        self.assertEqual(
            before, {e.corp_number: e.legal_name for e in BusinessEntity.objects.all()}
        )

    def test_changed_row_is_updated_and_first_seen_is_preserved(self):
        first_seen = BusinessEntity.objects.get(corp_number="100002").first_seen

        def rename(rows):
            for row in rows:
                if row["corp_number"] == "100002":
                    row["legal_name"] = "WOOD DOCTOR OF IOWA LLC"

        sync(path=self.variant("renamed.zip", rename))
        entity = BusinessEntity.objects.get(corp_number="100002")
        self.assertEqual(entity.legal_name, "WOOD DOCTOR OF IOWA LLC")
        self.assertEqual(entity.name_normalized, "WOOD DOCTOR OF IOWA")
        self.assertEqual(entity.first_seen, first_seen)

    def test_absent_row_is_deactivated_never_deleted(self):
        path = self.variant(
            "dropped.zip", lambda rows: [r for r in rows if r["corp_number"] != "100012"]
        )
        sync(path=path)
        entity = BusinessEntity.objects.get(corp_number="100012")
        self.assertFalse(entity.is_active)
        self.assertEqual(entity.deactivated_on, timezone.localdate())
        self.assertEqual(BusinessEntity.objects.count(), SAMPLE_ROWS)
        self.assertEqual(self.last_snapshot().deactivated, 1)

    def test_returning_row_is_reactivated(self):
        dropped = self.variant(
            "dropped.zip", lambda rows: [r for r in rows if r["corp_number"] != "100012"]
        )
        sync(path=dropped)
        sync()  # the original file, with the row back
        entity = BusinessEntity.objects.get(corp_number="100012")
        self.assertTrue(entity.is_active)
        self.assertIsNone(entity.deactivated_on)
        self.assertEqual(self.last_snapshot().reactivated, 1)

    def test_duplicate_key_in_source_does_not_take_the_load_down(self):
        def duplicate(rows):
            clone = dict(rows[0])
            clone["legal_name"] = "DUPLICATE KEY CO"
            return rows + [clone]

        sync(path=self.variant("dupe.zip", duplicate))
        self.assertEqual(BusinessEntity.objects.count(), SAMPLE_ROWS)


class GuardTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        sync()

    def assert_untouched(self):
        self.assertEqual(BusinessEntity.objects.filter(is_active=True).count(), SAMPLE_ROWS)

    def test_missing_column_aborts_before_staging(self):
        header, rows = read_sample()
        header.remove("legal_name")
        for row in rows:
            row.pop("legal_name")
        path = write_csv(Path(self.tmp.name) / "no_name.csv", header, rows)
        with self.assertRaises(CommandError):
            sync(path=path)
        self.assertEqual(self.last_snapshot().status, SnapshotStatus.ABORTED)
        self.assert_untouched()

    def test_shrunken_file_aborts_and_leaves_the_live_table_alone(self):
        path = self.variant("tiny.zip", lambda rows: rows[:4])
        with self.assertRaises(CommandError):
            sync(path=path)
        snap = self.last_snapshot()
        self.assertEqual(snap.status, SnapshotStatus.ABORTED)
        self.assertIn("safety gate", snap.message)
        self.assert_untouched()

    def test_excess_churn_aborts(self):
        # Two of twelve is over the 10% deactivation cap.
        path = self.variant(
            "churn.zip",
            lambda rows: [r for r in rows if r["corp_number"] not in {"100011", "100012"}],
        )
        with self.assertRaises(CommandError):
            sync(path=path)
        self.assertEqual(self.last_snapshot().status, SnapshotStatus.ABORTED)
        self.assert_untouched()

    def test_force_overrides_the_safety_gate(self):
        path = self.variant("tiny.zip", lambda rows: rows[:4])
        sync(path=path, force=True)
        snap = self.last_snapshot()
        self.assertEqual(snap.status, SnapshotStatus.OK)
        self.assertEqual(snap.deactivated, SAMPLE_ROWS - 4)
        self.assertEqual(BusinessEntity.objects.count(), SAMPLE_ROWS)

    def test_dry_run_writes_nothing(self):
        def rename(rows):
            for row in rows:
                if row["corp_number"] == "100002":
                    row["legal_name"] = "SOMETHING ELSE LLC"

        path = self.variant("renamed.zip", rename)
        sync(path=path, dry_run=True)
        self.assertEqual(
            BusinessEntity.objects.get(corp_number="100002").legal_name,
            "WOOD DOCTOR LLC",
        )
        snap = self.last_snapshot()
        self.assertEqual(snap.status, SnapshotStatus.ABORTED)
        self.assertIn("dry run", snap.message)

    def test_a_live_run_blocks_a_second_one(self):
        Snapshot.objects.create(dataset=self.dataset, status=SnapshotStatus.RUNNING)
        with self.assertRaises(CommandError):
            sync(force=True)

    def test_a_stale_running_snapshot_does_not_block(self):
        stale = Snapshot.objects.create(
            dataset=self.dataset, status=SnapshotStatus.RUNNING
        )
        Snapshot.objects.filter(pk=stale.pk).update(
            started_at=timezone.now() - dt.timedelta(hours=5)
        )
        sync(force=True)
        self.assertEqual(self.last_snapshot().status, SnapshotStatus.OK)


class EmptySourceTests(SyncTestCase):
    def test_empty_file_aborts(self):
        path = self.variant("empty.zip", lambda rows: [])
        with self.assertRaises(CommandError):
            sync(path=path)
        self.assertEqual(BusinessEntity.objects.count(), 0)


class UnknownDatasetTests(TestCase):
    def test_unknown_slug_is_a_command_error(self):
        with self.assertRaises(CommandError):
            call_command("sync_resource", "not-a-dataset", verbosity=0)
