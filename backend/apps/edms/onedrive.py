"""Microsoft Graph client for OneDrive, on behalf of a connected user.

Ported from the EDMSpro prototype (``apps/integrations/onedrive.py``) with one
substantive change: **this server no longer uploads file bytes.** Instead of
PUTting a PDF it holds, it mints a Graph *upload session* — a pre-authenticated,
single-file, time-limited URL — and hands that URL to the browser extension,
which streams the bytes straight from the court's EDMS to Microsoft.

What that buys, and why the extra round trip is worth it:

* Non-opt-in filings never transit Hudson infrastructure. That is a property of
  the architecture, provable from a network diagram, rather than a promise about
  what we delete.
* The OAuth tokens never leave this process. The extension only ever sees a URL
  scoped to one file in one folder, which Microsoft expires on its own.

Everything else — token refresh with the 5-minute skew, the 401 refresh-and-retry,
throttle classification (429/5xx retryable vs 4xx terminal), the OneDrive name
sanitizers, folder browse/create — is the prototype's logic, which was already
sound.

The one thing the server still does with bytes is *verification*: after the
extension reports an upload complete, we re-read the item from Graph ourselves.
A client that says "done" proves nothing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils import timezone as djtz

from .models import CloudIntegration

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
TOKEN_REFRESH_SKEW = timedelta(minutes=5)
DEFAULT_HTTP_TIMEOUT = 30

# Characters OneDrive rejects in file / folder names.
_RESERVED_CHARS = re.compile(r'[\\/*<>?:|#%"]+')
_TRIM_DOTS = re.compile(r"\.+$")


class OneDriveError(Exception):
    """Base class for OneDrive client failures."""


class OneDriveAuthError(OneDriveError):
    """Token can't be refreshed — the user must reconnect (terminal)."""


