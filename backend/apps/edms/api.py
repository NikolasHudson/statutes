"""``/api/edms`` — Hudson EDMSpro's HTTP surface.

The shape of this router follows from the custody model (see
:mod:`apps.edms.models`): the server orchestrates, the client moves bytes.

    extension                     this router                    Microsoft
    ─────────                     ───────────                    ─────────
    POST /route  (metadata) ──▶   resolve folder + filename
                                  ensure the folder exists  ──▶
                                  mint an upload session    ──▶
              ◀── upload_url
    PUT bytes ──────────────────────────────────────────────▶  (never via us)
    POST /sync/{id}/complete ─▶   re-read the item          ──▶
                                  mark success

Two rules are enforced here and asserted by test, because they are the product
promises rather than implementation details:

1. **Enabling the contribution opt-in is session-only.** A Bearer or API-key
   caller can read the flag and can turn it *off*; only a browser session — that
   is, the SPA consent screen — can turn it on. Nothing headless gets to enroll
   an attorney into sharing client documents.
2. **The safety filter is server-side.** The extension runs the same check for
   UX, but confidential case types are refused here, on the intake path, opt-in
   or not.

Everything is gated on the ``edms`` plan feature. The 402 wording comes from the
same place the rest of the API's paywall does, so a lapsed subscriber gets one
consistent story across surfaces.

**v1 ships without cloud saving.** The diagram above is the v2 product. v1 of
the extension downloads the filing to the user's own machine, named from the
template it reads off ``GET /settings`` — no OneDrive, no ``/route``, no upload
session. That code is *not* deleted (models, migrations and the
``ms_oauth``/``onedrive``/``storage`` modules are all intact and still tested);
it is moved onto :data:`cloud_router` below, which is mounted but answers 404
for everything while ``settings.EDMS_CLOUD_ENABLED`` is False — the default.
Setting ``EDMS_CLOUD_ENABLED=True`` restores the whole feature with no code
change. Three routes stay ungated because v1 needs them: ``GET``/``PATCH
/settings`` (the naming template, and the contribution opt-in, which remains a
live user preference) and ``GET /safety``.
"""

from __future__ import annotations

import datetime as dt
import functools
import logging

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.utils import timezone
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from apps.accounts.audit import AuditEvent, record_event
from apps.api.session_auth import session_auth
from core.brand import EDMS_PRODUCT_NAME

from . import ms_oauth, onedrive, safety, services, storage
from .auth import EDMS_AUTH, caller, enforce_upload_quota, require_edms
from .models import (
    DEFAULT_CASE_FOLDER_TEMPLATE,
    DEFAULT_NAMING_TEMPLATE,
    CaseFolderMapping,
    CloudIntegration,
    CrowdsourceArtifact,
    FilingSync,
    Provider,
)
from .routing import FILENAME_TOKENS, FOLDER_TOKENS, FilingMeta, resolve_destination

logger = logging.getLogger(__name__)

edms_router = Router(tags=["edms"], auth=EDMS_AUTH)

# The v2 cloud-saving surface. Same auth and same plan gate as the rest of the
# router (it inherits ``auth``/``tags`` from the mount at the bottom of this
# module); the only difference is that every operation on it is invisible while
# ``EDMS_CLOUD_ENABLED`` is off. Nothing that v1 needs may be registered here.
cloud_router = Router(auth=EDMS_AUTH)


def _cloud_only(run):
    """Hide a :data:`cloud_router` operation while ``EDMS_CLOUD_ENABLED`` is off.

    Registered with ninja's ``mode="view"`` decorator hook, which wraps
    ``Operation.run`` — i.e. this lands *ahead of* authentication, response
    validation and the plan check. That ordering is the point: raising
    :class:`~django.http.Http404` from here produces Django's ordinary 404, the
    byte-identical response an unregistered path gets, so an unauthenticated
    probe of ``/api/edms/route`` cannot tell a disabled feature from a URL that
    was never there. Refusing inside the handler instead would answer 401 to the
    same probe and confirm the route exists.
    """

    @functools.wraps(run)
    def wrapper(request, *args, **kwargs):
        if not getattr(settings, "EDMS_CLOUD_ENABLED", False):
            raise Http404("EDMSpro cloud saving is not enabled.")
        return run(request, *args, **kwargs)

    return wrapper


