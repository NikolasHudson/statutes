"""Auth hardening regression tests (findings #6 / #14 / #15).

Covers:
  * django-axes brute-force lockout on repeated bad logins, and that a
    successful login resets the counter.
  * The append-only ``AuditEvent`` trail for login success/failure, logout,
    registration, password change, and API-key lifecycle.
  * The account-enumeration-safe register message.
  * The /register IP throttle.

These run with the LocMem cache (no REDIS_URL in tests), so axes uses its
database handler — the lockout still holds, only the storage differs from prod.
Axes state (DB rows + cache) is cleared between tests so counts don't leak.
"""

from __future__ import annotations

import json

from axes.handlers.proxy import AxesProxyHandler
from axes.models import AccessAttempt
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.accounts.audit import AuditEvent
from apps.accounts.models import APIKey, User


def _post(client: Client, path: str, payload: dict, **extra):
    return client.post(
        path, data=json.dumps(payload), content_type="application/json", **extra
    )


def _reset_axes():
    AxesProxyHandler.reset_attempts()
    AccessAttempt.objects.all().delete()
    cache.clear()


@override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=3, AXES_RESET_ON_SUCCESS=True)
class LoginLockoutTests(TestCase):
    PASSWORD = "correct-horse-battery-staple"

    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)
        self.user = User.objects.create_user(
            email="lock@example.com", password=self.PASSWORD
        )

    def _bad_login(self):
        return _post(
            Client(),
            "/api/auth/login",
            {"email": "lock@example.com", "password": "wrong-password-xx"},
        )

    def test_repeated_bad_logins_lock_out(self):
        # First (FAILURE_LIMIT - 1) failures return the generic 401.
        for _ in range(2):
            self.assertEqual(self._bad_login().status_code, 401)
        # The Nth failure trips the lock; axes now blocks further attempts.
        self._bad_login()
        # A subsequent attempt — even with the CORRECT password — is refused
        # with the generic throttle response while the lock holds.
        resp = _post(
            Client(),
            "/api/auth/login",
            {"email": "lock@example.com", "password": self.PASSWORD},
        )
        self.assertEqual(resp.status_code, 429, resp.content)
        # And the body never reveals account existence / attempt count.
        self.assertIn("try again", resp.json()["detail"].lower())

    def test_lockout_emits_audit_events(self):
        for _ in range(3):
            self._bad_login()
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.LOGIN_FAILURE
            ).count(),
            3,
        )
        # The blocked correct-password attempt is recorded as a lockout event.
        _post(
            Client(),
            "/api/auth/login",
            {"email": "lock@example.com", "password": self.PASSWORD},
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.LOGIN_LOCKED_OUT
            ).exists()
        )

    def _recorded_failures(self) -> int:
        # The DB handler accumulates one AccessAttempt row per IP+username with
        # a running failures_since_start; sum them for this account.
        return sum(
            a.failures_since_start
            for a in AccessAttempt.objects.filter(username="lock@example.com")
        )

    def test_successful_login_resets_the_counter(self):
        # Two failures (under the limit of 3)…
        for _ in range(2):
            self.assertEqual(self._bad_login().status_code, 401)
        self.assertEqual(self._recorded_failures(), 2)

        # …then a success clears the count (AXES_RESET_ON_SUCCESS).
        ok = _post(
            Client(),
            "/api/auth/login",
            {"email": "lock@example.com", "password": self.PASSWORD},
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(self._recorded_failures(), 0)
        # Fresh bad attempts start from zero again rather than from 2, so the
        # account is not one failure away from a lock after a good login.
        for _ in range(2):
            self.assertEqual(self._bad_login().status_code, 401)


class AuditTrailTests(TestCase):
    """The audit table fills for every security-relevant account action."""

    PASSWORD = "audit-pass-123456"

    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)

    def _logged_in_client(self, email="audit@example.com"):
        User.objects.create_user(email=email, password=self.PASSWORD)
        client = Client()
        _post(client, "/api/auth/login", {"email": email, "password": self.PASSWORD})
        return client

    def test_login_success_and_logout_recorded(self):
        client = self._logged_in_client()
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.LOGIN_SUCCESS,
                actor_email="audit@example.com",
            ).exists()
        )
        client.post("/api/auth/logout")
        self.assertTrue(
            AuditEvent.objects.filter(event_type=AuditEvent.Event.LOGOUT).exists()
        )

    def test_registration_recorded_with_source_ip(self):
        resp = _post(
            Client(),
            "/api/auth/register",
            {"email": "new@example.com", "password": self.PASSWORD},
            REMOTE_ADDR="203.0.113.7",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        row = AuditEvent.objects.get(event_type=AuditEvent.Event.REGISTER)
        self.assertEqual(row.actor_email, "new@example.com")
        self.assertEqual(row.source_ip, "203.0.113.7")

    def test_source_ip_prefers_x_forwarded_for(self):
        _post(
            Client(),
            "/api/auth/register",
            {"email": "xff@example.com", "password": self.PASSWORD},
            HTTP_X_FORWARDED_FOR="198.51.100.4, 10.0.0.1",
            REMOTE_ADDR="10.0.0.1",
        )
        row = AuditEvent.objects.get(
            event_type=AuditEvent.Event.REGISTER, actor_email="xff@example.com"
        )
        # Behind the DO proxy the real client is the left-most XFF entry.
        self.assertEqual(row.source_ip, "198.51.100.4")

    def test_password_and_profile_and_key_events(self):
        client = self._logged_in_client()
        _post(
            client,
            "/api/auth/change-password",
            {"current_password": self.PASSWORD, "new_password": "brand-new-pw-99"},
        )
        client.patch(
            "/api/auth/me",
            data=json.dumps({"full_name": "Renamed"}),
            content_type="application/json",
        )
        created = _post(client, "/api/account/api-keys", {"name": "k"}).json()
        client.delete(f"/api/account/api-keys/{created['id']}")

        for event in (
            AuditEvent.Event.PASSWORD_CHANGE,
            AuditEvent.Event.PROFILE_CHANGE,
            AuditEvent.Event.API_KEY_CREATE,
            AuditEvent.Event.API_KEY_REVOKE,
        ):
            self.assertTrue(
                AuditEvent.objects.filter(event_type=event).exists(),
                f"missing audit event {event}",
            )
        # The raw key must never appear in the audit detail — only the prefix.
        create_row = AuditEvent.objects.get(
            event_type=AuditEvent.Event.API_KEY_CREATE
        )
        self.assertIn("prefix", create_row.detail)
        self.assertNotIn("raw_key", create_row.detail)

    def test_audit_event_is_append_only(self):
        row = AuditEvent.objects.create(
            event_type=AuditEvent.Event.LOGIN_SUCCESS, actor_email="x@example.com"
        )
        with self.assertRaises(RuntimeError):
            row.outcome = AuditEvent.Outcome.FAILURE
            row.save()


class RegisterEnumerationTests(TestCase):
    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)

    def test_duplicate_email_returns_generic_message(self):
        User.objects.create_user(email="dup@example.com", password="x" * 12)
        resp = _post(
            Client(),
            "/api/auth/register",
            {"email": "dup@example.com", "password": "longenough-12"},
        )
        self.assertEqual(resp.status_code, 400)
        # Must NOT confirm the email already exists (enumeration oracle).
        detail = resp.json()["detail"].lower()
        self.assertNotIn("already exists", detail)
        self.assertNotIn("taken", detail)
        # The duplicate attempt is still audited.
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.REGISTER_BLOCKED
            ).exists()
        )


class RegisterThrottleTests(TestCase):
    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)

    def test_register_is_ip_throttled(self):
        client = Client()
        # The 11th registration from one IP within the hour is rejected (cap 10).
        last = None
        for i in range(12):
            last = _post(
                client,
                "/api/auth/register",
                {"email": f"u{i}@example.com", "password": "longenough-12"},
                REMOTE_ADDR="192.0.2.50",
            )
        self.assertEqual(last.status_code, 429, last.content)
