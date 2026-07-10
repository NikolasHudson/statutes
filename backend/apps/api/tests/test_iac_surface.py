"""Phase 2 surface wiring for the Iowa Administrative Code: citation
rendering, search kind/doc_type scoping, and the agency browse tier."""

from django.test import TestCase

from apps.api.tests._factories import make_iac_minimal, make_iowa_corpus_minimal


class IACCitationRenderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.src, cls.agency, cls.chapter, cls.rule = make_iac_minimal()

    def test_rule_cites_with_r_sigil(self):
        from apps.corpus.services.corpus_tools import _render_citation

        self.assertEqual(_render_citation(self.rule), "Iowa Admin. Code r. 441—65.2")

    def test_chapter_cites_with_ch_sigil(self):
        from apps.corpus.services.corpus_tools import _render_citation

        self.assertEqual(_render_citation(self.chapter), "Iowa Admin. Code ch. 441—65")

    def test_search_row_citation_matches(self):
        from apps.api.search_common import _citation

        self.assertEqual(_citation(self.rule), "Iowa Admin. Code r. 441—65.2")


class IACSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_iowa_corpus_minimal()
        cls.src, cls.agency, cls.chapter, cls.rule = make_iac_minimal()

    def test_admin_doc_type_scopes_to_iac(self):
        resp = self.client.get(
            "/api/browse/search", {"q": "food assistance", "doc_type": "admin"}
        )
        body = resp.json()
        self.assertEqual(body["scope"], "iowa-admin-code")
        self.assertGreaterEqual(body["count"], 1)
        hit = body["results"][0]
        self.assertEqual(hit["node_id"], self.rule.id)
        self.assertEqual(hit["kind"], "admin")
        self.assertEqual(hit["citation"], "Iowa Admin. Code r. 441—65.2")
        # Chapter context must carry the agency prefix — a bare "65" is
        # meaningless across 87 agencies.
        self.assertEqual(hit["chapter"]["ordinal"], "441—65")

    def test_admin_code_alias_also_scopes(self):
        resp = self.client.get(
            "/api/browse/search", {"q": "food assistance", "doc_type": "admin_code"}
        )
        self.assertEqual(resp.json()["scope"], "iowa-admin-code")

    def test_code_scope_excludes_iac(self):
        resp = self.client.get(
            "/api/browse/search", {"q": "food assistance", "doc_type": "code"}
        )
        body = resp.json()
        self.assertNotIn(
            self.rule.id, [r["node_id"] for r in body["results"]]
        )


class IACBrowseTierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.iowa_src, cls.section, _ = make_iowa_corpus_minimal()
        cls.src, cls.agency, cls.chapter, cls.rule = make_iac_minimal()

    def test_list_chapters_groups_by_agency(self):
        resp = self.client.get("/api/browse/sources/iowa-admin-code/chapters")
        body = resp.json()
        self.assertIn("agencies", body)
        self.assertEqual(len(body["agencies"]), 1)
        ag = body["agencies"][0]
        self.assertEqual(ag["ordinal"], "441")
        self.assertEqual(ag["heading"], "Human Services Department[441]")
        self.assertEqual([c["id"] for c in ag["chapters"]], [self.chapter.id])
        # The flat list is kept for consumers that don't know about agencies.
        self.assertEqual([c["id"] for c in body["chapters"]], [self.chapter.id])

    def test_two_level_sources_have_no_agencies_key(self):
        resp = self.client.get("/api/browse/sources/iowa-code/chapters")
        self.assertNotIn("agencies", resp.json())

    def test_node_detail_serves_iac_rule(self):
        resp = self.client.get(f"/api/browse/nodes/{self.rule.id}")
        body = resp.json()
        self.assertEqual(body["citation"], "Iowa Admin. Code r. 441—65.2")
        self.assertEqual(body["source_slug"], "iowa-admin-code")
        self.assertIn("food assistance", body["body_text"])
        # Cross-refs are wired for IAC but stay empty until the citation
        # parser learns the em-dash rule form (Phase 3).
        self.assertEqual(body["cross_refs"], [])
