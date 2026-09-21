"""The hard rule, as a test.

Resources are not law. If a resources module ever imports ``apps.corpus`` (or
the other way round), registry rows start leaking into search, the citator and
the coverage counts, and a registered agent's home address becomes something
the product renders as authority. The boundary is only worth having if it is
checked, so this walks the source and checks it.
"""

from __future__ import annotations

import pathlib
import re

from django.test import SimpleTestCase

BACKEND = pathlib.Path(__file__).resolve().parents[3]

_CORPUS_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+apps\.corpus\b", re.M)
_RESOURCES_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+apps\.resources\b", re.M)

# The single file in apps/mcp_server allowed to import apps.resources.
MCP_ADAPTER = "apps/mcp_server/resources_tools.py"


def _sources(*relative: str):
    for rel in relative:
        root = BACKEND / rel
        for path in sorted(root.rglob("*.py")):
            if "migrations" in path.parts:
                continue
            yield path


class CorpusIsolationTests(SimpleTestCase):
    def test_resources_never_imports_the_corpus(self):
        offenders = [
            str(p.relative_to(BACKEND))
            for p in _sources("apps/resources")
            if _CORPUS_IMPORT_RE.search(p.read_text())
        ]
        self.assertEqual(offenders, [], "resources must not import apps.corpus")

    def test_the_corpus_never_imports_resources(self):
        # apps/api is the one place the two meet on the REST side, and only to
        # mount the router. The MCP server gets the same single meeting point:
        # one adapter file, so the corpus tools beside it stay corpus-only.
        offenders = [
            str(p.relative_to(BACKEND))
            for p in _sources("apps/corpus", "apps/mcp_server", "apps/citations")
            if _RESOURCES_IMPORT_RE.search(p.read_text())
            and p.relative_to(BACKEND).as_posix() != MCP_ADAPTER
        ]
        self.assertEqual(offenders, [], "the corpus must not import apps.resources")

    def test_the_mcp_adapter_is_only_an_adapter(self):
        # The exemption above is for wiring, not for logic: if the adapter ever
        # reaches for the corpus, registry rows and law are one import apart.
        text = (BACKEND / MCP_ADAPTER).read_text()
        self.assertIsNone(_CORPUS_IMPORT_RE.search(text))

    def test_no_model_points_at_the_corpus(self):
        from django.apps import apps as django_apps

        for model in django_apps.get_app_config("resources").get_models():
            for field in model._meta.get_fields():
                related = getattr(field, "related_model", None)
                if related is None:
                    continue
                label = related._meta.app_label
                self.assertNotEqual(
                    label,
                    "corpus",
                    f"{model.__name__}.{field.name} points at apps.corpus",
                )
