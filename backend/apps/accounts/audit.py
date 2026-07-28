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
* **Source IP** is whatever :func:`client_ip` resolves — which is also the key
  every throttle and the login lockout in this app use, so a wrong answer here is
  not a cosmetic logging bug: it is a forged audit trail and a throttle that
  counts proxies instead of people. Production sits behind TWO appending proxies
  (Cloudflare in front of DigitalOcean App Platform, verified 2026-07-13), so the
  address is taken from a header Cloudflare overwrites rather than from a count of
  hops nobody has measured. See :func:`client_ip` for the full order of trust.

Retention: there is no automatic purge of this table — auth/security events are
kept for the forensic/audit window. (Contrast the chat-trace table, which is
purged after ``CHAT_TRACE_RETENTION_DAYS``.) A formal retention period should be
set in the monitoring policy; until then these rows are retained indefinitely so
no security history is silently lost. If/when a retention limit is adopted,
implement it as a dedicated, reviewed management command — never a cascade.
"""

from __future__ import annotations

import hmac
import ipaddress
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
        # Organization membership + invitations (apps.tenancy.services, and the
        # org REST API on top of it). The org and the affected member live in
        # ``detail``; the actor is whoever made the change.
        ORG_MEMBER_ADD = "org_member_add", "Org member added"
        ORG_MEMBER_REMOVE = "org_member_remove", "Org member removed"
        ORG_ROLE_CHANGE = "org_role_change", "Org member role changed"
        ORG_INVITE_CREATE = "org_invite_create", "Org invitation sent"
        ORG_INVITE_REVOKE = "org_invite_revoke", "Org invitation revoked"
        ORG_INVITE_ACCEPT = "org_invite_accept", "Org invitation accepted"
        ORG_UPDATE = "org_update", "Organization updated"
        # Hudson EDMSpro (apps.edms). The cloud connection is standing, offline
        # access to an attorney's document store, and a contribution is a client
        # document leaving their control — both are exactly the kind of consent
        # decision this trail exists to be able to reconstruct later.
        EDMS_CONNECT = "edms_connect", "EDMSpro cloud account connected"
        EDMS_DISCONNECT = "edms_disconnect", "EDMSpro cloud account disconnected"
        EDMS_OPT_IN = "edms_opt_in", "EDMSpro contribution opt-in enabled"
        EDMS_OPT_OUT = "edms_opt_out", "EDMSpro contribution opt-in disabled"
        EDMS_CONTRIBUTE = "edms_contribute", "EDMSpro filing contributed"
        EDMS_PURGE = "edms_purge", "EDMSpro contributions purged"

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


def _literal_ip(value: Optional[str]) -> Optional[str]:
    """The value if it parses as an IP literal, else None.

    ``AuditEvent.source_ip`` and ``ContactSubmission.ip`` are ``inet`` columns:
    handing them a header value that isn't an address is a 500 on INSERT, not a
    row. Anything reaching here can be attacker-typed, so it is checked, never
    assumed.
    """
    candidate = (value or "").strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


# The marketing lead endpoints, and ONLY these, may assert a client IP via
# X-Real-Client-IP (see _resolve below). Scoped as a path prefix because the
# token that authorises it is a shared secret on a second app: if it ever leaks,
# the blast radius must stop at the lead funnel and must NOT extend to the login
# lockout or the audit trail, where "assert an arbitrary source IP" is precisely
# the forgery this module exists to prevent.
_MARKETING_PATH_PREFIX = "/api/marketing/"


def _request_path(request) -> str:
    path = getattr(request, "path", None)
    if not path:
        path = (getattr(request, "META", {}) or {}).get("PATH_INFO", "") or ""
    return path if isinstance(path, str) else ""


def _marketing_token_ok(request) -> bool:
    """Whether this request carries the marketing site's shared secret.

    ``hmac.compare_digest`` on two ``str`` raises ``TypeError`` the moment either
    side holds a character above U+007F — and Django decodes request headers as
    ISO-8859-1, so a single high byte in ``X-Marketing-Proxy-Token`` produces
    exactly that. Since ``client_ip`` runs on every login attempt (django-axes)
    and inside ``record_event``, that TypeError was a 500 on login, registration
    and the lead forms, reachable by any unauthenticated caller, latent only
    while ``MARKETING_PROXY_TOKEN`` is unset. Compare BYTES, and never raise.

    The token is expected to be ASCII (it is a secret we mint). A non-ASCII one
    simply will not match — which is the safe outcome, not a crash.
    """
    expected = getattr(settings, "MARKETING_PROXY_TOKEN", "") or ""
    presented = (getattr(request, "META", {}) or {}).get(
        "HTTP_X_MARKETING_PROXY_TOKEN", ""
    ) or ""
    if not expected or not presented:
        return False
    try:
        return hmac.compare_digest(
            presented.encode("utf-8", "replace"), expected.encode("utf-8", "replace")
        )
    except (AttributeError, TypeError, ValueError, UnicodeError):
        return False


def _trusted_hops() -> int:
    """How many trailing ``X-Forwarded-For`` entries our own infrastructure wrote."""
    try:
        return max(1, int(getattr(settings, "TRUSTED_PROXY_COUNT", 1)))
    except (TypeError, ValueError):
        return 1


def _resolve(request) -> Optional[str]:
    meta = getattr(request, "META", {}) or {}

    # (a) The marketing site's server-side route handlers. They call this API
    #     from a container, so the connection we see is THEIRS — the visitor's
    #     address survives only because the handler copies it into a dedicated
    #     header and proves the copy is ours with a shared secret. Both halves
    #     are required, and so is the path: a leaked token must not buy anyone
    #     the ability to assert a source IP against /api/auth/login.
    #
    #     This branch is deliberately ABOVE Cloudflare: on a proxied lead,
    #     CF-Connecting-IP is the MARKETING CONTAINER's egress address (Cloudflare
    #     sees the container as the client), so trusting CF first would key every
    #     lead on earth to one address — the exact bug this replaces.
    if _marketing_token_ok(request) and _request_path(request).startswith(
        _MARKETING_PATH_PREFIX
    ):
        ip = _literal_ip(meta.get("HTTP_X_REAL_CLIENT_IP"))
        if ip:
            return ip

    # (b) Cloudflare. Production is orange-clouded (verified 2026-07-13: A records
    #     are Cloudflare anycast, NS is *.ns.cloudflare.com, and responses carry
    #     server: cloudflare + cf-ray ALONGSIDE x-do-app-origin). Cloudflare
    #     OVERWRITES CF-Connecting-IP on ingress, so unlike X-Forwarded-For a
    #     client cannot forge it — and unlike a hop count it does not depend on
    #     how many appending proxies are in the chain, which is the property that
    #     makes it the right control here. Off by default: it is only unforgeable
    #     where Cloudflare is genuinely in front (see TRUST_CF_CONNECTING_IP).
    if getattr(settings, "TRUST_CF_CONNECTING_IP", False):
        ip = _literal_ip(meta.get("HTTP_CF_CONNECTING_IP"))
        if ip:
            return ip

    # (c) X-Forwarded-For, counted from the right. Each proxy APPENDS the address
    #     it accepted the connection from, so a forged "X-Forwarded-For: 1.2.3.4"
    #     arrives as "1.2.3.4, <real>": the left is what the caller typed and only
    #     the last TRUSTED_PROXY_COUNT entries were written by infrastructure we
    #     run. Reading the left-most (as this did until 2026-07) hands anyone a
    #     fresh throttle bucket per request and lets them forge their address in
    #     this very audit trail (SECURITY_AUDIT_2026-07 finding #5).
    #
    #     A header too short to have come through our full chain is not a header
    #     we can reason about, so it is discarded in favour of REMOTE_ADDR —
    #     degrading to a proxy's own address, never to a value the caller supplied.
    hops = _trusted_hops()
    forwarded = [
        entry.strip()
        for entry in (meta.get("HTTP_X_FORWARDED_FOR") or "").split(",")
        if entry.strip()
    ]
    if len(forwarded) >= hops:
        ip = _literal_ip(forwarded[-hops])
        if ip:
            return ip
    return _literal_ip(meta.get("REMOTE_ADDR"))


def client_ip(request) -> Optional[str]:
    """Who the client is — the one answer every IP-keyed control here depends on.

    Resolved in descending order of how hard the value is to forge:

    (a) ``X-Real-Client-IP``, but ONLY with a valid ``X-Marketing-Proxy-Token``
        AND only on ``/api/marketing/*``. The marketing site relays leads
        server-side, so the visitor's address cannot survive as a connection
        property; it is carried explicitly and authenticated instead. Hop
        arithmetic does not enter into it.
    (b) ``CF-Connecting-IP``, when ``TRUST_CF_CONNECTING_IP`` is on. Cloudflare
        overwrites this header on ingress, so a browser cannot forge it, and it
        is independent of how many proxies append to X-Forwarded-For.
    (c) The ``X-Forwarded-For`` chain, counted from the right by
        ``TRUSTED_PROXY_COUNT``, then ``REMOTE_ADDR``.

    Returns ``None`` rather than raising, on any shape of input — including a
    header crafted to blow up the comparison in (a). Audit emission and the login
    path both call this, and neither may be breakable by a header a stranger sent.
    """
    if request is None:
        return None
    try:
        return _resolve(request)
    except Exception:  # pragma: no cover - defensive; never break auth/audit
        security_logger.exception("client_ip_failed")
        return None


def proxy_chain_shape(request) -> dict[str, Any]:
    """What the proxy chain LOOKED like, for one request — a measurement, not a control.

    ``TRUSTED_PROXY_COUNT`` is the one value here that cannot be verified from
    outside the app: nothing echoes the origin-side headers, which is exactly how
    a confidently-wrong hop count ("App Platform is a single edge hop") shipped in
    the first place. These two fields ride along on the security log line, so the
    true shape is readable off any real request in prod instead of guessed:

        xff_len     — how many entries X-Forwarded-For actually arrived with
        cf_ip       — whether Cloudflare stamped CF-Connecting-IP at all

    Never raises, and never logs the addresses themselves (``source_ip`` is
    already the attributed one); this is a count and a boolean.
    """
    try:
        meta = (getattr(request, "META", {}) or {}) if request is not None else {}
        raw = meta.get("HTTP_X_FORWARDED_FOR") or ""
        return {
            "xff_len": len([e for e in raw.split(",") if e.strip()]),
            "cf_ip": bool(meta.get("HTTP_CF_CONNECTING_IP")),
        }
    except Exception:  # pragma: no cover - defensive
        return {}


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
            # How the chain actually looked, so TRUSTED_PROXY_COUNT can be read
            # off prod rather than guessed. See proxy_chain_shape.
            **proxy_chain_shape(request),
            **({"detail": detail} if detail else {}),
        },
    )
