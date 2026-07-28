"""Shared EDMSpro operations that are not HTTP handlers.

Kept out of ``api.py`` so the management commands and the ``pre_delete``
receiver run the same code the endpoints do — a purge that behaves differently
depending on whether a human or a cron triggered it is a compliance answer we
could not stand behind.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import AuditEvent, record_event

from . import storage
from .models import CloudIntegration, CrowdsourceArtifact, EdmsSettings, Provider

logger = logging.getLogger(__name__)


def get_or_create_settings(user) -> EdmsSettings:
    """The user's EDMSpro settings row, created with defaults on first touch.

    There is no post-save signal creating these: most accounts will never use
    EDMSpro, and a table of empty rows for every user is worse than a
    get_or_create on the handful of endpoints that need one."""
    row, _ = EdmsSettings.objects.get_or_create(user=user)
    return row


def get_integration(user, provider: str = Provider.ONEDRIVE) -> CloudIntegration | None:
    return CloudIntegration.objects.filter(user=user, provider=provider).first()


def disconnect(user, provider: str = Provider.ONEDRIVE, *, request=None) -> bool:
    """Drop the stored tokens for a provider. Returns whether anything existed.

    The row is deleted rather than blanked: "connected but with no usable token"
    is a state with no meaning to the user, and leaving encrypted material
    around after someone has explicitly asked us to forget it is the wrong
    default. Microsoft-side consent is revoked by the user at
    account.live.com — we cannot do it for them, and the SPA says so."""
    integration = get_integration(user, provider)
    if integration is None:
        return False
    account = integration.account_email
    integration.delete()
    record_event(
        event_type=AuditEvent.Event.EDMS_DISCONNECT,
        request=request,
        actor=user,
        detail={"provider": provider, "account": account},
    )
    return True


@transaction.atomic
def purge_user_contributions(user, *, mark_purged: bool = True, request=None) -> int:
    """Delete every object this user contributed, from the bucket and the index.

    Called on account deletion (via the ``pre_delete`` receiver, with
    ``mark_purged=False`` — the cascade removes the rows a moment later) and by
    the ``purge_crowdsource`` management command.

    A storage failure propagates on purpose. Inside the deletion transaction
    that aborts the whole delete, which is the only outcome that keeps the index
    and the bucket telling the same story: silently continuing would leave
    unattributable client documents in a bucket while the record of whose they
    were disappears."""
    rows = list(
        CrowdsourceArtifact.objects.filter(
            submitted_by=user, status=CrowdsourceArtifact.Status.STORED
        )
    )
    if not rows:
        return 0
    storage.delete_objects([r.object_key for r in rows])
    if mark_purged:
        CrowdsourceArtifact.objects.filter(pk__in=[r.pk for r in rows]).update(
            status=CrowdsourceArtifact.Status.PURGED, purged_at=timezone.now()
        )
    record_event(
        event_type=AuditEvent.Event.EDMS_PURGE,
        request=request,
        actor=user,
        detail={"artifacts": len(rows)},
    )
    return len(rows)
