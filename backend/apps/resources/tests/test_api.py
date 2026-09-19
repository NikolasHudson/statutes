"""The Resources HTTP surface.

Two of these tests are policy, not behaviour, and should be the last ones
anyone deletes: every route requires a session (401) and a live plan (402).
The dataset lists registered agents, who are frequently private individuals at
their home addresses — it is behind a login on purpose, there is no bulk
export, and the search routes are throttled.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.accounts.models import Tier
from apps.resources.datasets.sos_entities.models import BusinessEntity
from apps.resources.ratelimit import RATE_LIMIT

from ._fixtures import SAMPLE_ZIP

BASE = "/api/resources"
SOS = f"{BASE}/iowa-business-entities"

User = get_user_model()


def load_fixture():
    from django.core.management import call_command

    call_command(
        "sync_resource", "iowa-business-entities", "--file", str(SAMPLE_ZIP),
        verbosity=0,
    )


def body(response) -> dict:
    return json.loads(response.content)


class ResourcesApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_fixture()

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="paid@example.com", password="x", tier=Tier.SOLO
        )
        self.client = Client()
        self.client.force_login(self.user)


class AuthTests(ResourcesApiTestCase):
    def test_every_route_requires_a_session(self):
        anon = Client()
        for url in (
            BASE,
            f"{SOS}/search?q=wood",
            f"{SOS}/entities/100001",
            f"{SOS}/agents?name=TRACY+NERISON",
            f"{SOS}/types",
        ):
            self.assertEqual(anon.get(url).status_code, 401, url)

    @override_settings(BILLING_REQUIRE_PAID=True)
    def test_no_plan_is_402_not_403(self):
        free = Client()
        free.force_login(
            User.objects.create_user(
                email="free@example.com", password="x", tier=Tier.FREE
            )
        )
        for url in (BASE, f"{SOS}/search?q=wood", f"{SOS}/entities/100001"):
            self.assertEqual(free.get(url).status_code, 402, url)

    def test_responses_are_never_cached(self):
        response = self.client.get(f"{SOS}/search?q=wood")
        self.assertEqual(response["Cache-Control"], "private, no-store")


class DatasetIndexTests(ResourcesApiTestCase):
    def test_lists_the_enabled_dataset_with_provenance(self):
        payload = body(self.client.get(BASE))
        entry = payload["datasets"][0]
        self.assertEqual(entry["slug"], "iowa-business-entities")
        self.assertEqual(entry["license"], "CC BY 4.0")
        self.assertTrue(entry["attribution_text"])
        self.assertEqual(entry["row_count"], 12)
        self.assertIsNotNone(entry["as_of"])


class SearchTests(ResourcesApiTestCase):
    def get(self, query: str):
        return body(self.client.get(f"{SOS}/search?{query}"))

    def names(self, query: str) -> list[str]:
        return [r["legal_name"] for r in self.get(query)["results"]]

    def test_no_filter_is_422(self):
        response = self.client.get(f"{SOS}/search")
        self.assertEqual(response.status_code, 422)

    def test_finds_the_quoted_name_from_plain_words(self):
        # The searcher types two plain words; the filing is wrapped in doubled
        # quotes and spells its form "L. C.". The exact normalized match
        # ("WOOD DOCTOR LLC") leads, as it should, and the quoted filing is
        # right behind it rather than lost.
        names = self.names("q=wood+doctor")
        self.assertEqual(names[0], "WOOD DOCTOR LLC")
        self.assertIn('" THE WOOD DOCTOR, L. C. "', names)

    def test_survives_a_typo(self):
        self.assertIn('" THE WOOD DOCTOR, L. C. "', self.names("q=wod+doctor"))

    def test_digit_query_pins_the_exact_corp_number_first(self):
        results = self.get("q=100005")["results"]
        self.assertEqual(results[0]["corp_number"], "100005")

    def test_exact_name_outranks_fuzzy(self):
        self.assertEqual(self.names("q=BETA+COMPANY")[0], "BETA COMPANY")

    def test_entity_form_is_ignored_on_both_sides(self):
        # The filing says "ZEBRA HOLDINGS, L. C."; the searcher types "LLC".
        self.assertIn("ZEBRA HOLDINGS, L. C.", self.names("q=zebra+holdings+llc"))

    def test_city_and_zip_filters_need_no_query(self):
        self.assertTrue(self.get("city=AMES")["results"])
        self.assertTrue(self.get("zip=50309")["results"])

    def test_agent_filter(self):
        names = self.names("agent=John+Smith")
        self.assertIn("BETA COMPANY", names)
        self.assertNotIn('" THE WOOD DOCTOR, L. C. "', names)

    def test_type_filter(self):
        payload = self.get("city=AMES&type=DOMESTIC+PROFIT")
        self.assertTrue(payload["results"])
        for row in payload["results"]:
            self.assertEqual(row["entity_type"], "DOMESTIC PROFIT")

    def test_inactive_hidden_by_default(self):
        BusinessEntity.objects.filter(corp_number="100002").update(
            is_active=False, deactivated_on="2026-01-01"
        )
        self.assertNotIn("WOOD DOCTOR LLC", self.names("q=wood+doctor"))
        self.assertIn(
            "WOOD DOCTOR LLC", self.names("q=wood+doctor&include_inactive=true")
        )

    def test_page_size_is_clamped(self):
        payload = self.get("city=AMES&page_size=5000")
        self.assertEqual(payload["page_size"], 50)

    def test_pagination_walks_without_repeating(self):
        first = self.get("city=AMES&page=1&page_size=2")
        second = self.get("city=AMES&page=2&page_size=2")
        self.assertEqual(first["total"], second["total"])
        self.assertFalse(
            {r["corp_number"] for r in first["results"]}
            & {r["corp_number"] for r in second["results"]}
        )

    def test_page_past_the_end_still_reports_the_total(self):
        payload = self.get("city=AMES&page=50")
        self.assertEqual(payload["results"], [])
        self.assertGreater(payload["total"], 0)

    def test_as_of_is_carried(self):
        self.assertIsNotNone(self.get("q=wood")["as_of"])

    def test_rate_limited(self):
        for _ in range(RATE_LIMIT):
            self.assertEqual(
                self.client.get(f"{SOS}/search?q=wood").status_code, 200
            )
        self.assertEqual(self.client.get(f"{SOS}/search?q=wood").status_code, 429)


class DetailTests(ResourcesApiTestCase):
    def test_full_record(self):
        payload = body(self.client.get(f"{SOS}/entities/100001"))
        self.assertEqual(payload["legal_name"], '" THE WOOD DOCTOR, L. C. "')
        self.assertEqual(payload["registered_agent"], "TRACY NERISON")
        self.assertEqual(payload["registered_agent_address"]["city"], "CEDAR RAPIDS")
        self.assertTrue(payload["is_active"])
        self.assertIsNotNone(payload["first_seen"])
        self.assertIsNotNone(payload["as_of"])

    def test_agent_entity_count_is_other_entities_at_the_same_agent_zip(self):
        # JOHN SMITH of AMES 50010 is on three filings; the namesake in
        # DUBUQUE is a different person and must not be counted.
        payload = body(self.client.get(f"{SOS}/entities/100006"))
        self.assertEqual(payload["agent_entity_count"], 2)

    def test_blank_agent_counts_nothing(self):
        payload = body(self.client.get(f"{SOS}/entities/100003"))
        self.assertEqual(payload["agent_entity_count"], 0)

    def test_unknown_and_malformed_corp_numbers_are_404(self):
        self.assertEqual(self.client.get(f"{SOS}/entities/999999").status_code, 404)
        self.assertEqual(
            self.client.get(f"{SOS}/entities/not%20a%20number").status_code, 404
        )


class AgentLookupTests(ResourcesApiTestCase):
    def test_reverse_lookup_by_agent(self):
        payload = body(self.client.get(f"{SOS}/agents?name=JOHN+SMITH"))
        self.assertEqual(payload["total"], 4)

    def test_zip_separates_namesakes(self):
        payload = body(self.client.get(f"{SOS}/agents?name=JOHN+SMITH&zip=50010"))
        self.assertEqual(payload["total"], 3)

    def test_name_is_required(self):
        self.assertEqual(self.client.get(f"{SOS}/agents").status_code, 422)


class TypesTests(ResourcesApiTestCase):
    def test_types_are_derived_from_the_data(self):
        payload = body(self.client.get(f"{SOS}/types"))
        types = {t["type"]: t["count"] for t in payload["types"]}
        self.assertEqual(types["DOMESTIC LIMITED LIABILITY COMPANY"], 5)
        self.assertIn("FOREIGN PROFIT", types)
