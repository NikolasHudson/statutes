"""Unit tests for the Verify-Document text extraction layer.

The docling PDF/DOCX path is an HTTP call to a separate microservice; here we
stub ``urlopen`` so the tests stay offline and assert the contract Django
relies on: success returns the service's text, and every failure mode maps to
a friendly ``ExtractionError`` (never a raw stack trace to the user).
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.api.services.extract import ExtractionError, extract_text


class _FakeUpload:
    """Minimal stand-in for a Django UploadedFile."""

    def __init__(self, name: str, data: bytes = b"%PDF-1.4 fake", size=None):
        self.name = name
        self._data = data
        # Django sets .size from the multipart part length; default to the data
        # length so the production size check sees a realistic value.
        self.size = len(data) if size is None else size

    def read(self) -> bytes:
        return self._data


def _ok_response(payload: dict):
    """A urlopen() context-manager result whose read() yields JSON."""
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def _http_error(code: int, detail: str | None):
    body = json.dumps({"detail": detail}).encode() if detail else b"{}"
    return urllib.error.HTTPError(
        url="http://docling/extract",
        code=code,
        msg="err",
        hdrs=None,
        fp=io.BytesIO(body),
    )


@override_settings(DOCLING_SERVICE_URL="http://docling:8080", DOCLING_TIMEOUT=5)
class RichDocExtractionTests(SimpleTestCase):
    def test_paste_passes_through(self):
        out = extract_text(pasted="Iowa Code § 714.16 controls.")
        self.assertEqual(out.source_name, "paste")
        self.assertEqual(out.text, "Iowa Code § 714.16 controls.")

    def test_pdf_returns_service_text(self):
        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen",
            return_value=_ok_response({"text": "Extracted brief text.", "source_name": "brief.pdf"}),
        ):
            out = extract_text(file=_FakeUpload("brief.pdf"))
        # source_name is the uploaded filename; text is what docling returned.
        self.assertEqual(out.source_name, "brief.pdf")
        self.assertEqual(out.text, "Extracted brief text.")

    def test_filename_header_is_sent(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["filename"] = req.get_header("X-filename")
            captured["url"] = req.full_url
            return _ok_response({"text": "ok"})

        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            extract_text(file=_FakeUpload("My Brief.docx"))
        self.assertEqual(captured["filename"], "My Brief.docx")
        self.assertEqual(captured["url"], "http://docling:8080/extract")

    def test_service_unreachable_is_friendly(self):
        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with self.assertRaises(ExtractionError) as ctx:
                extract_text(file=_FakeUpload("brief.pdf"))
        self.assertIn("unavailable", str(ctx.exception).lower())

    def test_document_error_surfaces_service_detail(self):
        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen",
            side_effect=_http_error(415, "Unsupported file type: brief.pdf"),
        ):
            with self.assertRaises(ExtractionError) as ctx:
                extract_text(file=_FakeUpload("brief.pdf"))
        self.assertIn("Unsupported file type", str(ctx.exception))

    def test_server_error_is_generic(self):
        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen",
            side_effect=_http_error(500, None),
        ):
            with self.assertRaises(ExtractionError) as ctx:
                extract_text(file=_FakeUpload("brief.pdf"))
        self.assertIn("Couldn't extract", str(ctx.exception))

    def test_empty_extraction_is_rejected(self):
        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen",
            return_value=_ok_response({"text": "   "}),
        ):
            with self.assertRaises(ExtractionError) as ctx:
                extract_text(file=_FakeUpload("scan.pdf"))
        self.assertIn("scanned", str(ctx.exception).lower())


@override_settings(DOCLING_SERVICE_URL="http://docling:8080", DOCLING_TIMEOUT=5)
class UploadSizeCapTests(SimpleTestCase):
    """The byte cap must fire BEFORE the file is read or forwarded (#4/#10)."""

    def test_oversized_upload_rejected_before_read(self):
        from apps.api.services.extract import _MAX_UPLOAD_BYTES

        # .size over the cap; reading would crash the test if it were reached.
        class _Boom(_FakeUpload):
            def read(self):  # noqa: D401
                raise AssertionError("file.read() must not run for oversized uploads")

        big = _Boom("brief.pdf", data=b"", size=_MAX_UPLOAD_BYTES + 1)
        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen",
            side_effect=AssertionError("docling must not be called"),
        ):
            with self.assertRaises(ExtractionError) as ctx:
                extract_text(file=big)
        self.assertIn("too large", str(ctx.exception).lower())

    def test_within_cap_still_extracts(self):
        ok = _FakeUpload("brief.pdf", data=b"%PDF-1.4 small")
        with mock.patch(
            "apps.api.services.extract.urllib.request.urlopen",
            return_value=_ok_response({"text": "fine"}),
        ):
            out = extract_text(file=ok)
        self.assertEqual(out.text, "fine")

    def test_internal_token_header_sent_when_configured(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["token"] = req.get_header("X-internal-token")
            return _ok_response({"text": "ok"})

        with override_settings(DOCLING_INTERNAL_TOKEN="s3cret"):
            with mock.patch(
                "apps.api.services.extract.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                extract_text(file=_FakeUpload("brief.pdf"))
        self.assertEqual(captured["token"], "s3cret")

    def test_internal_token_header_absent_when_unset(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["token"] = req.get_header("X-internal-token")
            return _ok_response({"text": "ok"})

        # Neither settings nor env set -> header omitted so local dev works.
        with override_settings(DOCLING_INTERNAL_TOKEN=""):
            with mock.patch.dict("os.environ", {}, clear=False):
                import os as _os

                _os.environ.pop("DOCLING_INTERNAL_TOKEN", None)
                with mock.patch(
                    "apps.api.services.extract.urllib.request.urlopen",
                    side_effect=fake_urlopen,
                ):
                    extract_text(file=_FakeUpload("brief.pdf"))
        self.assertIsNone(captured["token"])


@override_settings(DOCLING_SERVICE_URL="")
class NoServiceConfiguredTests(SimpleTestCase):
    def test_pdf_upload_without_service_is_friendly(self):
        with self.assertRaises(ExtractionError) as ctx:
            extract_text(file=_FakeUpload("brief.pdf"))
        self.assertIn("isn't available", str(ctx.exception))

    def test_plaintext_still_works_without_service(self):
        out = extract_text(file=_FakeUpload("note.txt", data=b"plain text"))
        self.assertEqual(out.text, "plain text")