class OneDriveTerminalError(OneDriveError):
    """Graph returned a non-retryable error (4xx other than 429)."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"OneDrive {status_code}: {body[:240]}")
        self.status_code = status_code
        self.body = body


class OneDriveRetryableError(OneDriveError):
    """Graph returned 429 / 5xx — the caller should back off and retry."""

    def __init__(self, status_code: int, body: str, retry_after: int | None = None):
        super().__init__(f"OneDrive {status_code}: {body[:240]}")
        self.status_code = status_code
        self.body = body
        self.retry_after = retry_after


@dataclass(frozen=True)
class UploadSession:
    """A pre-authenticated Graph upload URL for exactly one file."""

    upload_url: str
    expires_at: datetime | None
    folder_path: str
    filename: str


@dataclass(frozen=True)
class RemoteItem:
    item_id: str
    name: str
    web_url: str
    size: int
    folder_path: str


# ---------------------------------------------------------------------------
# Name sanitizing
# ---------------------------------------------------------------------------


def sanitize_segment(name: str, max_len: int = 200) -> str:
    """Make a string safe to use as a OneDrive folder or file segment."""
    cleaned = _RESERVED_CHARS.sub("_", name or "").strip()
    cleaned = _TRIM_DOTS.sub("", cleaned)
    if cleaned.startswith("~"):
        cleaned = "_" + cleaned[1:]
    if not cleaned:
        cleaned = "untitled"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(". ")
    return cleaned


def sanitize_filename(filename: str) -> str:
    if "." in filename:
        stem, _, ext = filename.rpartition(".")
        return f"{sanitize_segment(stem)}.{sanitize_segment(ext, max_len=10)}"
    return sanitize_segment(filename)


def sanitize_path(folder_path: str) -> str:
    """Sanitize every segment of a drive-relative folder path."""
    return "/".join(
        sanitize_segment(p) for p in (folder_path or "").strip("/").split("/") if p
    )


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return djtz.now()


def _refresh_token(integration: CloudIntegration) -> None:
    """Mint a new access token from the stored refresh token; persist both.

    An ``invalid_grant`` here is terminal — revoked consent, a rotated password,
    or 90 days idle. We flag the integration so the SPA can show "Reconnect"
    instead of failing every subsequent save with the same opaque error."""
    if not integration.refresh_token:
        integration.mark_needs_reconnect("No refresh token stored.")
        raise OneDriveAuthError("OneDrive is not connected — reconnect to continue.")
    tenant = settings.MS_OAUTH_TENANT or "common"
    resp = requests.post(
        TOKEN_URL_TEMPLATE.format(tenant=tenant),
        data={
            "client_id": settings.MS_OAUTH_CLIENT_ID,
            "client_secret": settings.MS_OAUTH_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": integration.refresh_token,
            "scope": " ".join(settings.MS_OAUTH_SCOPES),
        },
        timeout=DEFAULT_HTTP_TIMEOUT,
    )
    if resp.status_code >= 400:
        integration.mark_needs_reconnect(f"Refresh failed ({resp.status_code}).")
        raise OneDriveAuthError(
            f"OneDrive refresh failed ({resp.status_code}) — reconnect to continue."
        )
    body = resp.json()
    expires_in = int(body.get("expires_in", 3600))
    integration.access_token = body["access_token"]
    if body.get("refresh_token"):
        integration.refresh_token = body["refresh_token"]
    integration.expires_at = _now() + timedelta(seconds=expires_in) - TOKEN_REFRESH_SKEW
    integration.needs_reconnect = False
    integration.last_error = ""
    integration.save(
        update_fields=[
            "access_token_enc",
            "refresh_token_enc",
            "expires_at",
            "needs_reconnect",
            "last_error",
        ]
    )


def ensure_fresh_token(integration: CloudIntegration) -> None:
    """Refresh the access token if it is expired or about to expire."""
    if (
        integration.expires_at is None
        or integration.expires_at <= _now() + TOKEN_REFRESH_SKEW
        or not integration.access_token
    ):
        _refresh_token(integration)


# ---------------------------------------------------------------------------
# Graph plumbing
# ---------------------------------------------------------------------------


def _parse_retry_after(resp: requests.Response) -> int | None:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def _raise_for_graph(resp: requests.Response) -> None:
    if resp.status_code < 400:
        return
    body = resp.text or ""
    if resp.status_code in (429, 500, 502, 503, 504):
        raise OneDriveRetryableError(resp.status_code, body, _parse_retry_after(resp))
    raise OneDriveTerminalError(resp.status_code, body)


def _graph(
    integration: CloudIntegration,
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    raise_for_status: bool = True,
) -> requests.Response:
    """Authed Graph call with one-shot 401 refresh-and-retry.

    The retry exists because a token can be revoked mid-flight (or the clock can
    skew past our 5-minute cushion); one refresh turns that into a success
    instead of a user-visible failure."""
    ensure_fresh_token(integration)
    headers = {"Authorization": f"Bearer {integration.access_token}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    resp = requests.request(
        method, url, headers=headers, json=json_body, timeout=DEFAULT_HTTP_TIMEOUT
    )
    if resp.status_code == 401:
        _refresh_token(integration)
        headers["Authorization"] = f"Bearer {integration.access_token}"
        resp = requests.request(
            method, url, headers=headers, json=json_body, timeout=DEFAULT_HTTP_TIMEOUT
        )
    if raise_for_status:
        _raise_for_graph(resp)
    return resp


def _item_url(item_id: str) -> str:
    if item_id in ("", "root"):
        return f"{GRAPH_BASE}/me/drive/root"
    return f"{GRAPH_BASE}/me/drive/items/{quote(item_id, safe='')}"


def _path_url(folder_path: str, suffix: str = "") -> str:
    """Graph's path addressing: ``/me/drive/root:/A/B:<suffix>``.

    An empty path addresses the drive root, which has no ``:`` form."""
    safe = sanitize_path(folder_path)
    if not safe:
        return f"{GRAPH_BASE}/me/drive/root{suffix}"
    encoded = "/".join(quote(p, safe="") for p in safe.split("/"))
    return f"{GRAPH_BASE}/me/drive/root:/{encoded}:{suffix}"


def _drive_path_segment(parent_path: str) -> str:
    """``parentReference.path`` comes back like ``/drive/root:/Documents/Casework``.
    Strip the ``/drive/root:`` prefix to get the user-facing path."""
    if parent_path.startswith("/drive/root:"):
        return parent_path[len("/drive/root:"):]
    return parent_path


def _folder_to_dict(item: dict) -> dict:
    parent_path = _drive_path_segment((item.get("parentReference") or {}).get("path", ""))
    name = item.get("name", "")
    full_path = (parent_path.rstrip("/") + "/" + name) if parent_path else name
    return {
        "id": item.get("id", ""),
        "name": name,
        "path": full_path.lstrip("/"),
        "child_count": (item.get("folder") or {}).get("childCount", 0),
        "web_url": item.get("webUrl", ""),
    }


def _to_remote_item(body: dict) -> RemoteItem:
    parent = body.get("parentReference") or {}
    return RemoteItem(
        item_id=body.get("id", ""),
        name=body.get("name", ""),
        web_url=body.get("webUrl", ""),
        size=int(body.get("size") or 0),
        folder_path=_drive_path_segment(parent.get("path", "")).lstrip("/"),
    )


# ---------------------------------------------------------------------------
# Account + folders
# ---------------------------------------------------------------------------


def get_profile(integration: CloudIntegration) -> dict:
    """The connected account's identity, for the "Connected as …" status."""
    body = _graph(integration, "GET", f"{GRAPH_BASE}/me").json()
    return {
        "email": body.get("mail") or body.get("userPrincipalName") or "",
        "name": body.get("displayName", ""),
    }


