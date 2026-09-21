"""``lookup_business_entity`` — the registry as an agent tool.

The ranking and matching are covered against the HTTP route in ``test_api``;
the tool answers from the same function, so these tests are about what is
different for an agent: the labelling, the refusal to list, and no paging.
"""

from __future__ import annotations

from django.test import TestCase

from apps.resources.datasets.sos_entities.models import BusinessEntity
from apps.resources.datasets.sos_entities.tool import (
    KIND,
    LIMIT_MAX,
    lookup_business_entity_tool as lookup,
)

from .test_api import load_fixture


class LookupBusinessEntityToolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_fixture()

    def test_every_payload_is_labelled_registry_data(self):
        payloads = (
            lookup(query="wood doctor"),
            lookup(corp_number="100005"),
            lookup(corp_number="999999999"),
            lookup(),
        )
        for out in payloads:
            self.assertEqual(out["kind"], KIND)
            self.assertIn("not legal authority", out["notice"])
            self.assertEqual(out["dataset"], "iowa-business-entities")
            self.assertTrue(out["source_url"])
            self.assertIn("sos.iowa.gov", out["verify_url"])

    def test_name_search_matches_the_web_route(self):
        out = lookup(query="wood doctor")
        self.assertTrue(out["found"])
        self.assertEqual(out["results"][0]["legal_name"], "WOOD DOCTOR LLC")
        self.assertTrue(out["as_of"])

    def test_digit_query_pins_the_corp_number(self):
        self.assertEqual(lookup(query="100005")["results"][0]["corp_number"], "100005")

    def test_no_filter_is_refused_not_listed(self):
        for out in (lookup(), lookup(entity_type="LLC"), lookup(query="  \x00 ")):
            self.assertFalse(out["found"])
            self.assertIn("error", out)
            self.assertNotIn("results", out)

    def test_limit_is_clamped_and_there_is_no_cursor(self):
        city = (
            BusinessEntity.objects.filter(is_active=True)
            .exclude(ra_city="")
            .values_list("ra_city", flat=True)
            .first()
        )
        out = lookup(city=city, limit=10_000)
        self.assertLessEqual(out["returned"], LIMIT_MAX)
        one = lookup(city=city, limit=1)
        self.assertEqual(one["returned"], 1)
        for key in ("page", "page_size", "next", "cursor", "offset"):
            self.assertNotIn(key, one)
        if one["total"] > 1:
            self.assertIn("cannot be paged", one["more"])

    def test_junk_limit_falls_back(self):
        self.assertTrue(lookup(query="wood doctor", limit="lots")["found"])

    def test_inactive_hidden_by_default(self):
        entity = BusinessEntity.objects.get(legal_name="BETA COMPANY")
        BusinessEntity.objects.filter(pk=entity.pk).update(is_active=False)

        def names(**kw):
            return [r["legal_name"] for r in lookup(query="beta company", **kw)["results"]]

        self.assertNotIn("BETA COMPANY", names())
        self.assertIn("BETA COMPANY", names(include_inactive=True))

    def test_detail_carries_addresses_but_no_geocodes(self):
        out = lookup(corp_number="100005")
        self.assertTrue(out["found"])
        entity = out["entity"]
        self.assertEqual(entity["corp_number"], "100005")
        for block in ("registered_agent_address", "home_office_address"):
            self.assertIn("address_1", entity[block])
            self.assertNotIn("lat", entity[block])
            self.assertNotIn("lon", entity[block])
        self.assertIn("agent_entity_count", entity)

    def test_unknown_and_malformed_corp_numbers_are_not_found(self):
        for bad in ("999999999", "../etc", "1; DROP"):
            out = lookup(corp_number=bad)
            self.assertFalse(out["found"], bad)
            self.assertNotIn("entity", out)