cloud_router.add_decorator(_cloud_only, mode="view")


class _CloudInSchema:
    """The same flag, for ``include_in_schema``.

    ``/api/openapi.json`` is served unauthenticated and ninja re-reads
    ``include_in_schema`` truthily each time it renders the document, so a lazy
    object keeps the published spec in step with what the router will actually
    answer. A static ``True`` here would have the public API docs list thirteen
    endpoints that 404 — exactly the disclosure the pre-auth 404 exists to
    prevent, just through the other door."""

    def __bool__(self) -> bool:
        return bool(getattr(settings, "EDMS_CLOUD_ENABLED", False))


CLOUD_IN_SCHEMA = _CloudInSchema()

# Where the OAuth callback lands the browser when it is done.
SETTINGS_PATH = "/account/edms"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConnectionOut(Schema):
    """Everything the SPA needs to render the Connection section, including the
    two failure states that are not "disconnected": the platform has no Azure
    app registration at all (``configured=False``), and the stored token has
    gone stale (``needs_reconnect``)."""

    configured: bool
    connected: bool
    provider: str = ""
    account_email: str = ""
    account_name: str = ""
    needs_reconnect: bool = False
    connected_at: dt.datetime | None = None


class SettingsOut(Schema):
    cloud_provider: str
    default_destination_folder_id: str
    default_destination_path: str
    naming_template: str
    case_folder_template: str
    crowdsource_opt_in: bool
    crowdsource_opt_in_at: dt.datetime | None
    connection: ConnectionOut
    folder_tokens: list[str]
    filename_tokens: list[str]


class UpdateSettingsRequest(Schema):
    """Every field optional; only what is sent is written (``exclude_unset``)."""

    default_destination_folder_id: str | None = None
    default_destination_path: str | None = None
    naming_template: str | None = None
    case_folder_template: str | None = None
    crowdsource_opt_in: bool | None = None


class FolderOut(Schema):
    id: str
    name: str
    path: str
    child_count: int = 0
    web_url: str = ""


class FolderListOut(Schema):
    parent: dict
    folders: list[FolderOut]


class CreateFolderRequest(Schema):
    parent_id: str = "root"
    name: str


class CaseFolderOut(Schema):
    case_number: str
    folder_id: str
    folder_path: str
    naming_template: str


class CaseFolderRequest(Schema):
    folder_id: str = ""
    folder_path: str = ""
    naming_template: str = ""


class RouteRequest(Schema):
    """Docket metadata only — deliberately no file, no URL to fetch, nothing
    that would put a document in this process."""

    case_number: str
    case_type: str = ""
    docket_num: str = ""
    cms_doc_id: str = ""
    doc_title: str = ""
    doc_type: str = ""
    row_date: dt.date | None = None
    filer: str = ""
    county: str = ""
    judge: str = ""


class RouteResponse(Schema):
    sync_id: int
    upload_url: str
    folder_path: str
    filename: str
    expires_at: dt.datetime | None = None
    # Whether the extension may additionally POST this document to /crowdsource.
    # Computed server-side (opt-in AND not a confidential case type) so the
    # client never has to decide; the intake path re-checks anyway.
    crowdsource_eligible: bool = False


class CompleteRequest(Schema):
    item_id: str = ""
    byte_size: int | None = None


class FailRequest(Schema):
    error: str = ""


class SyncOut(Schema):
    id: int
    case_number: str
    docket_num: str
    # The court's own document id. The extension keys its "already saved" map on
    # this to decide which docket rows still need a save button, so it has to
    # come back out even though nothing else reads it.
    cms_doc_id: str
    doc_title: str
    doc_type: str
    row_date: dt.date | None
    status: str
    provider: str
    destination_path: str
    destination_filename: str
    cloud_item_id: str
    cloud_web_url: str
    error: str
    byte_size: int | None
    created_at: dt.datetime
    completed_at: dt.datetime | None