def list_child_folders(integration: CloudIntegration, parent_id: str = "root") -> dict:
    """Child folders of a parent item, plus the parent's own metadata so the
    picker can render breadcrumbs."""
    parent_url = _item_url(parent_id)
    parent_item = _graph(integration, "GET", parent_url).json()

    if parent_id in ("", "root"):
        parent_meta = {"id": parent_item.get("id", ""), "name": "OneDrive", "path": ""}
    else:
        parent_meta = _folder_to_dict(parent_item)

    children_url = (
        f"{parent_url}/children"
        "?$select=id,name,folder,parentReference,webUrl"
        "&$top=200"
    )
    body = _graph(integration, "GET", children_url).json()
    folders = [_folder_to_dict(it) for it in (body.get("value") or []) if "folder" in it]
    folders.sort(key=lambda f: f["name"].lower())
    return {"parent": parent_meta, "folders": folders}


def create_child_folder(integration: CloudIntegration, parent_id: str, name: str) -> dict:
    """Create a folder under ``parent_id`` (root when empty)."""
    name = sanitize_segment(name)
    if not name:
        raise OneDriveError("Folder name cannot be empty.")
    url = f"{_item_url(parent_id)}/children"
    resp = _graph(
        integration,
        "POST",
        url,
        json_body={
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename",
        },
    )
    return _folder_to_dict(resp.json())


