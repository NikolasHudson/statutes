"""Turn whatever the user submitted to Verify Document into plain text.

Two inputs, one output: pasted text passes straight through; an uploaded file
is decoded (plain text now; PDF/DOCX via docling lands in Phase 1.1). The
returned ``(source_name, text)`` pair feeds both the verifier and the audit
trail — ``source_name`` is "paste" or the uploaded filename.

Offset integrity matters: the verifier reports character spans back into this
exact text so the UI can highlight citations in place. Extraction must not
silently reflow or re-encode in a way that desyncs those spans from what the
user sees.
"""

from __future__ import annotations

from dataclasses import dataclass


class ExtractionError(Exception):
    """Raised when a submitted document can't be turned into text."""


# Suffixes we can decode as-is without a document converter.
_PLAINTEXT_SUFFIXES = (".txt", ".md", ".markdown", ".text")


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
    data = file.read()
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
    """Extract text from a PDF/DOCX. Wired to docling in Phase 1.1; until then
    a clear, user-facing error so the upload path fails honestly instead of
    silently."""
    raise ExtractionError(
        "PDF and Word upload is coming soon — for now, paste the document text "
        "to verify it."
    )
