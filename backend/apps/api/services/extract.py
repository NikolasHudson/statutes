"""Turn whatever the user submitted to Verify Document into plain text.

Two inputs, one output: pasted text passes straight through; an uploaded file
is decoded (plain text inline; PDF/DOCX via the docling microservice). The
returned ``(source_name, text)`` pair feeds both the verifier and the audit
trail — ``source_name`` is "paste" or the uploaded filename.

Offset integrity matters: the verifier reports character spans back into this
exact text so the UI can highlight citations in place. Extraction must not
silently reflow or re-encode in a way that desyncs those spans from what the
user sees.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


class ExtractionError(Exception):
    """Raised when a submitted document can't be turned into text."""


# Suffixes we can decode as-is without a document converter.
_PLAINTEXT_SUFFIXES = (".txt", ".md", ".markdown", ".text")

# Hard upload byte cap (#4/#10), enforced from file.size BEFORE we read the
# bytes into memory or forward them to docling. Tied to the 250k-char extraction
# limit: a born-digital legal brief well under that is a few MB even with images,
# so 40MB is generous headroom while still bounding a memory-exhaustion lever
# against the shared 2GB docling box. Must stay <= the docling service's own
# DOCLING_MAX_BODY_BYTES ceiling so the edge rejects first with a clear message.
_MAX_UPLOAD_BYTES = getattr(settings, "MAX_UPLOAD_BYTES", 40 * 1024 * 1024)


@dataclass
class Extracted:
    source_name: str
    text: str


def extract_text(*, file=None, pasted: str | None = None) -> Extracted:
    """Resolve the request's input to text.

    ``file`` is a Django ``UploadedFile`` (or None); ``pasted`` is the textarea
    contents (or None). Exactly one is expected; if both are present the file
    wins.
    """
    if file is not None and getattr(file, "name", None):
        return Extracted(source_name=file.name, text=_extract_file(file))
    if pasted and pasted.strip():
        return Extracted(source_name="paste", text=pasted)
    raise ExtractionError("No document provided — paste text or upload a file.")


def _extract_file(file) -> str:
    name = (file.name or "").lower()
    # Reject oversized uploads before reading them into memory or forwarding to
    # docling (#4/#10). file.size is set by Django's upload handlers from the
    # multipart part length, so this fires at the edge without buffering.
    size = getattr(file, "size", None)
    if size is not None and size > _MAX_UPLOAD_BYTES:
        mb = _MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ExtractionError(
            f"File is too large (limit {mb} MB). Upload a smaller document or "
            f"paste the relevant text directly."
        )
    data = file.read()
    # Defensive backstop for uploads whose .size wasn't populated (e.g. a custom
    # handler): the bytes are in memory now, so cap before forwarding them on.
    if size is None and len(data) > _MAX_UPLOAD_BYTES:
        mb = _MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ExtractionError(
            f"File is too large (limit {mb} MB). Upload a smaller document or "
            f"paste the relevant text directly."
        )
    if name.endswith(_PLAINTEXT_SUFFIXES):
        return data.decode("utf-8", errors="replace")
    if name.endswith((".pdf", ".docx", ".doc")):
        return _extract_richdoc(data, file.name)
    # Unknown extension: best-effort decode so a .text-without-suffix still
    # works, but reject anything that isn't valid UTF-8 rather than feed the
    # verifier mojibake.
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionError(
            f"Unsupported file type: {file.name}. Upload a PDF, DOCX, or text "
            f"file, or paste the text directly."
        ) from exc


def _extract_richdoc(data: bytes, filename: str) -> str:
    """Extract text from a PDF/DOCX via the docling microservice.

    Docling (PyTorch + layout models) runs as its own App Platform component
    so its footprint stays out of this API image; we POST the raw bytes to it
    and feed the returned text straight to the verifier. ``DOCLING_SERVICE_URL``
    unset means no service is deployed — fail honestly rather than silently.
    """
    base = (settings.DOCLING_SERVICE_URL or "").rstrip("/")
    if not base:
        raise ExtractionError(
            "PDF and Word upload isn't available right now — paste the document "
            "text to verify it."
        )

    headers = {
        "Content-Type": "application/octet-stream",
        # The service uses this only for the source label + to pick the
        # docling backend; it never trusts it as a path.
        "X-Filename": filename,
    }
    # Service-to-service shared secret (#9/#28). The docling component enforces
    # this when DOCLING_INTERNAL_TOKEN is set on both sides; unset (local dev on
    # :8001) we simply omit the header and the service skips the check.
    token = getattr(settings, "DOCLING_INTERNAL_TOKEN", "") or os.environ.get(
        "DOCLING_INTERNAL_TOKEN", ""
    )
    if token:
        headers["X-Internal-Token"] = token

    req = urllib.request.Request(
        f"{base}/extract",
        data=data,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.DOCLING_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 415/400 from the service mean the document itself is the problem —
        # surface its (already user-facing) detail. Anything else is ours.
        detail = _service_detail(exc)
        if exc.code in (400, 415) and detail:
            raise ExtractionError(detail) from exc
        raise ExtractionError(
            "Couldn't extract text from this document — try pasting the text "
            "instead."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ExtractionError(
            "The document extraction service is unavailable — paste the "
            "document text to verify it."
        ) from exc

    text = payload.get("text", "")
    if not text.strip():
        raise ExtractionError(
            "No text could be extracted from this document — it may be scanned "
            "or image-only. Paste the text instead."
        )
    return text


def _service_detail(exc: urllib.error.HTTPError) -> str | None:
    """Pull the JSON ``detail`` string out of an error response, if present."""
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (ValueError, OSError):
        return None
    detail = body.get("detail")
    return detail if isinstance(detail, str) else None