class SyncListOut(Schema):
    results: list[SyncOut]
    total: int


class SafetyOut(Schema):
    blocked: list[dict]
    note: str


class ContributeQuery(Schema):
    """Metadata rides in the query string because the body IS the PDF.

    A multipart form would make Django buffer the upload (to memory, then to the
    ephemeral container disk) before we ever saw it — precisely the thing the
    streaming intake exists to avoid."""

    case_number: str
    case_type: str = ""
    doc_type: str = ""
    doc_title: str = ""
    county: str = ""
    row_date: dt.date | None = None
    sync_id: int | None = None


class ContributeOut(Schema):
    artifact_id: str
    byte_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connection_out(user) -> ConnectionOut:
    integration = services.get_integration(user)
    if integration is None:
        return ConnectionOut(configured=ms_oauth.is_configured(), connected=False)
    return ConnectionOut(
        configured=ms_oauth.is_configured(),
        connected=True,
        provider=integration.provider,
        account_email=integration.account_email,
        account_name=integration.account_name,
        needs_reconnect=integration.needs_reconnect,
        connected_at=integration.connected_at,
    )


def _settings_out(user) -> SettingsOut:
    row = services.get_or_create_settings(user)
    return SettingsOut(
        cloud_provider=row.cloud_provider,
        default_destination_folder_id=row.default_destination_folder_id,
        default_destination_path=row.default_destination_path,
        naming_template=row.naming_template,
        case_folder_template=row.case_folder_template,
        crowdsource_opt_in=row.crowdsource_opt_in,
        crowdsource_opt_in_at=row.crowdsource_opt_in_at,
        connection=_connection_out(user),
        folder_tokens=list(FOLDER_TOKENS),
        filename_tokens=list(FILENAME_TOKENS),
    )


