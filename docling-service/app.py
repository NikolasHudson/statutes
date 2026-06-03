"""Docling extraction microservice.

A single job: turn an uploaded PDF/DOCX into plain text for the Verify Document
feature. It runs as its own App Platform component (own ML-sized container)
because docling drags in PyTorch + layout models we don't want in the lean
Django API image. The Django side (``backend/apps/api/services/extract.py``)
POSTs the file bytes here and feeds the returned text straight to the citation
verifier.

Protocol — deliberately minimal so neither side needs a multipart parser:

    POST /extract
      headers: X-Filename: <original name>   (used only for the source label
                                               + to pick the docling backend)
      body:    the raw file bytes
      200  -> {"source_name": "...", "text": "..."}
      415  -> unsupported / unparseable document
      400  -> empty body

    GET /health -> {"status": "ok", "model_loaded": bool}

Offset integrity: the verifier reports character spans back into exactly the
``text`` we return, and the UI highlights against that same text — so the text
here just has to be internally consistent (no second reflow downstream), which
a single docling export guarantees.
"""

from __future__ import annotations

import concurrent.futures
import hmac
import logging
import os
from io import BytesIO

from fastapi import Depends, FastAPI, Header, HTTPException, Request

logger = logging.getLogger("docling_service")
logging.basicConfig(level=logging.INFO)

# Shared secret for service-to-service auth (#9/#28). The Django client sends it
# as X-Internal-Token; we compare in constant time before reading the body or
# touching the converter. When unset (local dev) auth is disabled so the local
# docling on :8001 still works without ceremony — the prod spec binds this as a
# SECRET and the network isolation (internal_ports) is the outer layer.
_INTERNAL_TOKEN = os.environ.get("DOCLING_INTERNAL_TOKEN", "")

# Hard ceiling on the request body (#10). A PDF/DOCX big enough to matter for
# citation verification is well under this; anything larger is rejected with 413
# before we buffer or parse it, so an oversized upload can't OOM the 2GB box.
# Tied to the 250k-char extraction limit on the Django side — a few MB of text.
_MAX_BODY_BYTES = int(os.environ.get("DOCLING_MAX_BODY_BYTES", str(40 * 1024 * 1024)))

# Per-request converter deadline (#10). A small decompression/layout bomb can be
# under the size cap yet pin the single worker for minutes; we run convert() in a
# worker thread and abort with 504 if it overruns. Defaults below the Django
# DOCLING_TIMEOUT so the client doesn't give up on a request we're still serving.
_CONVERT_TIMEOUT = int(os.environ.get("DOCLING_CONVERT_TIMEOUT", "90"))

# OCR is heavy (EasyOCR + its own models) and most legal filings are
# born-digital PDFs with a real text layer, so it's off by default. Flip
# DOCLING_OCR=1 to handle scanned documents at the cost of latency + memory.
_OCR_ENABLED = os.environ.get("DOCLING_OCR", "").lower() in ("1", "true", "yes")

# Extensions docling handles for our use case. Anything else is rejected here
# so the caller gets a clean 415 instead of a converter stack trace.
_SUPPORTED_SUFFIXES = (".pdf", ".docx", ".doc")

app = FastAPI(title="docling-extract", version="1.0")

# Built once at startup and reused — model load is the expensive part, so we
# pay it on boot, not per request. Populated by the startup handler.
_converter = None

# A single worker matching the single uvicorn worker: convert() is CPU/memory
# heavy and we only ever run one at a time, but routing it through a thread lets
# us impose a hard deadline (the GIL is released inside the native model passes).
_convert_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    """Reject calls without the shared secret (#9/#28).

    Disabled when DOCLING_INTERNAL_TOKEN is unset (local dev). Constant-time
    compare so a wrong token can't be probed by timing. Runs before any body
    read or converter work via FastAPI's dependency ordering.
    """
    if not _INTERNAL_TOKEN:
        return
    if not hmac.compare_digest(x_internal_token or "", _INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _build_converter():
    """Construct the docling DocumentConverter with our pipeline options."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = _OCR_ENABLED
    # Table structure detection is its own model pass; we only need the prose
    # text for citation verification, so skip it to keep latency down.
    pdf_options.do_table_structure = False
    # The Dockerfile pre-downloads model weights to this path at build time so
    # cold starts don't reach the network. When set, point docling at them.
    artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH")
    if artifacts:
        pdf_options.artifacts_path = artifacts

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        }
    )


@app.on_event("startup")
def _load_models() -> None:
    global _converter
    logger.info("loading docling converter (ocr=%s)...", _OCR_ENABLED)
    _converter = _build_converter()
    logger.info("docling converter ready")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": _converter is not None}


def _export_text(document) -> str:
    """Get plain text out of a DoclingDocument across library versions.

    Prefer a true text export; fall back to markdown (which is still readable
    prose for a legal brief — the citation matcher works on either)."""
    for method in ("export_to_text", "export_to_markdown"):
        fn = getattr(document, method, None)
        if callable(fn):
            return fn()
    raise RuntimeError("DoclingDocument exposes no text export method")


@app.post("/extract", dependencies=[Depends(require_internal_token)])
async def extract(
    request: Request,
    x_filename: str = Header(default="upload"),
    content_length: int | None = Header(default=None),
) -> dict:
    if _converter is None:  # startup hasn't finished / failed
        raise HTTPException(status_code=503, detail="Converter not ready.")

    name = x_filename or "upload"
    if not name.lower().endswith(_SUPPORTED_SUFFIXES):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {name}",
        )

    # Reject oversized uploads before buffering the whole body (#10). Trust the
    # declared Content-Length for an early-out, then re-check the actual bytes in
    # case the header lied or was chunked.
    if content_length is not None and content_length > _MAX_BODY_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Document exceeds the {_MAX_BODY_BYTES} byte upload limit.",
        )

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty request body.")
    if len(data) > _MAX_BODY_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Document exceeds the {_MAX_BODY_BYTES} byte upload limit.",
        )

    from docling.datamodel.base_models import DocumentStream

    def _do_convert() -> str:
        stream = DocumentStream(name=name, stream=BytesIO(data))
        result = _converter.convert(stream)
        return _export_text(result.document)

    try:
        # Hard per-request deadline so a layout/decompression bomb can't pin the
        # single worker (#10). The convert keeps running in the pool thread after
        # a timeout (Python can't kill it), but we free this request and return
        # 504; the next request queues behind it on the single-slot pool.
        future = _convert_pool.submit(_do_convert)
        text = future.result(timeout=_CONVERT_TIMEOUT)
    except concurrent.futures.TimeoutError as exc:
        logger.warning("extraction timed out for %s after %ss", name, _CONVERT_TIMEOUT)
        raise HTTPException(
            status_code=504,
            detail="Document took too long to process.",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — any converter failure is a 415
        logger.warning("extraction failed for %s: %s", name, exc)
        raise HTTPException(
            status_code=415,
            detail="Could not extract text from this document.",
        ) from exc

    return {"source_name": name, "text": text}
