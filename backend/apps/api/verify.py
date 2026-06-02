"""Verify Document endpoint.

Streaming sibling of the chat endpoint, for the "verify citations" tool: the
user submits a legal document (pasted text, or — Phase 1.1 — an uploaded
PDF/DOCX) and gets back every citation graded green / yellow / red, one row at
a time, into the same progress module the chat surface uses.

Protocol: ``POST /api/verify/document`` returns ``application/x-ndjson``; each
line is one event:

    {"type": "start",         "char_count": N, "citations_total": K}
    {"type": "citation_done", "index": i, "finding": {...}}
    {"type": "summary",       "total": K, "green": a, "yellow": b, "red": c}
    {"type": "done"}
    {"type": "error",         "message": "..."}

Auth + budget reuse the chat gates: a logged-in user, charged against the same
daily/global LLM spend cap (the semantic check spends our Anthropic key).
"""

from __future__ import annotations

import json
import time

from django.http import StreamingHttpResponse
from ninja import File, Form, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.api.accounts import _require_login
from apps.api.chat import ALLOWED_CHAT_MODELS, _enforce_chat_quota
from apps.api.services.extract import ExtractionError, extract_text
from apps.api.trace_capture import record_verification_run
from apps.corpus.services.semantic_support import OpenAIChecker, default_checker
from apps.corpus.services.verify_document import iter_verify_document


verify_router = Router()

# Same ceiling the bulk citation-validation route uses — a whole 100-page brief
# is well under this, but one request can't chew unbounded text (and LLM spend).
_MAX_CHARS = 250_000


@verify_router.post("/verify/document", auth=None)
def verify_document_endpoint(
    request,
    file: UploadedFile = File(None),  # noqa: B008 — ninja dependency marker
    text: str = Form(None),  # noqa: B008
    model: str = Form(None),  # noqa: B008
):
    """Grade every citation in a submitted document. Streams NDJSON."""
    user = _require_login(request)

    if model and model not in ALLOWED_CHAT_MODELS:
        raise HttpError(400, f"unsupported model: {model}")

    try:
        extracted = extract_text(file=file, pasted=text)
    except ExtractionError as exc:
        raise HttpError(400, str(exc))

    if not extracted.text.strip():
        raise HttpError(400, "The document is empty.")
    if len(extracted.text) > _MAX_CHARS:
        raise HttpError(400, f"Document exceeds {_MAX_CHARS:,} character limit.")

    # Spends our OpenAI key for the semantic pass — gate it on the same budget
    # as chat so the two features share one ceiling.
    _enforce_chat_quota(user)

    # Use the model the user selected in chat. ``default_checker`` is None when
    # no OpenAI key is configured, in which case the semantic pass is skipped
    # and grading is verbatim-only.
    checker = default_checker()
    if checker is not None and model:
        checker = OpenAIChecker(model=model)

    response = StreamingHttpResponse(
        _stream_verify_events(
            user=user,
            source_name=extracted.source_name,
            text=extracted.text,
            semantic=checker,
        ),
        content_type="application/x-ndjson",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _stream_verify_events(*, user, source_name: str, text: str, semantic):
    """Drive ``iter_verify_document`` and serialize each event to NDJSON. Records
    the run to the audit log on the way out (success or failure)."""
    started = time.monotonic()
    findings: list[dict] = []
    summary: dict = {"total": 0, "green": 0, "yellow": 0, "red": 0}
    char_count = len(text)
    error: str | None = None
    index = 0

    try:
        for kind, payload in iter_verify_document(text, semantic=semantic):
            if kind == "start":
                char_count = payload["char_count"]
                yield _line(
                    {
                        "type": "start",
                        "char_count": payload["char_count"],
                        "citations_total": payload["citations_total"],
                    }
                )
            elif kind == "citation":
                finding = payload.to_dict()
                findings.append(finding)
                yield _line(
                    {"type": "citation_done", "index": index, "finding": finding}
                )
                index += 1
            elif kind == "summary":
                summary = payload
                yield _line({"type": "summary", **payload})
        yield _line({"type": "done"})
    except GeneratorExit:
        error = "client disconnected"
        raise
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        yield _line({"type": "error", "message": "Verification failed."})
    finally:
        record_verification_run(
            user=user,
            source_name=source_name,
            char_count=char_count,
            findings=findings,
            summary=summary,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=error or "",
        )


def _line(obj: dict) -> str:
    return json.dumps(obj, default=str) + "\n"