def _sync_out(row: FilingSync) -> SyncOut:
    return SyncOut(
        id=row.id,
        case_number=row.case_number,
        docket_num=row.docket_num,
        cms_doc_id=row.cms_doc_id,
        doc_title=row.doc_title,
        doc_type=row.doc_type,
        row_date=row.row_date,
        status=row.status,
        provider=row.provider,
        destination_path=row.destination_path,
        destination_filename=row.destination_filename,
        cloud_item_id=row.cloud_item_id,
        cloud_web_url=row.cloud_web_url,
        error=row.error,
        byte_size=row.byte_size,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _require_integration(user) -> CloudIntegration:
    integration = services.get_integration(user)
    if integration is None:
        raise HttpError(
            409, "OneDrive is not connected. Connect it in Account → EDMSpro."
        )
    return integration


def _graph(fn, *args, **kwargs):
    """Run a Graph call, mapping its failure modes onto honest HTTP statuses.

    Worth being precise about, because these three mean very different things to
    the extension: 409 = stop and tell the user to reconnect; 503 = we were
    throttled, retry later; 502 = Microsoft refused this specific operation and
    retrying will not help."""
    try:
        return fn(*args, **kwargs)
    except onedrive.OneDriveAuthError as exc:
        raise HttpError(409, str(exc)) from exc
    except onedrive.OneDriveRetryableError as exc:
        raise HttpError(
            503, "OneDrive is throttling or unavailable. Try again shortly."
        ) from exc
    except onedrive.OneDriveTerminalError as exc:
        logger.warning("edms: graph terminal error %s: %s", exc.status_code, exc.body[:200])
        raise HttpError(502, f"OneDrive rejected the request ({exc.status_code}).") from exc
    except onedrive.OneDriveError as exc:
        raise HttpError(502, str(exc)) from exc


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@edms_router.get("/settings", response=SettingsOut)
def get_settings(request):
    who = require_edms(request)
    return _settings_out(who.user)


@edms_router.patch("/settings", response=SettingsOut)
def update_settings(request, payload: UpdateSettingsRequest):
    """Update EDMSpro preferences.

    ``crowdsource_opt_in`` is the one field with an asymmetric rule: enabling it
    requires a session (the SPA consent screen), disabling it is allowed from
    any authenticated caller. That asymmetry is the point — sharing a client's
    filings must be a deliberate act taken while reading the explanation, while
    stopping must be possible from wherever the user happens to be."""
    who = require_edms(request)
    row = services.get_or_create_settings(who.user)
    data = payload.dict(exclude_unset=True)

    opt_in = data.pop("crowdsource_opt_in", None)
    for field, value in data.items():
        if value is None:
            continue
        setattr(row, field, value.strip() if isinstance(value, str) else value)

    # Empty templates fall back to the defaults rather than being stored blank —
    # a blank naming template would render every filing to the same filename.
    row.naming_template = row.naming_template or DEFAULT_NAMING_TEMPLATE
    row.case_folder_template = row.case_folder_template or DEFAULT_CASE_FOLDER_TEMPLATE

    if opt_in is not None and opt_in != row.crowdsource_opt_in:
        if opt_in and not who.is_session:
            raise HttpError(
                403,
                "Contribution sharing can only be enabled from the EDMSpro "
                "settings page, where the consent explanation is shown.",
            )
        row.crowdsource_opt_in = opt_in
        row.crowdsource_opt_in_at = timezone.now() if opt_in else None
        record_event(
            event_type=(
                AuditEvent.Event.EDMS_OPT_IN if opt_in else AuditEvent.Event.EDMS_OPT_OUT
            ),
            request=request,
            actor=who.user,
            detail={"via": who.kind},
        )
    row.save()
    return _settings_out(who.user)


@edms_router.get("/safety", response=SafetyOut)
def get_safety(request):
    """The blocked case types, served to both the SPA and the extension so the
    enforced list and the advertised list are the same list."""
    require_edms(request)
    return SafetyOut(
        blocked=safety.safety_list(),
        note=(
            "Filings in these case types are never shared, regardless of your "
            "contribution setting."
        ),
    )


# ---------------------------------------------------------------------------
# OneDrive connection
# ---------------------------------------------------------------------------


@cloud_router.get("/integrations/onedrive/authorize", auth=session_auth)
def onedrive_authorize(request):
    """Start the Microsoft consent flow. Browser-only, by design.

    The state is bound to this Django session (not the cache — production has no
    Redis, so a cache-stashed state would live in one gunicorn worker's memory
    and be missing when Microsoft redirects to a different one)."""
    who = require_edms(request)
    if not ms_oauth.is_configured():
        raise HttpError(503, "Cloud storage integration is not configured on this deployment.")
    state = ms_oauth.new_state(request.session)
    return {"authorize_url": ms_oauth.authorize_url(state)}


@cloud_router.get("/integrations/onedrive/callback", auth=None)
def onedrive_callback(request, code: str = "", state: str = "", error: str = ""):
    """Microsoft's redirect target. Ends by bouncing the browser back to the
    settings page with a status in the query string — the user is looking at a
    tab, not reading JSON."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return HttpResponseRedirect(f"{SETTINGS_PATH}?connected=signin")
    if not ms_oauth.consume_state(request.session, state):
        return HttpResponseRedirect(f"{SETTINGS_PATH}?connected=state")
    if error or not code:
        return HttpResponseRedirect(f"{SETTINGS_PATH}?connected=denied")

    try:
        bundle = ms_oauth.exchange_code(code)
    except ms_oauth.MicrosoftOAuthError:
        logger.warning("edms: OneDrive code exchange failed for user %s", user.pk)
        return HttpResponseRedirect(f"{SETTINGS_PATH}?connected=failed")

    integration, _ = CloudIntegration.objects.get_or_create(
        user=user, provider=Provider.ONEDRIVE
    )
    integration.access_token = bundle.access_token
    integration.refresh_token = bundle.refresh_token
    integration.expires_at = bundle.expires_at
    integration.account_email = bundle.account_email
    integration.account_name = bundle.account_name
    integration.needs_reconnect = False
    integration.last_error = ""
    integration.save()

    settings_row = services.get_or_create_settings(user)
    if not settings_row.cloud_provider:
        settings_row.cloud_provider = Provider.ONEDRIVE
        settings_row.save(update_fields=["cloud_provider", "updated_at"])

    record_event(
        event_type=AuditEvent.Event.EDMS_CONNECT,
        request=request,
        actor=user,
        detail={"provider": Provider.ONEDRIVE, "account": bundle.account_email},
    )
    return HttpResponseRedirect(f"{SETTINGS_PATH}?connected=1")


@cloud_router.delete("/integrations/onedrive", response=ConnectionOut)
def onedrive_disconnect(request):
    who = require_edms(request)
    services.disconnect(who.user, Provider.ONEDRIVE, request=request)
    return _connection_out(who.user)


@cloud_router.get("/integrations/onedrive/folders", response=FolderListOut)
def onedrive_folders(request, parent_id: str = "root"):
    who = require_edms(request)
    integration = _require_integration(who.user)
    return _graph(onedrive.list_child_folders, integration, parent_id)


@cloud_router.post("/integrations/onedrive/folders", response=FolderOut)
def onedrive_create_folder(request, payload: CreateFolderRequest):
    who = require_edms(request)
    integration = _require_integration(who.user)
    if not payload.name.strip():
        raise HttpError(400, "Folder name is required.")
    return _graph(
        onedrive.create_child_folder, integration, payload.parent_id, payload.name
    )


# ---------------------------------------------------------------------------
# Per-case overrides
# ---------------------------------------------------------------------------


@cloud_router.get("/case-folders/{case_number}", response=CaseFolderOut)
def get_case_folder(request, case_number: str):
    """The per-case override, or an empty one — the extension's gear popover
    renders the same form either way, so "no override yet" is not a 404."""
    who = require_edms(request)
    row = CaseFolderMapping.objects.filter(
        user=who.user, case_number=case_number
    ).first()
    if row is None:
        return CaseFolderOut(
            case_number=case_number, folder_id="", folder_path="", naming_template=""
        )
    return CaseFolderOut(
        case_number=row.case_number,
        folder_id=row.folder_id,
        folder_path=row.folder_path,
        naming_template=row.naming_template,
    )


@cloud_router.put("/case-folders/{case_number}", response=CaseFolderOut)
def put_case_folder(request, case_number: str, payload: CaseFolderRequest):
    who = require_edms(request)
    row, _ = CaseFolderMapping.objects.update_or_create(
        user=who.user,
        case_number=case_number,
        defaults={
            "provider": Provider.ONEDRIVE,
            "folder_id": payload.folder_id.strip(),
            "folder_path": payload.folder_path.strip(),
            "naming_template": payload.naming_template.strip(),
        },
    )
    return CaseFolderOut(
        case_number=row.case_number,
        folder_id=row.folder_id,
        folder_path=row.folder_path,
        naming_template=row.naming_template,
    )


@cloud_router.delete("/case-folders/{case_number}", response={200: dict})
def delete_case_folder(request, case_number: str):
    who = require_edms(request)
    deleted, _ = CaseFolderMapping.objects.filter(
        user=who.user, case_number=case_number
    ).delete()
    return {"deleted": bool(deleted)}


# ---------------------------------------------------------------------------
# The save flow
# ---------------------------------------------------------------------------


@cloud_router.post("/route", response=RouteResponse)
def route(request, payload: RouteRequest):
    """Resolve the destination and mint a per-file upload URL.

    This is the whole server side of a save. It never sees the document; it
    decides where the document belongs, makes sure that folder exists, and asks
    Microsoft for a URL the extension can PUT to. The ``FilingSync`` row is
    written before the URL is returned so an upload that is started and then
    abandoned still leaves a trace the user can see and retry."""
    who = require_edms(request)
    if not payload.case_number.strip():
        raise HttpError(400, "case_number is required.")
    enforce_upload_quota(who.user)
    integration = _require_integration(who.user)

    meta = FilingMeta(
        case_number=payload.case_number.strip(),
        case_type=payload.case_type,
        docket_num=payload.docket_num,
        doc_title=payload.doc_title,
        doc_type=payload.doc_type,
        row_date=payload.row_date,
        filer=payload.filer,
        county=payload.county,
        judge=payload.judge,
    )
    destination = resolve_destination(who.user, meta)

    _graph(onedrive.ensure_folder_path, integration, destination.folder_path)
    session = _graph(
        onedrive.create_upload_session,
        integration,
        folder_path=destination.folder_path,
        filename=destination.filename,
    )
    integration.mark_healthy()

    sync = FilingSync.objects.create(
        user=who.user,
        case_number=meta.case_number,
        case_type=meta.case_type,
        docket_num=meta.docket_num,
        cms_doc_id=payload.cms_doc_id,
        doc_title=meta.doc_title,
        doc_type=meta.doc_type,
        row_date=meta.row_date,
        filer=meta.filer,
        county=meta.county,
        judge=meta.judge,
        provider=Provider.ONEDRIVE,
        status=FilingSync.Status.PENDING_UPLOAD,
        destination_path=session.folder_path,
        destination_filename=session.filename,
        upload_expires_at=session.expires_at,
    )

    settings_row = services.get_or_create_settings(who.user)
    eligible = settings_row.crowdsource_opt_in and not safety.is_blocked(meta.case_number)

    return RouteResponse(
        sync_id=sync.id,
        upload_url=session.upload_url,
        folder_path=session.folder_path,
        filename=session.filename,
        expires_at=session.expires_at,
        crowdsource_eligible=eligible,
    )


@cloud_router.post("/sync/{int:sync_id}/complete", response=SyncOut)
def complete_sync(request, sync_id: int, payload: CompleteRequest):
    """Mark a save successful — after checking with Microsoft ourselves.

    The client reports the item id it got back from the final chunk; we read
    that item from Graph before believing it. If the id is missing we fall back
    to a path lookup, which can legitimately miss (Graph may have renamed the
    file on a collision), and an unverifiable save is recorded as failed rather
    than as a success we cannot stand behind."""
    who = require_edms(request)
    sync = FilingSync.objects.filter(pk=sync_id, user=who.user).first()
    if sync is None:
        raise HttpError(404, "Unknown sync.")
    if sync.status == FilingSync.Status.SUCCESS:
        return _sync_out(sync)

    integration = _require_integration(who.user)
    item = None
    if payload.item_id:
        item = _graph(onedrive.get_item, integration, payload.item_id)
    if item is None:
        item = _graph(
            onedrive.get_item_by_path,
            integration,
            sync.destination_path,
            sync.destination_filename,
        )
    if item is None:
        sync.status = FilingSync.Status.FAILED
        sync.error = "Upload could not be confirmed in OneDrive."
        sync.completed_at = timezone.now()
        sync.save(update_fields=["status", "error", "completed_at"])
        raise HttpError(409, sync.error)

    sync.status = FilingSync.Status.SUCCESS
    sync.error = ""
    sync.cloud_item_id = item.item_id
    sync.cloud_web_url = item.web_url
    sync.destination_filename = item.name or sync.destination_filename
    sync.byte_size = item.size or payload.byte_size
    sync.completed_at = timezone.now()
    sync.save(
        update_fields=[
            "status",
            "error",
            "cloud_item_id",
            "cloud_web_url",
            "destination_filename",
            "byte_size",
            "completed_at",
        ]
    )
    return _sync_out(sync)


@cloud_router.post("/sync/{int:sync_id}/fail", response=SyncOut)
def fail_sync(request, sync_id: int, payload: FailRequest):
    """Record a client-side upload failure so the history shows what happened
    instead of a row stuck on "pending" forever."""
    who = require_edms(request)
    sync = FilingSync.objects.filter(pk=sync_id, user=who.user).first()
    if sync is None:
        raise HttpError(404, "Unknown sync.")
    if sync.status != FilingSync.Status.SUCCESS:
        sync.status = FilingSync.Status.FAILED
        sync.error = (payload.error or "Upload failed.")[:1000]
        sync.completed_at = timezone.now()
        sync.save(update_fields=["status", "error", "completed_at"])
    return _sync_out(sync)


@cloud_router.get("/syncs", response=SyncListOut)
def list_syncs(
    request,
    status: str = "",
    case_number: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    who = require_edms(request)
    qs = FilingSync.objects.filter(user=who.user)
    if status:
        qs = qs.filter(status=status)
    if case_number:
        qs = qs.filter(case_number__icontains=case_number)
    total = qs.count()
    rows = list(qs[offset:offset + limit])
    return SyncListOut(results=[_sync_out(r) for r in rows], total=total)


# ---------------------------------------------------------------------------
# Crowdsource intake — write-only, opt-in, streaming
# ---------------------------------------------------------------------------


@cloud_router.post("/crowdsource", response={201: ContributeOut})
def contribute(request, meta: ContributeQuery = Query(...)):
    """Accept one opted-in PDF and stream it to the private bucket. Then stop.

    There is no step after this. No processing, no redaction, no library, no
    corpus ingestion, no read endpoint — the bucket is inert until a
    contribution policy exists. The row written here is what makes the bucket
    purgeable on request; it is not an index anything reads.

    The request body is the PDF, streamed straight through
    :func:`apps.edms.storage.stream_to_bucket`; it is never assembled in memory
    and never written to the container's disk."""
    who = require_edms(request)
    settings_row = services.get_or_create_settings(who.user)
    if not settings_row.crowdsource_opt_in:
        raise HttpError(403, "Contribution sharing is turned off for this account.")

    reason = safety.blocked_reason(meta.case_number)
    if reason:
        raise HttpError(403, f"{reason} filings are never shared.")

    content_type = (request.META.get("CONTENT_TYPE") or "").split(";")[0].strip().lower()
    if content_type != "application/pdf":
        raise HttpError(415, "Send the filing as a raw application/pdf body.")

    declared = request.META.get("CONTENT_LENGTH") or ""
    if declared.isdigit() and int(declared) > storage.MAX_UPLOAD_BYTES:
        raise HttpError(413, "That filing is larger than the 40MB contribution limit.")

    if not storage.is_configured():
        raise HttpError(503, "Contribution storage is not configured on this deployment.")

    key = storage.object_key(who.user.pk)
    try:
        stored = storage.stream_to_bucket(request, key=key, content_type="application/pdf")
    except storage.PayloadTooLarge as exc:
        raise HttpError(413, str(exc)) from exc
    except storage.StorageNotConfigured as exc:  # pragma: no cover - checked above
        raise HttpError(503, str(exc)) from exc

    with transaction.atomic():
        artifact = CrowdsourceArtifact.objects.create(
            submitted_by=who.user,
            bucket=stored.bucket,
            object_key=stored.key,
            byte_size=stored.byte_size,
            content_type="application/pdf",
            sha256=stored.sha256,
            case_number=meta.case_number,
            case_type=meta.case_type,
            doc_type=meta.doc_type,
            doc_title=meta.doc_title,
            county=meta.county,
            row_date=meta.row_date,
            safety_flags={"blocked_prefix_check": "passed", "product": EDMS_PRODUCT_NAME},
        )
    record_event(
        event_type=AuditEvent.Event.EDMS_CONTRIBUTE,
        request=request,
        actor=who.user,
        detail={
            "artifact": str(artifact.id),
            "case_type": meta.case_type,
            "doc_type": meta.doc_type,
            "bytes": stored.byte_size,
        },
    )
    return 201, ContributeOut(artifact_id=str(artifact.id), byte_size=stored.byte_size)


# ---------------------------------------------------------------------------
# Mount the v2 surface
# ---------------------------------------------------------------------------
# Empty prefix: the cloud routes are siblings of /settings and /safety under
# /api/edms, not a sub-path. They are mounted unconditionally and gated per
# request instead of at import, so the flag is a *setting* — one that a test
# can flip with override_settings and an operator can flip with an env var —
# rather than a fact frozen into the URLconf at boot.
edms_router.add_router("", cloud_router)

# Applied here rather than as a kwarg on thirteen decorators, and applied to the
# template's operations so the per-mount clones inherit it (ninja's
# ``Operation.clone`` copies this attribute verbatim).
for _path_view in cloud_router.path_operations.values():
    for _operation in _path_view.operations:
        _operation.include_in_schema = CLOUD_IN_SCHEMA
