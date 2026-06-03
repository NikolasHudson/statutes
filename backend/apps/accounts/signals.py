"""Auth-signal receivers that feed the security audit trail.

Wired from :meth:`AccountsConfig.ready`. These cover the three events Django
emits centrally — successful login, failed login, and logout — so they are
captured no matter which code path triggers auth (the ninja API login, the
Django admin login, ``force_login`` in tests, etc.). Credential/profile and
API-key lifecycle events have no built-in signal and are emitted explicitly
from the ninja handlers in ``apps/api/accounts.py``.

``user_login_failed`` is the one that matters most for brute-force forensics:
it fires for every bad password with the attempted credentials, and django-axes
listens to the same signal to drive its lockout counter.
"""

from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .audit import AuditEvent, record_event


@receiver(user_logged_in)
def _on_logged_in(sender, request, user, **kwargs):
    record_event(
        event_type=AuditEvent.Event.LOGIN_SUCCESS,
        request=request,
        actor=user,
        outcome=AuditEvent.Outcome.SUCCESS,
    )


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    # ``credentials`` is the dict passed to authenticate(); our login view
    # passes ``email=...``. Fall back to the conventional ``username`` key for
    # any other auth path (e.g. the admin).
    attempted = (
        credentials.get("email")
        or credentials.get("username")
        or ""
    )
    record_event(
        event_type=AuditEvent.Event.LOGIN_FAILURE,
        request=request,
        actor_email=attempted,
        outcome=AuditEvent.Outcome.FAILURE,
    )


@receiver(user_logged_out)
def _on_logged_out(sender, request, user, **kwargs):
    record_event(
        event_type=AuditEvent.Event.LOGOUT,
        request=request,
        actor=user,
        outcome=AuditEvent.Outcome.SUCCESS,
    )
