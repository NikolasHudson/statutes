"""Where a filing goes and what it is called.

This is the prototype's ``apps/routing/tasks.py`` with the Celery task removed.
The template rendering and the precedence rules survive unchanged — they were
the valuable part; the queue was an artifact of the server-side upload design
that split custody made unnecessary.

Precedence, most specific first:

1. A :class:`~apps.edms.models.CaseFolderMapping` for this exact case number
   (what the extension's per-case gear popover writes).
2. The user's :class:`~apps.edms.models.EdmsSettings` default root +
   case-folder template.
3. The built-in defaults, so a user who has configured nothing still gets
   filings sorted by case number under one root folder.

Both templates render against the same docket metadata the extension scraped,
and both go through :func:`~apps.edms.onedrive.sanitize_segment`, so a case
caption containing ``/`` or ``:`` cannot escape the intended folder.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from .models import (
    DEFAULT_CASE_FOLDER_TEMPLATE,
    DEFAULT_NAMING_TEMPLATE,
    DEFAULT_ROOT_FOLDER,
    CaseFolderMapping,
    EdmsSettings,
)
from .onedrive import sanitize_filename, sanitize_segment

# Tokens the UI offers as clickable chips. Served by the API so the SPA, the
# extension and the renderer can never disagree about what is substitutable.
FOLDER_TOKENS = ("{case_number}", "{case_type}", "{docket_num}", "{filer}", "{county}", "{year}")
FILENAME_TOKENS = (
    "{date}",
    "{case_num}",
    "{doc_title}",
    "{doc_type}",
    "{docket_num}",
    "{judge}",
    "{county}",
)


@dataclass(frozen=True)
class FilingMeta:
    """The docket row the extension scraped. Every field optional but
    ``case_number`` — a filing with no case is not routable."""

    case_number: str
    case_type: str = ""
    docket_num: str = ""
    doc_title: str = ""
    doc_type: str = ""
    row_date: dt.date | None = None
    filer: str = ""
    county: str = ""
    judge: str = ""


@dataclass(frozen=True)
class Destination:
    folder_path: str
    filename: str


def _substitute(template: str, values: dict[str, str]) -> str:
    """Replace every occurrence of each token. ``str.replace`` (not the
    prototype's single-shot ``.replace(tok, val)`` with a count of 1) so a
    template that uses a token twice — ``{case_number}/{case_number} filings`` —
    renders both."""
    out = template
    for token, value in values.items():
        out = out.replace(token, value)
    return out


def render_folder(template: str, meta: FilingMeta, *, today: dt.date | None = None) -> str:
    """Render a case-folder template to a sanitized, drive-relative sub-path.

    An empty token can leave ``//`` or a trailing slash; those collapse rather
    than producing an unnamed folder level. If everything renders empty we fall
    back to the case number, and finally to ``misc`` — a filing always lands
    somewhere findable, never at the drive root."""
    year = ""
    if meta.row_date:
        year = str(meta.row_date.year)
    elif today:
        year = str(today.year)
    rendered = template or DEFAULT_CASE_FOLDER_TEMPLATE
    rendered = _substitute(
        rendered,
        {
            "{case_number}": meta.case_number or "",
            "{case_type}": meta.case_type or "",
            "{docket_num}": meta.docket_num or "",
            "{filer}": meta.filer or "",
            "{county}": meta.county or "",
            "{year}": year,
        },
    )
    rendered = re.sub(r"/+", "/", rendered).strip("/")
    parts = [sanitize_segment(p) for p in rendered.split("/") if p.strip()]
    if parts:
        return "/".join(parts)
    return sanitize_segment(meta.case_number or "misc")


def render_filename(template: str, meta: FilingMeta) -> str:
    """Render a naming template to a single sanitized ``.pdf`` filename."""
    rendered = _substitute(
        template or DEFAULT_NAMING_TEMPLATE,
        {
            "{date}": (meta.row_date.isoformat() if meta.row_date else "undated"),
            "{case_num}": meta.case_number or "unknown",
            "{doc_title}": meta.doc_title or "document",
            "{doc_type}": meta.doc_type or "",
            "{docket_num}": meta.docket_num or "",
            "{judge}": meta.judge or "",
            "{county}": meta.county or "",
        },
    )
    # Separator hygiene: an empty token in the middle of "{a}_{b}_{c}" leaves
    # "__", which reads as a bug to the user staring at their file list.
    rendered = re.sub(r"[_\-\s]{2,}", "_", rendered).strip("_-. ")
    if not rendered:
        rendered = meta.case_number or "document"
    if not rendered.lower().endswith(".pdf"):
        rendered += ".pdf"
    return sanitize_filename(rendered)


def resolve_destination(user, meta: FilingMeta, *, today: dt.date | None = None) -> Destination:
    """The folder path + filename for one filing. See module docstring for
    precedence."""
    today = today or dt.date.today()
    settings_row = EdmsSettings.objects.filter(user=user).first()
    override = CaseFolderMapping.objects.filter(
        user=user, case_number=meta.case_number
    ).first()

    naming_template = (
        (override.naming_template if override else "")
        or (settings_row.naming_template if settings_row else "")
        or DEFAULT_NAMING_TEMPLATE
    )
    filename = render_filename(naming_template, meta)

    # A per-case override names the destination outright — it is the folder the
    # attorney picked for THIS case, so it is used as given (still rendered, so
    # a template in the override keeps working) and not nested under the root.
    if override and override.folder_path:
        rendered = render_folder(override.folder_path, meta, today=today)
        if rendered:
            return Destination(folder_path=rendered, filename=filename)

    root = ((settings_row.default_destination_path if settings_row else "") or "").strip("/")
    if not root:
        root = DEFAULT_ROOT_FOLDER
    root_parts = [sanitize_segment(p) for p in root.split("/") if p.strip()]
    case_template = (
        (settings_row.case_folder_template if settings_row else "")
        or DEFAULT_CASE_FOLDER_TEMPLATE
    )
    case_folder = render_folder(case_template, meta, today=today)
    parts = root_parts + ([case_folder] if case_folder else [])
    return Destination(folder_path="/".join(parts), filename=filename)