def ensure_folder_path(integration: CloudIntegration, folder_path: str) -> dict:
    """Create ``folder_path`` (drive-relative) if it doesn't exist; return it.

    Walks the path a segment at a time with ``conflictBehavior: fail`` so a
    concurrent create is a 409 we treat as success rather than a duplicate
    "Case 123 1" folder — two browser tabs saving from the same docket is the
    normal case, not an edge case."""
    safe = sanitize_path(folder_path)
    if not safe:
        root = _graph(integration, "GET", _item_url("root")).json()
        return {"id": root.get("id", ""), "name": "OneDrive", "path": ""}

    parent_id = "root"
    walked: list[str] = []
    for segment in safe.split("/"):
        walked.append(segment)
        current = "/".join(walked)
        resp = _graph(
            integration,
            "GET",
            _path_url(current) + "?$select=id,name,folder,parentReference,webUrl",
            raise_for_status=False,
        )
        if resp.status_code == 200:
            item = resp.json()
            parent_id = item.get("id", "")
            continue
        if resp.status_code != 404:
            _raise_for_graph(resp)
        created = _graph(
            integration,
            "POST",
            f"{_item_url(parent_id)}/children",
            json_body={
                "name": segment,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            },
            raise_for_status=False,
        )
        if created.status_code == 409:
            # Someone else made it between our GET and our POST — re-read.
            item = _graph(
                integration,
                "GET",
                _path_url(current) + "?$select=id,name,folder,parentReference,webUrl",
            ).json()
            parent_id = item.get("id", "")
            continue
        _raise_for_graph(created)
        parent_id = created.json().get("id", "")

    return {"id": parent_id, "name": safe.split("/")[-1], "path": safe}


# ---------------------------------------------------------------------------
# Upload sessions + verification
# ---------------------------------------------------------------------------


def create_upload_session(
    integration: CloudIntegration, *, folder_path: str, filename: str
) -> UploadSession:
    """Mint a Graph upload session for one file at ``folder_path/filename``.

    ``conflictBehavior: rename`` means Microsoft — not us — resolves a name
    collision, so saving the same filing twice produces "Motion (1).pdf" instead
    of an error or a silent overwrite. The returned URL carries its own
    authorization: the extension PUTs to it with no Hudson credential and no
    Microsoft token."""
    safe_folder = sanitize_path(folder_path)
    safe_name = sanitize_filename(filename)
    target = f"{safe_folder}/{safe_name}" if safe_folder else safe_name
    resp = _graph(
        integration,
        "POST",
        _path_url(target, ":/createUploadSession"),
        json_body={
            "item": {
                "@microsoft.graph.conflictBehavior": "rename",
                "name": safe_name,
            }
        },
    )
    body = resp.json()
    upload_url = body.get("uploadUrl", "")
    if not upload_url:
        raise OneDriveError("Graph returned no uploadUrl for the upload session.")
    return UploadSession(
        upload_url=upload_url,
        expires_at=_parse_graph_datetime(body.get("expirationDateTime")),
        folder_path=safe_folder,
        filename=safe_name,
    )


def get_item(integration: CloudIntegration, item_id: str) -> RemoteItem | None:
    """Read one drive item by id. ``None`` if it isn't there."""
    if not item_id:
        return None
    resp = _graph(
        integration,
        "GET",
        _item_url(item_id) + "?$select=id,name,size,webUrl,parentReference",
        raise_for_status=False,
    )
    if resp.status_code == 404:
        return None
    _raise_for_graph(resp)
    return _to_remote_item(resp.json())


def get_item_by_path(integration: CloudIntegration, folder_path: str, filename: str):
    """Read one drive item by path. ``None`` if it isn't there.

    The fallback for verification when the client didn't report an item id.
    Note it can miss legitimately: ``conflictBehavior: rename`` may have landed
    the file under a different name, which is why the id path is preferred."""
    safe_folder = sanitize_path(folder_path)
    safe_name = sanitize_filename(filename)
    target = f"{safe_folder}/{safe_name}" if safe_folder else safe_name
    resp = _graph(
        integration,
        "GET",
        _path_url(target, "?$select=id,name,size,webUrl,parentReference"),
        raise_for_status=False,
    )
    if resp.status_code == 404:
        return None
    _raise_for_graph(resp)
    return _to_remote_item(resp.json())


def _parse_graph_datetime(raw: str | None) -> datetime | None:
    """Graph stamps ``2026-07-28T18:03:12.345Z``; ``fromisoformat`` on Python
    3.12 handles the ``Z``, but a malformed value must not break a save."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
