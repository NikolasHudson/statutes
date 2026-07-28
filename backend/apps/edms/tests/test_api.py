"""``/api/edms`` behaviour: who gets in, what the save flow writes, and the two
rules that are product promises rather than implementation details.

Graph is mocked throughout — these tests are about our decisions (where does a
filing go, what do we believe, what do we refuse), not about Microsoft's API.
The one thing deliberately NOT mocked is the boundary itself: no test here ever
hands the server a document, because no endpoint here accepts one.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Tier
from apps.edms.models import (
    CaseFolderMapping,
    CloudIntegration,
    EdmsSettings,
    FilingSync,
    Provider,
)
from apps.edms.onedrive import RemoteItem, UploadSession

from ._factories import connect_onedrive, make_api_key, make_bearer, make_user

ROUTE_PAYLOAD = {
    "case_number": "CVCV012345",
    "doc_title": "Motion to Dismiss",
    "doc_type": "Motion",
    "row_date": "2024-03-15",
}


def _session_client(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _fake_session(folder="Hudson EDMSpro/CVCV012345", name="doc.pdf"):
    return UploadSession(
        upload_url="https://upload.example.com/session/abc",
        expires_at=timezone.now() + dt.timedelta(minutes=15),
        folder_path=folder,
        filename=name,
    )


def _fake_item(item_id="ITEM1", name="doc.pdf"):
    return RemoteItem(
        item_id=item_id,
        name=name,
        web_url="https://onedrive.example.com/doc.pdf",
        size=1234,
        folder_path="Hudson EDMSpro/CVCV012345",
    )


class AuthMatrixTests(TestCase):
    """Three credential shapes, one policy — and an ``mcp`` token is not one of
    the three."""

    def setUp(self):
        self.user = make_user()

    def test_session_cookie_accepted(self):
        self.assertEqual(_session_client(self.user).get("/api/edms/settings").status_code, 200)

    def test_api_key_accepted(self):
        raw = make_api_key(self.user)
        resp = Client().get("/api/edms/settings", headers={"x-api-key": raw})
        self.assertEqual(resp.status_code, 200)

    def test_oauth_bearer_with_edms_scope_accepted(self):
        token = make_bearer(self.user, scope="edms")
        resp = Client().get(
            "/api/edms/settings", headers={"authorization": f"Bearer {token}"}
        )
        self.assertEqual(resp.status_code, 200)

    def test_oauth_bearer_with_only_mcp_scope_refused(self):
        """The scope is a boundary, not a label: an MCP connector's token must
        not reach a user's document store."""
        token = make_bearer(self.user, scope="mcp")
        resp = Client().get(
            "/api/edms/settings", headers={"authorization": f"Bearer {token}"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_unknown_bearer_refused(self):
        resp = Client().get("/api/edms/settings", headers={"authorization": "Bearer nope"})
        self.assertEqual(resp.status_code, 401)

    def test_no_credential_refused(self):
        self.assertEqual(Client().get("/api/edms/settings").status_code, 401)

    def test_deactivated_user_loses_bearer_access(self):
        token = make_bearer(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        resp = Client().get(
            "/api/edms/settings", headers={"authorization": f"Bearer {token}"}
        )
        self.assertEqual(resp.status_code, 401)


class EntitlementTests(TestCase):
    def test_free_tier_gets_403(self):
        user = make_user("free@example.com", tier=Tier.FREE)
        resp = _session_client(user).get("/api/edms/settings")
        self.assertEqual(resp.status_code, 403)

    @override_settings(BILLING_REQUIRE_PAID=True)
    def test_no_plan_gets_402_before_the_feature_check(self):
        user = make_user("free@example.com", tier=Tier.FREE)
        resp = _session_client(user).get("/api/edms/settings")
        self.assertEqual(resp.status_code, 402)

    def test_me_advertises_the_edms_feature(self):
        user = make_user()
        body = _session_client(user).get("/api/auth/me").json()
        self.assertIn("edms", body["features"])

    def test_me_omits_edms_for_free_tier(self):
        user = make_user("free@example.com", tier=Tier.FREE)
        body = _session_client(user).get("/api/auth/me").json()
        self.assertNotIn("edms", body["features"])


class SettingsTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client_ = _session_client(self.user)

    def test_defaults_are_created_on_first_read(self):
        body = self.client_.get("/api/edms/settings").json()
        self.assertEqual(body["naming_template"], "{date}_{case_num}_{doc_title}")
        self.assertEqual(body["case_folder_template"], "{case_number}")
        self.assertFalse(body["crowdsource_opt_in"])
        self.assertFalse(body["connection"]["connected"])
        self.assertIn("{case_number}", body["folder_tokens"])
        self.assertIn("{doc_title}", body["filename_tokens"])

    def test_patch_updates_templates(self):
        resp = self.client_.patch(
            "/api/edms/settings",
            data=json.dumps({"case_folder_template": "{year}/{case_number}"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["case_folder_template"], "{year}/{case_number}")

    def test_blank_template_falls_back_to_the_default(self):
        resp = self.client_.patch(
            "/api/edms/settings",
            data=json.dumps({"naming_template": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.json()["naming_template"], "{date}_{case_num}_{doc_title}")

    def test_connection_reports_needs_reconnect(self):
        integration = connect_onedrive(self.user)
        integration.mark_needs_reconnect("invalid_grant")
        body = self.client_.get("/api/edms/settings").json()
        self.assertTrue(body["connection"]["connected"])
        self.assertTrue(body["connection"]["needs_reconnect"])

    def test_tokens_are_never_serialized(self):
        connect_onedrive(self.user)
        raw = self.client_.get("/api/edms/settings").content.decode()
        self.assertNotIn("access-token", raw)
        self.assertNotIn("refresh-token", raw)
        self.assertNotIn("access_token", raw)


class CrowdsourceOptInRuleTests(TestCase):
    """Enabling contribution sharing is session-only; disabling is not.

    This asymmetry is the product rule, not an accident of implementation: a
    headless caller must never be able to enroll an attorney into sharing client
    documents, but stopping must be possible from anywhere."""

    def setUp(self):
        self.user = make_user()

    def _patch(self, client, value, **headers):
        return client.patch(
            "/api/edms/settings",
            data=json.dumps({"crowdsource_opt_in": value}),
            content_type="application/json",
            headers=headers,
        )

    def test_session_can_enable(self):
        resp = self._patch(_session_client(self.user), True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["crowdsource_opt_in"])
        self.assertIsNotNone(resp.json()["crowdsource_opt_in_at"])

    def test_api_key_cannot_enable(self):
        raw = make_api_key(self.user)
        resp = self._patch(Client(), True, **{"x-api-key": raw})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(EdmsSettings.objects.get(user=self.user).crowdsource_opt_in)

    def test_bearer_cannot_enable(self):
        token = make_bearer(self.user)
        resp = self._patch(Client(), True, **{"authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 403)

    def test_bearer_can_disable(self):
        EdmsSettings.objects.create(user=self.user, crowdsource_opt_in=True)
        token = make_bearer(self.user)
        resp = self._patch(Client(), False, **{"authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["crowdsource_opt_in"])

    def test_toggle_is_audited(self):
        from apps.accounts.audit import AuditEvent

        self._patch(_session_client(self.user), True)
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.user, event_type=AuditEvent.Event.EDMS_OPT_IN
            ).exists()
        )


class SafetyEndpointTests(TestCase):
    def test_blocked_list_is_served(self):
        body = _session_client(make_user()).get("/api/edms/safety").json()
        prefixes = {row["prefix"] for row in body["blocked"]}
        self.assertEqual(prefixes, {"JV", "JD", "AD"})


# The OneDrive save flow is v2 code that v1 does not ship (see
# EDMS_CLOUD_ENABLED in core/settings.py). It stays fully tested — the flag,
# not a deletion, is what keeps it out of production — so the suites that
# exercise it turn it on explicitly. V1DefaultPostureTests at the bottom of
# this file is the one that asserts the shipped default.
@override_settings(EDMS_CLOUD_ENABLED=True)
class RouteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client_ = _session_client(self.user)

    def _post_route(self, **overrides):
        payload = {**ROUTE_PAYLOAD, **overrides}
        return self.client_.post(
            "/api/edms/route", data=json.dumps(payload), content_type="application/json"
        )

    def test_requires_a_connected_provider(self):
        resp = self._post_route()
        self.assertEqual(resp.status_code, 409)

    def test_requires_a_case_number(self):
        connect_onedrive(self.user)
        self.assertEqual(self._post_route(case_number="  ").status_code, 400)

    @mock.patch("apps.edms.onedrive.create_upload_session")
    @mock.patch("apps.edms.onedrive.ensure_folder_path")
    def test_happy_path_returns_an_upload_url_and_logs_metadata(self, ensure, mint):
        connect_onedrive(self.user)
        ensure.return_value = {"id": "F1", "name": "CVCV012345", "path": "x"}
        mint.return_value = _fake_session(name="2024-03-15_CVCV012345_Motion to Dismiss.pdf")

        resp = self._post_route()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["upload_url"], "https://upload.example.com/session/abc")
        self.assertFalse(body["crowdsource_eligible"])

        sync = FilingSync.objects.get(pk=body["sync_id"])
        self.assertEqual(sync.status, FilingSync.Status.PENDING_UPLOAD)
        self.assertEqual(sync.case_number, "CVCV012345")
        self.assertEqual(sync.destination_path, "Hudson EDMSpro/CVCV012345")
        self.assertEqual(sync.row_date, dt.date(2024, 3, 15))
        # The folder is ensured before the session is minted, and both run
        # against the resolved destination.
        ensure.assert_called_once()
        self.assertEqual(ensure.call_args.args[1], "Hudson EDMSpro/CVCV012345")

    @mock.patch("apps.edms.onedrive.create_upload_session")
    @mock.patch("apps.edms.onedrive.ensure_folder_path")
    def test_crowdsource_eligibility_follows_opt_in_and_the_safety_filter(self, ensure, mint):
        connect_onedrive(self.user)
        ensure.return_value = {"id": "F1", "name": "n", "path": "x"}
        mint.return_value = _fake_session()
        EdmsSettings.objects.update_or_create(
            user=self.user, defaults={"crowdsource_opt_in": True}
        )

        self.assertTrue(self._post_route().json()["crowdsource_eligible"])
        # …but never for a confidential case type, opt-in or not.
        self.assertFalse(
            self._post_route(case_number="JVJV000123").json()["crowdsource_eligible"]
        )

    @mock.patch("apps.edms.onedrive.create_upload_session")
    @mock.patch("apps.edms.onedrive.ensure_folder_path")
    def test_stale_token_surfaces_as_409_reconnect(self, ensure, mint):
        from apps.edms.onedrive import OneDriveAuthError

        connect_onedrive(self.user)
        ensure.side_effect = OneDriveAuthError("reconnect to continue")
        self.assertEqual(self._post_route().status_code, 409)

    @mock.patch("apps.edms.onedrive.create_upload_session")
    @mock.patch("apps.edms.onedrive.ensure_folder_path")
    def test_throttling_surfaces_as_503(self, ensure, mint):
        from apps.edms.onedrive import OneDriveRetryableError

        connect_onedrive(self.user)
        ensure.side_effect = OneDriveRetryableError(429, "throttled", 30)
        self.assertEqual(self._post_route().status_code, 503)

    @override_settings(EDMS_DAILY_UPLOAD_LIMIT=2)
    @mock.patch("apps.edms.onedrive.create_upload_session")
    @mock.patch("apps.edms.onedrive.ensure_folder_path")
    def test_daily_quota(self, ensure, mint):
        connect_onedrive(self.user)
        ensure.return_value = {"id": "F1", "name": "n", "path": "x"}
        mint.return_value = _fake_session()
        self.assertEqual(self._post_route().status_code, 200)
        self.assertEqual(self._post_route().status_code, 200)
        self.assertEqual(self._post_route().status_code, 429)


@override_settings(EDMS_CLOUD_ENABLED=True)  # v2 code, preserved: see V1DefaultPostureTests
class CompleteTests(TestCase):
    """A client that says "done" proves nothing."""

    def setUp(self):
        self.user = make_user()
        self.client_ = _session_client(self.user)
        connect_onedrive(self.user)
        self.sync = FilingSync.objects.create(
            user=self.user,
            case_number="CVCV012345",
            provider=Provider.ONEDRIVE,
            destination_path="Hudson EDMSpro/CVCV012345",
            destination_filename="doc.pdf",
        )

    def _complete(self, **payload):
        return self.client_.post(
            f"/api/edms/sync/{self.sync.id}/complete",
            data=json.dumps(payload),
            content_type="application/json",
        )

    @mock.patch("apps.edms.onedrive.get_item")
    def test_success_requires_the_item_to_exist(self, get_item):
        get_item.return_value = _fake_item()
        resp = self._complete(item_id="ITEM1")
        self.assertEqual(resp.status_code, 200)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.status, FilingSync.Status.SUCCESS)
        self.assertEqual(self.sync.cloud_item_id, "ITEM1")
        self.assertEqual(self.sync.byte_size, 1234)

    @mock.patch("apps.edms.onedrive.get_item_by_path")
    @mock.patch("apps.edms.onedrive.get_item")
    def test_falls_back_to_a_path_lookup(self, get_item, by_path):
        get_item.return_value = None
        by_path.return_value = _fake_item(name="doc (1).pdf")
        self.assertEqual(self._complete(item_id="GONE").status_code, 200)
        self.sync.refresh_from_db()
        # Graph renamed on collision — the history shows the real filename.
        self.assertEqual(self.sync.destination_filename, "doc (1).pdf")

    @mock.patch("apps.edms.onedrive.get_item_by_path")
    @mock.patch("apps.edms.onedrive.get_item")
    def test_unverifiable_upload_is_recorded_as_failed(self, get_item, by_path):
        get_item.return_value = None
        by_path.return_value = None
        self.assertEqual(self._complete(item_id="NOPE").status_code, 409)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.status, FilingSync.Status.FAILED)
        self.assertIn("could not be confirmed", self.sync.error)

    def test_another_users_sync_is_invisible(self):
        other = _session_client(make_user("other@example.com"))
        resp = other.post(
            f"/api/edms/sync/{self.sync.id}/complete",
            data=json.dumps({"item_id": "ITEM1"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_client_reported_failure_is_recorded(self):
        resp = self.client_.post(
            f"/api/edms/sync/{self.sync.id}/fail",
            data=json.dumps({"error": "network died"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.sync.refresh_from_db()
        self.assertEqual(self.sync.status, FilingSync.Status.FAILED)
        self.assertEqual(self.sync.error, "network died")


@override_settings(EDMS_CLOUD_ENABLED=True)  # v2 code, preserved: see V1DefaultPostureTests
class SyncHistoryTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user("other@example.com")
        for i in range(3):
            FilingSync.objects.create(user=self.user, case_number=f"CV{i}")
        FilingSync.objects.create(user=self.other, case_number="THEIRS")

    def test_history_is_scoped_to_the_caller(self):
        body = _session_client(self.user).get("/api/edms/syncs").json()
        self.assertEqual(body["total"], 3)
        self.assertNotIn("THEIRS", [r["case_number"] for r in body["results"]])

    def test_filters(self):
        body = _session_client(self.user).get("/api/edms/syncs?case_number=CV1").json()
        self.assertEqual(body["total"], 1)


@override_settings(EDMS_CLOUD_ENABLED=True)  # v2 code, preserved: see V1DefaultPostureTests
class CaseFolderTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client_ = _session_client(self.user)

    def test_missing_override_reads_as_empty_not_404(self):
        body = self.client_.get("/api/edms/case-folders/CVCV1").json()
        self.assertEqual(body["case_number"], "CVCV1")
        self.assertEqual(body["folder_path"], "")

    def test_upsert_and_delete(self):
        resp = self.client_.put(
            "/api/edms/case-folders/CVCV1",
            data=json.dumps({"folder_path": "Clients/Acme", "folder_id": "F9"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            CaseFolderMapping.objects.filter(user=self.user, case_number="CVCV1").exists()
        )
        # Idempotent — a second PUT updates rather than colliding on the
        # (user, case_number) constraint.
        self.client_.put(
            "/api/edms/case-folders/CVCV1",
            data=json.dumps({"folder_path": "Clients/Beta"}),
            content_type="application/json",
        )
        self.assertEqual(
            CaseFolderMapping.objects.get(user=self.user, case_number="CVCV1").folder_path,
            "Clients/Beta",
        )
        self.assertTrue(
            self.client_.delete("/api/edms/case-folders/CVCV1").json()["deleted"]
        )


@override_settings(EDMS_CLOUD_ENABLED=True)  # v2 code, preserved: see V1DefaultPostureTests
class DisconnectTests(TestCase):
    def test_disconnect_removes_the_stored_tokens(self):
        user = make_user()
        connect_onedrive(user)
        resp = _session_client(user).delete("/api/edms/integrations/onedrive")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["connected"])
        self.assertFalse(CloudIntegration.objects.filter(user=user).exists())

    def test_authorize_is_503_when_microsoft_is_not_configured(self):
        resp = _session_client(make_user()).get("/api/edms/integrations/onedrive/authorize")
        self.assertEqual(resp.status_code, 503)

    @override_settings(MS_OAUTH_CLIENT_ID="cid", MS_OAUTH_CLIENT_SECRET="secret")
    def test_authorize_url_carries_state_bound_to_the_session(self):
        client = _session_client(make_user())
        body = client.get("/api/edms/integrations/onedrive/authorize").json()
        self.assertIn("login.microsoftonline.com", body["authorize_url"])
        self.assertIn("state=", body["authorize_url"])
        self.assertIn("edms_ms_oauth_state", client.session)


# Deliberately NOT decorated: this class asserts what a deployment that sets
# nothing actually serves.
class V1DefaultPostureTests(TestCase):
    """What EDMSpro v1 ships: the cloud surface is absent, the rest is not.

    Every other class above turns ``EDMS_CLOUD_ENABLED`` on because it is
    testing preserved v2 code. This one pins the default, which is the posture
    production runs in — and pins it against an *entitled, authenticated* user,
    because "the paywall happened to stop them" is not the control being tested.
    """

    # One line per operation on ``cloud_router``. A route added there without a
    # line here is a route nobody checked was dark.
    GATED = [
        ("get", "/api/edms/integrations/onedrive/authorize"),
        ("get", "/api/edms/integrations/onedrive/callback"),
        ("delete", "/api/edms/integrations/onedrive"),
        ("get", "/api/edms/integrations/onedrive/folders"),
        ("post", "/api/edms/integrations/onedrive/folders"),
        ("get", "/api/edms/case-folders/CVCV012345"),
        ("put", "/api/edms/case-folders/CVCV012345"),
        ("delete", "/api/edms/case-folders/CVCV012345"),
        ("post", "/api/edms/route"),
        ("post", "/api/edms/sync/1/complete"),
        ("post", "/api/edms/sync/1/fail"),
        ("get", "/api/edms/syncs"),
        ("post", "/api/edms/crowdsource?case_number=CVCV012345"),
    ]

    def setUp(self):
        self.user = make_user()  # SOLO tier — entitled to the `edms` feature
        self.client_ = _session_client(self.user)

    @staticmethod
    def _call(client, method, path):
        if method in ("get", "delete"):
            return getattr(client, method)(path)
        return getattr(client, method)(
            path, data=json.dumps({}), content_type="application/json"
        )

    def test_every_cloud_route_is_gone_for_an_entitled_user(self):
        for method, path in self.GATED:
            with self.subTest(route=f"{method.upper()} {path}"):
                resp = self._call(self.client_, method, path)
                self.assertEqual(resp.status_code, 404)

    def test_the_v1_routes_are_untouched(self):
        """Gating the cloud feature must not take the naming template (which is
        how the extension names the file it downloads) or the safety list with
        it."""
        self.assertEqual(self.client_.get("/api/edms/settings").status_code, 200)
        self.assertEqual(self.client_.get("/api/edms/safety").status_code, 200)
        # …and the contribution opt-in is still a live preference, even though
        # the endpoint that consumed it is gated.
        resp = self.client_.patch(
            "/api/edms/settings",
            data=json.dumps({"crowdsource_opt_in": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["crowdsource_opt_in"])

    def test_a_gated_route_looks_exactly_like_one_that_never_existed(self):
        """The 404 has to land before authentication. If it did not, an
        anonymous probe would get 401 and learn the endpoint is there — a
        feature we have not shipped should not be discoverable."""
        anon = Client()
        control = anon.get("/api/edms/no-such-route-at-all")
        self.assertEqual(control.status_code, 404)
        for method, path in self.GATED:
            with self.subTest(route=f"{method.upper()} {path}"):
                resp = self._call(anon, method, path)
                self.assertEqual(resp.status_code, 404)
                self.assertEqual(resp.content, control.content)

    def test_the_public_openapi_document_does_not_advertise_them_either(self):
        """``/api/openapi.json`` needs no credential, so a spec listing routes
        that 404 would hand back the fact the pre-auth 404 withholds."""
        schema = Client().get("/api/openapi.json").content.decode()
        for fragment in (
            "/edms/route",
            "/edms/syncs",
            "/edms/crowdsource",
            "/edms/case-folders",
            "/edms/integrations/onedrive",
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, schema)
        # The v1 surface is still documented.
        self.assertIn("/edms/settings", schema)
        self.assertIn("/edms/safety", schema)
        with override_settings(EDMS_CLOUD_ENABLED=True):
            self.assertIn(
                "/edms/route", Client().get("/api/openapi.json").content.decode()
            )

    def test_the_flag_is_the_only_thing_holding_v2_back(self):
        """The counterpart to the above: the code is preserved, not removed, so
        flipping one setting brings the whole surface back."""
        with override_settings(EDMS_CLOUD_ENABLED=True):
            self.assertEqual(self.client_.get("/api/edms/syncs").status_code, 200)
            self.assertEqual(
                self.client_.get("/api/edms/case-folders/CVCV012345").status_code, 200
            )
            self.assertEqual(Client().get("/api/edms/syncs").status_code, 401)
