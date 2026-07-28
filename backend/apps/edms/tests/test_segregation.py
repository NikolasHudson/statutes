"""The two structural guarantees, asserted rather than documented.

**1. Filings never enter the corpus.** Motions and orders are not law. They must
not appear in search, browse, chat RAG, research or MCP — and the platform has
many retrieval entry points, so "remember not to index filings" is not a control
anyone can keep. The control is that this app cannot reach ``apps.corpus`` at
all. When the Motions & Orders Library is eventually built it gets its own
tables here, and this test is what stops that decision from quietly eroding.

**2. Documents never land on Hudson's disk or in Hudson's DB.** No ``FileField``,
no ``BinaryField``, no base64 body parameter. The custody promise is only worth
something if it is a property of the code rather than a habit.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest import mock

from django.db import models
from django.test import Client, TestCase, override_settings

from apps.corpus.models import Node, NodeVersion, Source
from apps.edms import models as edms_models
from apps.edms import storage
from apps.edms.models import EdmsSettings

from ._factories import SPACES_SETTINGS, FakeS3, connect_onedrive, make_user

PACKAGE_ROOT = Path(edms_models.__file__).parent


class NoCorpusCouplingTests(TestCase):
    def test_no_module_imports_apps_corpus(self):
        """Parsed, not grepped: the rule is about imports, and the modules are
        expected to *discuss* corpus segregation in their docstrings."""
        offenders = []
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            if path.name == "test_segregation.py":
                continue  # this file imports corpus models deliberately, to assert on them
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                if any(n == "apps.corpus" or n.startswith("apps.corpus.") for n in names):
                    offenders.append(str(path.relative_to(PACKAGE_ROOT.parent.parent)))
        self.assertEqual(
            sorted(set(offenders)),
            [],
            "apps/edms must not import apps.corpus — filings are not law and must "
            "never reach a retrieval surface. Give the library its own tables.",
        )

    def test_no_model_stores_a_document(self):
        forbidden = (models.FileField, models.ImageField, models.BinaryField)
        offenders = [
            f"{model.__name__}.{field.name}"
            for model in edms_models.__dict__.values()
            if isinstance(model, type) and issubclass(model, models.Model)
            for field in model._meta.get_fields()
            if isinstance(field, forbidden)
        ]
        self.assertEqual(
            offenders,
            [],
            "apps/edms stores metadata, not documents. Bytes go browser → provider, "
            "or (opted-in only) straight through to the private bucket.",
        )


# Drives the whole v2 save flow, so it needs the cloud routes registered.
@override_settings(EDMS_CLOUD_ENABLED=True, **SPACES_SETTINGS)
class NoCorpusWritesTests(TestCase):
    """Behavioural backstop for the import rule: exercise the whole save +
    contribute flow and assert the corpus is untouched."""

    def setUp(self):
        self.user = make_user()
        self.client_ = Client()
        self.client_.force_login(self.user)
        connect_onedrive(self.user)
        patcher = mock.patch.object(storage, "_client", return_value=FakeS3())
        patcher.start()
        self.addCleanup(patcher.stop)

    @mock.patch("apps.edms.onedrive.get_item")
    @mock.patch("apps.edms.onedrive.create_upload_session")
    @mock.patch("apps.edms.onedrive.ensure_folder_path")
    def test_full_flow_creates_no_corpus_rows(self, ensure, mint, get_item):
        from apps.edms.onedrive import RemoteItem, UploadSession

        ensure.return_value = {"id": "F1", "name": "n", "path": "p"}
        mint.return_value = UploadSession(
            upload_url="https://upload.example.com/s",
            expires_at=None,
            folder_path="Hudson EDMSpro/CVCV1",
            filename="doc.pdf",
        )
        get_item.return_value = RemoteItem(
            item_id="I1", name="doc.pdf", web_url="https://x", size=10, folder_path="p"
        )
        EdmsSettings.objects.update_or_create(
            user=self.user, defaults={"crowdsource_opt_in": True}
        )

        before = (Node.objects.count(), NodeVersion.objects.count(), Source.objects.count())

        route = self.client_.post(
            "/api/edms/route",
            data=json.dumps({"case_number": "CVCV1", "doc_title": "Motion"}),
            content_type="application/json",
        )
        self.assertEqual(route.status_code, 200)
        sync_id = route.json()["sync_id"]
        self.client_.post(
            f"/api/edms/sync/{sync_id}/complete",
            data=json.dumps({"item_id": "I1"}),
            content_type="application/json",
        )
        self.client_.post(
            "/api/edms/crowdsource?case_number=CVCV1&doc_type=Motion",
            data=b"%PDF-1.7 body",
            content_type="application/pdf",
        )

        after = (Node.objects.count(), NodeVersion.objects.count(), Source.objects.count())
        self.assertEqual(before, after)
