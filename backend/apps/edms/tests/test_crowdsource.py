"""The contribution path — the one place a user's document reaches us.

Everything here is about limits: who may contribute (opt-in, server-checked),
what may never be contributed (confidential case types, whatever the user
clicked), how bytes move (streamed, capped, never on disk), and what happens
afterwards (nothing — the bucket is inert — except purge).

The retention rule is asserted explicitly because it is counter-intuitive and
was a deliberate decision: turning the opt-in **off does not remove anything**.
It stops future intake. Removal is account deletion or the purge command.
"""

from __future__ import annotations

import io
import json
from unittest import mock

from django.test import Client, TestCase, override_settings

from apps.accounts.audit import AuditEvent
from apps.edms import storage
from apps.edms.models import CrowdsourceArtifact, EdmsSettings
from apps.edms.services import purge_user_contributions

from ._factories import SPACES_SETTINGS, FakeS3, make_bearer, make_user

PDF = b"%PDF-1.7\n" + b"x" * 2048


def _session_client(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _url(case_number="CVCV012345", **extra):
    params = {"case_number": case_number, "doc_type": "Motion", **extra}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/api/edms/crowdsource?{query}"


class MeteredReaderTests(TestCase):
    """Unit-level, because the cap has to hold against a stream that lies about
    its length — the HTTP-level Content-Length check is a courtesy, not the
    control."""

    def test_counts_and_hashes(self):
        reader = storage.MeteredReader(io.BytesIO(PDF))
        out = b""
        while chunk := reader.read(512):
            out += chunk
        self.assertEqual(out, PDF)
        self.assertEqual(reader.bytes_read, len(PDF))
        self.assertEqual(len(reader.sha256), 64)

    def test_raises_once_over_the_cap(self):
        reader = storage.MeteredReader(io.BytesIO(PDF), max_bytes=100)
        with self.assertRaises(storage.PayloadTooLarge):
            while reader.read(64):
                pass


# /crowdsource is gated with the rest of the cloud path: its only client was
# the save flow v1 does not ship, so nothing can reach it until
# EDMS_CLOUD_ENABLED is on. The opt-in *setting* is not gated — it is still
# writable through PATCH /api/edms/settings (see test_api.py).
@override_settings(EDMS_CLOUD_ENABLED=True, **SPACES_SETTINGS)
class ContributeTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client_ = _session_client(self.user)
        self.fake = FakeS3()
        patcher = mock.patch.object(storage, "_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _opt_in(self):
        EdmsSettings.objects.update_or_create(
            user=self.user, defaults={"crowdsource_opt_in": True}
        )

    def _post(self, url=None, body=PDF, content_type="application/pdf"):
        return self.client_.post(url or _url(), data=body, content_type=content_type)

    def test_refused_without_opt_in(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.fake.objects, {})

    def test_refused_for_confidential_case_types_even_when_opted_in(self):
        self._opt_in()
        for case_number in ("JVJV000123", "JD-000123", "ad 000999"):
            with self.subTest(case_number=case_number):
                resp = self._post(_url(case_number=case_number))
                self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.fake.objects, {})

    def test_wrong_content_type_refused(self):
        self._opt_in()
        self.assertEqual(self._post(content_type="application/json").status_code, 415)

    def test_declared_oversize_refused_before_streaming(self):
        self._opt_in()
        with mock.patch.object(storage, "MAX_UPLOAD_BYTES", 100):
            self.assertEqual(self._post().status_code, 413)
        self.assertEqual(self.fake.objects, {})

    def test_happy_path_streams_and_indexes(self):
        self._opt_in()
        resp = self._post()
        self.assertEqual(resp.status_code, 201)

        artifact = CrowdsourceArtifact.objects.get(pk=resp.json()["artifact_id"])
        self.assertEqual(artifact.submitted_by, self.user)
        self.assertEqual(artifact.byte_size, len(PDF))
        self.assertEqual(artifact.doc_type, "Motion")
        self.assertEqual(artifact.status, CrowdsourceArtifact.Status.STORED)
        # The bytes went to the bucket, under an opaque key that leaks no case
        # information to anyone reading a listing.
        self.assertEqual(self.fake.objects[artifact.object_key], PDF)
        self.assertNotIn("CVCV012345", artifact.object_key)

    def test_contribution_is_audited(self):
        self._opt_in()
        self._post()
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.user, event_type=AuditEvent.Event.EDMS_CONTRIBUTE
            ).exists()
        )

    def test_bearer_client_may_contribute(self):
        """The extension is the normal caller here — it holds an OAuth token,
        not a cookie. (It still cannot turn the opt-in ON; see test_api.)"""
        self._opt_in()
        token = make_bearer(self.user)
        resp = Client().post(
            _url(),
            data=PDF,
            content_type="application/pdf",
            headers={"authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 201)

    def test_503_when_the_bucket_is_not_configured(self):
        self._opt_in()
        with override_settings(SPACES_BUCKET=""):
            self.assertEqual(self._post().status_code, 503)


@override_settings(EDMS_CLOUD_ENABLED=True, **SPACES_SETTINGS)
class RetentionAndPurgeTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.fake = FakeS3()
        patcher = mock.patch.object(storage, "_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client_ = _session_client(self.user)
        EdmsSettings.objects.update_or_create(
            user=self.user, defaults={"crowdsource_opt_in": True}
        )
        self.client_.post(_url(), data=PDF, content_type="application/pdf")
        self.artifact = CrowdsourceArtifact.objects.get(submitted_by=self.user)

    def test_opting_out_is_prospective_and_removes_nothing(self):
        resp = self.client_.patch(
            "/api/edms/settings",
            data=json.dumps({"crowdsource_opt_in": False}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.artifact.refresh_from_db()
        self.assertEqual(self.artifact.status, CrowdsourceArtifact.Status.STORED)
        self.assertIn(self.artifact.object_key, self.fake.objects)
        self.assertEqual(self.fake.deleted, [])
        # …and further contributions are refused.
        self.assertEqual(
            self.client_.post(_url(), data=PDF, content_type="application/pdf").status_code,
            403,
        )

    def test_purge_deletes_the_object_and_marks_the_row(self):
        self.assertEqual(purge_user_contributions(self.user), 1)
        self.artifact.refresh_from_db()
        self.assertEqual(self.artifact.status, CrowdsourceArtifact.Status.PURGED)
        self.assertIsNotNone(self.artifact.purged_at)
        self.assertEqual(self.fake.deleted, [self.artifact.object_key])

    def test_purge_is_idempotent(self):
        purge_user_contributions(self.user)
        self.assertEqual(purge_user_contributions(self.user), 0)

    def test_account_deletion_empties_the_bucket_first(self):
        """The cascade would otherwise take the index row and leave the object —
        bytes nobody can attribute or honour a removal request for."""
        key = self.artifact.object_key
        self.user.delete()
        self.assertEqual(self.fake.deleted, [key])
        self.assertFalse(CrowdsourceArtifact.objects.filter(object_key=key).exists())

    def test_management_command(self):
        from django.core.management import call_command

        out = io.StringIO()
        call_command("purge_crowdsource", "--user", self.user.email, stdout=out)
        self.assertIn("Purged 1 artifact", out.getvalue())
        self.assertEqual(self.fake.deleted, [self.artifact.object_key])

    def test_management_command_dry_run_changes_nothing(self):
        from django.core.management import call_command

        out = io.StringIO()
        call_command(
            "purge_crowdsource", "--user", str(self.user.pk), "--dry-run", stdout=out
        )
        self.assertIn("Would purge 1 artifact", out.getvalue())
        self.assertEqual(self.fake.deleted, [])
