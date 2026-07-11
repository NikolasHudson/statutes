"""Append-only security audit trail (SOC 2 CC7.2 / CC6.1).

This is the security-event log: who authenticated, who changed their
credentials, who minted or revoked an API key, and from where. It is
deliberately *separate* from the product-accuracy traces
(``apps/api/models.ChatTrace`` / ``VerificationRun``), which are intentionally
unattributed (``user=None``) for query confidentiality and MUST stay that way.
Do not route auth events through that path or attribution there.

Design:

* **Append-only.** Rows are only ever inserted. There is no update/delete path
  in the app; ``AuditEvent.save`` refuses to mutate an existing row. Pruning,
  if ever needed, is an explicit ops action (a management command), not
  something the request path can do.
* **Actor may be null.** A failed login has no authenticated user, so we record
  the *attempted* identifier (email) in ``actor_email`` and leave ``actor`` null.
* **Source IP** respects ``X-Forwarded-For`` because the app runs behind the
  DigitalOcean App Platform proxy (see :func:`client_ip`).

Retention: there is no automatic purge of this table — auth/security events are
kept for the forensic/audit window. (Contrast the chat-trace table, which is
purged after ``CHAT_TRACE_RETENTION_DAYS``.) A formal retention period should be
set in the monitoring policy; until then these rows are retained indefinitely so
no security history is silently lost. If/when a retention limit is adopted,
implement it as a dedicated, reviewed management command — never a cascade.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.conf import settings
from django.db import models
from django.utils import timezone


security_logger = logging.getLogger("security")


class AuditEvent(models.Model):
    """One security-relevant event. Append-only — see module docstring."""

    class Event(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Login success"
        LOGIN_FAILURE = "login_failure", "Login failure"
        LOGIN_LOCKED_OUT = "login_locked_out", "Login blocked (locked out)"
        LOGOUT = "logout", "Logout"
        REGISTER = "register", "Registration"
        REGISTER_BLOCKED = "register_blocked", "Registration blocked (throttled)"
        PASSWORD_CHANGE = "password_change", "Password change"
        PROFILE_CHANGE = "profile_change", "Profile / email change"
        SETTINGS_CHANGE = "settings_change", "Settings / preferences change"
        TOS_ACCEPTED = "tos_accepted", "Terms of Service accepted"
        ONBOARDING_COMPLETED = "onboarding_completed", "Onboarding completed"
        API_KEY_CREATE = "api_key_create", "API key created"
        API_KEY_REVOKE = "api_key_revoke", "API key revoked"
        # Staff acting on ANOTHER user's account via /api/admin/users. The
        # actor is the staff member; the target lives in ``detail`` so the
        # trail answers "who changed whose account, and what changed".
        ADMIN_USER_CHANGE = "admin_user_change", "Admin changed a user account"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        BLOCKED = "blocked", "Blocked"

    # Null when there is no authenticated user (e.g. a failed login). We keep
    # the row even if the user is later deleted, so this is SET_NULL, not
    # CASCADE — losing the actor FK must not lose the audit record.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    # The identifier the actor presented (login email, target email on a
    # profile change). Survives actor deletion and covers the no-actor case.
    actor_email = models.CharField(max_length=254, blank=True)
    event_type = models.CharField(max_length=32, choices=Event.choices, db_index=True)
    outcome = models.CharField(
        max_length=16, choices=Outcome.choices, default=Outcome.SUCCESS
    )
    # UTC (USE_TZ is on); auto_now_add stamps insertion time.
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    # Small free-form bag for event-specific context (e.g. key prefix, the
    # failure count at lockout). Never put secrets/passwords in here.
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["actor_email", "created_at"]),
        ]

    def __str__(self) -> str:
        who = self.actor_email or (self.actor and self.actor.email) or "anonymous"
        return f"{self.created_at:%Y-%m-%dT%H:%M:%SZ} {self.event_type} {who} {self.outcome}"

    def save(self, *args, **kwargs):
        # Append-only: refuse to mutate an existing row. Inserts (no pk yet)
        # are fine; anything that would UPDATE is a programming error here.
        if self.pk is not None:
            raise RuntimeError("AuditEvent is append-only; existing rows cannot be modified")
        super().save(*args, **kwargs)


def client_ip(request) -> Optional[str]:
    """Best-effort source IP, honouring the DO App Platform proxy.

    App Platform terminates TLS and forwards the real client IP in
    ``X-Forwarded-For`` (left-most entry is the original client). ``REMOTE_ADDR``
    behind the proxy is the proxy itself, so prefer XFF when present. Returns
    ``None`` rather than raising on a malformed header so audit emission can
    never break the request path.
    """
    if request is None:
        return None
    meta = getattr(request, "META", {}) or {}
    xff = meta.get("HTTP_X_FORWARDED_FOR")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    addr = meta.get("REMOTE_ADDR")
    return addr or None


def _user_agent(request) -> str:
    if request is None:
        return ""
    return (getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT", "")[:400]


def record_event(
    *,
    event_type: str,
    request=None,
    actor=None,
    actor_email: str = "",
    outcome: str = AuditEvent.Outcome.SUCCESS,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Write one audit row and emit a structured ``security`` log line.

    Never raises: audit logging must not be able to break login/registration.
    A DB failure is swallowed after being logged so the underlying auth action
    still completes (the structured log line is the backstop record).
    """
    ip = client_ip(request)
    email = (actor_email or (getattr(actor, "email", "") or "")).strip().lower()
    try:
        AuditEvent.objects.create(
            actor=actor if getattr(actor, "pk", None) else None,
            actor_email=email,
            event_type=event_type,
            outcome=outcome,
            source_ip=ip,
            user_agent=_user_agent(request),
            detail=detail or {},
        )
    except Exception:  # pragma: no cover - defensive; never break auth
        security_logger.exception(
            "audit_write_failed", extra={"event_type": event_type}
        )

    # Structured log line regardless of DB success, so the security logger is a
    # durable second copy that survives even if the table write fails.
    security_logger.info(
        event_type,
        extra={
            "event": event_type,
            "outcome": outcome,
            "actor_email": email or None,
            "actor_id": getattr(actor, "pk", None),
            "source_ip": ip,
            **({"detail": detail} if detail else {}),
        },
    )
