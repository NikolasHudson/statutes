"""Integration tests for the streaming Verify-Document endpoint.

Drives the real NDJSON pipeline end to end against a fixture corpus: auth gate,
event sequence, per-citation findings, and the audit-log row it writes. The
semantic layer is disabled (no ANTHROPIC_API_KEY in tests) so grading is the
deterministic verbatim path.
"""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from apps.api.models import VerificationRun
from apps.corpus.services import lookups
from apps.api.tests._factories import make_iowa_corpus_minimal, make_user


def _events(resp) -> list[dict]:
    body = b"".join(resp.streaming_content).decode()
    return [json.loads(line) for line in body.splitlines() if line.strip()]


# OPENAI_API_KEY="" disables the semantic layer so the stream is deterministic
# and offline; these tests assert the verbatim/resolution grading + plumbing.
@override_settings(CHAT_TRACE_CAPTURE=True, OPENAI_API_KEY="")
class VerifyEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.src, cls.section, cls.version = make_iowa_corpus_minimal()

    def setUp(self):
        lookups.reset_default_source_cache()
        self.user = make_user(email="lawyer@example.com")
        self.client = Client()

    def _post_paste(self, text: str):
        # Multipart form (the endpoint takes Form/File), text in the `text` field.
        return self.client.post("/api/verify/document", data={"text": text})

    def test_requires_login(self):
        resp = self._post_paste("Iowa Code § 714.16 governs.")
        self.assertIn(resp.status_code, (401, 403))

    def test_stream_grades_each_citation(self):
        self.client.force_login(self.user)
        text = (
            'Iowa Code § 714.16 says a "merchant who commits a deceptive '
            'practice or unfair method of competition violates this section." '
            "But Iowa Code § 714.404 does not exist."
        )
        resp = self._post_paste(text)
        self.assertEqual(resp.status_code, 200)
        events = _events(resp)

        kinds = [e["type"] for e in events]
        self.assertEqual(kinds[0], "start")
        self.assertEqual(kinds[-1], "done")
        self.assertIn("summary", kinds)

        start = events[0]
        self.assertEqual(start["citations_total"], 2)

        findings = [e["finding"] for e in events if e["type"] == "citation_done"]
        by_raw = {f["raw"]: f for f in findings}
        good = next(f for r, f in by_raw.items() if "714.16" in r)
        bad = next(f for r, f in by_raw.items() if "714.404" in r)
        self.assertEqual(good["status"], "green")
        self.assertEqual(bad["status"], "red")

        summary = next(e for e in events if e["type"] == "summary")
        self.assertEqual(summary["green"], 1)
        self.assertEqual(summary["red"], 1)

    def test_writes_audit_row(self):
        self.client.force_login(self.user)
        resp = self._post_paste("Iowa Code § 714.16 is controlling here.")
        self.assertEqual(resp.status_code, 200)
        _events(resp)  # drain the stream so the finally-block writes the row
        row = VerificationRun.objects.get()
        self.assertIsNone(row.user)  # unattributed, like ChatTrace
        self.assertEqual(row.source_name, "paste")
        self.assertEqual(row.citations_total, 1)
        self.assertEqual(row.green, 1)

    def test_empty_document_is_rejected(self):
        self.client.force_login(self.user)
        resp = self._post_paste("   ")
        self.assertEqual(resp.status_code, 400)

    def test_selected_model_is_accepted(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/verify/document",
            data={"text": "Iowa Code § 714.16 controls.", "model": "gpt-4o"},
        )
        self.assertEqual(resp.status_code, 200)
        kinds = [e["type"] for e in _events(resp)]
        self.assertEqual(kinds[-1], "done")

    def test_unsupported_model_is_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/verify/document",
            data={"text": "Iowa Code § 714.16 controls.", "model": "evil-model"},
        )
        self.assertEqual(resp.status_code, 400)
