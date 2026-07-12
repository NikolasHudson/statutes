"""No free account (decided 2026-07-12): ``BILLING_REQUIRE_PAID`` closes every
interactive surface to accounts without a live plan.

The rule is one function — :func:`apps.tenancy.services.has_paid_access`,
reading the ``user.tier`` derived cache — and each surface is a thin gate on
it: the session endpoints (chat, chat/stream, verify, research search) answer
**402**, the API-key/MCP chokepoint (:func:`apps.api.auth.require_feature`)
answers 402 before any feature logic, and the email assistant rejects with a
notify-once instead of spending LLM budget. ``/api/auth/me`` carries
``paid_access`` so the SPA can render the paywall.

Default-off is load-bearing and tested implicitly: the whole rest of the suite
runs with the flag unset and must keep passing (that IS the beta behavior).
"""

from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import Client, TestCase, override_settings
from ninja.errors import HttpError

from apps.accounts.models import Tier
from apps.api.auth import require_feature
from apps.mail.models import AddressAllowlist, AssistantAddress, InboundEmail
from apps.mail.services import claim_pending, process_inbound
from apps.tenancy.services import has_paid_access

from ._factories import make_api_key, make_user


def _client(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


_CHAT_PAYLOAD = json.dumps({"messages": [{"role": "user", "content": "hi"}]})


class HasPaidAccessTests(TestCase):
    def test_flag_off_everyone_passes(self):
        self.assertTrue(has_paid_access(make_user("f@e.com", tier=Tier.FREE)))

    @override_settings(BILLING_REQUIRE_PAID=True)
    def test_free_tier_refused(self):
        self.assertFalse(has_paid_access(make_user("f@e.com", tier=Tier.FREE)))

    @override_settings(BILLING_REQUIRE_PAID=True)
    def test_paid_tiers_pass(self):
        for i, tier in enumerate((Tier.SOLO, Tier.FIRM, Tier.CUSTOM)):
            self.assertTrue(
                has_paid_access(make_user(f"p{i}@e.com", tier=tier)), tier
            )

    @override_settings(BILLING_REQUIRE_PAID=True)
    def test_staff_exempt_even_on_free_tier(self):
        staff = make_user("staff@e.com", tier=Tier.FREE)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        self.assertTrue(has_paid_access(staff))

    @override_settings(BILLING_REQUIRE_PAID=True)
    def test_anonymous_and_none_refused(self):
        self.assertFalse(has_paid_access(AnonymousUser()))
        self.assertFalse(has_paid_access(None))


@override_settings(BILLING_REQUIRE_PAID=True)
class SessionSurfaceTests(TestCase):
    """Every session-authenticated interactive endpoint answers 402 — not 403,
    so the SPA can tell "go pay" apart from "not allowed"."""

    def setUp(self):
        self.free = _client(make_user("free@e.com", tier=Tier.FREE))

    def test_chat_402(self):
        r = self.free.post(
            "/api/chat", data=_CHAT_PAYLOAD, content_type="application/json"
        )
        self.assertEqual(r.status_code, 402)

    def test_chat_stream_402(self):
        r = self.free.post(
            "/api/chat/stream", data=_CHAT_PAYLOAD, content_type="application/json"
        )
        self.assertEqual(r.status_code, 402)

    def test_verify_document_402(self):
        r = self.free.post("/api/verify/document", {"text": "See Iowa Code 714.16."})
        self.assertEqual(r.status_code, 402)

    def test_research_search_402(self):
        r = self.free.get("/api/research/search", {"q": "lien priority"})
        self.assertEqual(r.status_code, 402)

    @override_settings(OPENAI_API_KEY="")
    def test_paid_user_passes_the_gate(self):
        # Proof the 402 above is the paywall, not something else in the path:
        # the same request from a solo user gets past it (and then fails on
        # the unrelated, unmistakable "no OpenAI key" 503).
        solo = _client(make_user("solo@e.com", tier=Tier.SOLO))
        r = solo.post(
            "/api/chat", data=_CHAT_PAYLOAD, content_type="application/json"
        )
        self.assertEqual(r.status_code, 503)

    def test_me_reports_paid_access(self):
        self.assertFalse(self.free.get("/api/auth/me").json()["paid_access"])
        solo = _client(make_user("solo2@e.com", tier=Tier.SOLO))
        self.assertTrue(solo.get("/api/auth/me").json()["paid_access"])

    def test_billing_and_org_stay_reachable(self):
        # The unpaid user must still be able to see billing state and their
        # org — that's how they fix the situation.
        self.assertEqual(self.free.get("/api/billing/subscription").status_code, 200)
        self.assertEqual(self.free.get("/api/org").status_code, 200)


class MeFlagDefaultTests(TestCase):
    def test_flag_off_me_reports_paid_access_true(self):
        free = _client(make_user("free@e.com", tier=Tier.FREE))
        self.assertTrue(free.get("/api/auth/me").json()["paid_access"])


@override_settings(BILLING_REQUIRE_PAID=True)
class ApiKeySurfaceTests(TestCase):
    """One chokepoint covers REST X-API-Key and MCP: require_feature."""

    def test_free_key_refused_for_every_feature(self):
        key, _ = make_api_key(make_user("free@e.com", tier=Tier.FREE))
        for feature in ("lookup", "search", "validate"):
            with self.assertRaises(HttpError) as ctx:
                require_feature(key, feature)
            self.assertEqual(ctx.exception.status_code, 402, feature)

    def test_solo_key_still_passes_its_features(self):
        key, _ = make_api_key(make_user("solo@e.com", tier=Tier.SOLO))
        require_feature(key, "lookup")  # must not raise


@override_settings(BILLING_REQUIRE_PAID=True)
class EmailAssistantTests(TestCase):
    def setUp(self):
        self.user = make_user("lawyer@example.com", tier=Tier.FREE)
        self.address = AssistantAddress.objects.create(
            address="assistant@mail.nick.law",
            mode=AssistantAddress.Mode.ALLOWLIST,
        )
        AddressAllowlist.objects.create(
            address=self.address, email="lawyer@example.com"
        )

    @mock.patch("apps.mail.services.run_chat_turn")
    def test_free_sender_rejected_without_llm_spend(self, turn):
        inbound = InboundEmail.objects.create(
            provider_id="pm-1",
            rfc_message_id="<orig-1@example.com>",
            address=self.address,
            from_email="lawyer@example.com",
            to_email="assistant@mail.nick.law",
            subject="Lien priority",
            body_text="What is the lien priority rule?",
            spf_pass=True,
            dkim_pass=True,
        )
        (claimed,) = claim_pending()
        process_inbound(claimed)
        inbound.refresh_from_db()
        self.assertEqual(inbound.status, InboundEmail.Status.REJECTED)
        self.assertEqual(inbound.reject_reason, "no active plan")
        turn.assert_not_called()
