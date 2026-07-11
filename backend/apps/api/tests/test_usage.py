"""Token/cost accounting + dollar budget caps (apps.api.usage).

Three surfaces under test: the capture layer (emit/collect writes correct,
content-free LlmUsage rows), the enforcement layer (daily/monthly/global
dollar budgets reject before any OpenAI work), and the staff-only
/api/admin/usage aggregates the dashboard reads.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.accounts.models import Tier
from apps.api.models import LlmUsage
from apps.api.usage import (
    FEATURE_CHAT,
    FEATURE_EMAIL,
    collect_usage,
    cost_microusd,
    emit_usage,
    price_for,
)

from ._factories import make_user


def _post_chat(client: Client, content: str = "hi"):
    return client.post(
        "/api/chat",
        data=json.dumps({"messages": [{"role": "user", "content": content}]}),
        content_type="application/json",
    )


class _FakeUsage:
    prompt_tokens = 1000
    completion_tokens = 100


class _FakeMessage:
    content = "Grounded answer."
    tool_calls = None


class _FakeCompletion:
    model = "gpt-4o-mini"
    usage = _FakeUsage()
    choices = [type("C", (), {"message": _FakeMessage()})()]


def _fake_openai():
    client = mock.MagicMock()
    client.chat.completions.create.return_value = _FakeCompletion()
    return mock.patch("openai.OpenAI", return_value=client)


class PriceTableTests(TestCase):
    def test_longest_prefix_wins(self):
        # gpt-4o-mini must not fall through to the gpt-4o price.
        self.assertEqual(price_for("gpt-4o-mini"), (0.15, 0.60))
        self.assertEqual(price_for("gpt-4o"), (2.50, 10.00))
        # Dated variants resolve to their base model's price.
        self.assertEqual(price_for("gpt-5-mini-2025-08-07"), (0.25, 2.00))

    def test_unknown_model_costs_zero(self):
        self.assertEqual(price_for("claude-fable-5"), (0.0, 0.0))
        self.assertEqual(cost_microusd("claude-fable-5", 1000, 1000), 0)

    def test_cost_math_is_exact_integer_microusd(self):
        # 1000 prompt @ $0.15/M + 100 completion @ $0.60/M
        # = 150 + 60 micro-dollars.
        self.assertEqual(cost_microusd("gpt-4o-mini", 1000, 100), 210)


class CaptureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(email="capture@example.com")

    def test_emit_outside_collector_writes_unattributed_row(self):
        emit_usage(FEATURE_CHAT, "gpt-4o-mini", 1000, 100)
        row = LlmUsage.objects.get()
        self.assertIsNone(row.user)
        self.assertIsNone(row.request_id)
        self.assertEqual(row.cost_microusd, 210)

    def test_collector_attributes_and_groups_one_turn(self):
        with collect_usage(self.user):
            emit_usage(FEATURE_CHAT, "gpt-4o-mini", 1000, 100)
            emit_usage("verification", "gpt-4o", 500, 50)
        rows = list(LlmUsage.objects.order_by("id"))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.user_id == self.user.id for r in rows))
        # One turn: both side-calls share the request_id.
        self.assertEqual(rows[0].request_id, rows[1].request_id)
        self.assertIsNotNone(rows[0].request_id)

    def test_relabel_maps_chat_to_email(self):
        with collect_usage(self.user, relabel={FEATURE_CHAT: FEATURE_EMAIL}):
            emit_usage(FEATURE_CHAT, "gpt-5-mini", 100, 10)
            emit_usage("verification", "gpt-4o", 100, 10)
        features = set(LlmUsage.objects.values_list("feature", flat=True))
        self.assertEqual(features, {FEATURE_EMAIL, "verification"})

    def test_zero_token_emission_writes_nothing(self):
        emit_usage(FEATURE_CHAT, "gpt-4o-mini", 0, 0)
        self.assertEqual(LlmUsage.objects.count(), 0)


@override_settings(OPENAI_API_KEY="sk-test")
class ChatEndpointCaptureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(email="chatspend@example.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_chat_turn_records_attributed_usage(self):
        with _fake_openai():
            resp = _post_chat(self.client)
        self.assertEqual(resp.status_code, 200)
        row = LlmUsage.objects.get()
        self.assertEqual(row.user_id, self.user.id)
        self.assertEqual(row.feature, FEATURE_CHAT)
        self.assertEqual(row.model, "gpt-4o-mini")
        self.assertEqual(row.prompt_tokens, 1000)
        self.assertEqual(row.completion_tokens, 100)
        self.assertEqual(row.cost_microusd, 210)
        self.assertIsNotNone(row.request_id)

    def test_usage_rows_store_no_content(self):
        """The confidentiality contract: whatever the user asked, no usage
        column may contain it."""
        with _fake_openai():
            _post_chat(self.client, content="my client embezzled funds")
        row = LlmUsage.objects.get()
        for field in row._meta.fields:
            value = str(getattr(row, field.name))
            self.assertNotIn("embezzled", value)


@override_settings(OPENAI_API_KEY="sk-test")
class BudgetEnforcementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(email="capped@example.com", tier=Tier.SOLO)
        self.client = Client()
        self.client.force_login(self.user)

    def _spend(self, usd: float, user=None):
        LlmUsage.objects.create(
            user=user or self.user,
            feature=FEATURE_CHAT,
            model="gpt-5-mini",
            prompt_tokens=1,
            completion_tokens=1,
            cost_microusd=int(usd * 1_000_000),
        )

    def test_daily_budget_trips_429_before_openai(self):
        self._spend(0.60)  # over the solo $0.50/day
        fake = mock.MagicMock()
        with mock.patch("openai.OpenAI", return_value=fake):
            resp = _post_chat(self.client)
        self.assertEqual(resp.status_code, 429)
        fake.chat.completions.create.assert_not_called()
        self.assertIn("budget", resp.json()["detail"].lower())

    def test_monthly_override_column_wins(self):
        self.user.monthly_budget_usd = Decimal("0.10")
        self.user.save(update_fields=["monthly_budget_usd"])
        self._spend(0.20)
        with _fake_openai():
            resp = _post_chat(self.client)
        self.assertEqual(resp.status_code, 429)

    def test_under_budget_passes(self):
        self._spend(0.10)
        with _fake_openai():
            resp = _post_chat(self.client)
        self.assertEqual(resp.status_code, 200)

    def test_staff_exempt_from_user_budgets(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self._spend(999.0)
        with (
            override_settings(CHAT_GLOBAL_MONTHLY_BUDGET_USD=0),
            _fake_openai(),
        ):
            resp = _post_chat(self.client)
        self.assertEqual(resp.status_code, 200)

    @override_settings(CHAT_GLOBAL_MONTHLY_BUDGET_USD=1.0)
    def test_global_ceiling_trips_503_for_everyone(self):
        other = make_user(email="other@example.com")
        self._spend(2.0, user=other)
        self.user.is_staff = True  # even staff
        self.user.save(update_fields=["is_staff"])
        resp = _post_chat(self.client)
        self.assertEqual(resp.status_code, 503)

    def test_budget_denial_does_not_burn_a_message_slot(self):
        """The dollar gate runs before the daily message counter bumps."""
        self._spend(0.60)
        _post_chat(self.client)  # 429
        self.assertIsNone(
            cache.get(
                f"chat:user:{self.user.pk}:"
                f"{__import__('django').utils.timezone.now():%Y-%m-%d}"
            )
        )


class AdminUsageApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = make_user(email="admin@example.com")
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.member = make_user(email="member@example.com", tier=Tier.SOLO)
        self.client = Client()

    def _seed(self):
        with collect_usage(self.member):
            emit_usage(FEATURE_CHAT, "gpt-5-mini", 10_000, 1_000)
        with collect_usage(self.member):
            emit_usage(FEATURE_CHAT, "gpt-5-mini", 10_000, 1_000)
            emit_usage("verification", "gpt-4o", 2_000, 200)

    def test_non_staff_gets_401(self):
        self.client.force_login(self.member)
        resp = self.client.get("/api/admin/usage/summary")
        self.assertEqual(resp.status_code, 401)

    def test_anonymous_gets_401(self):
        resp = self.client.get("/api/admin/usage/summary")
        self.assertEqual(resp.status_code, 401)

    def test_summary_aggregates(self):
        self._seed()
        self.client.force_login(self.staff)
        resp = self.client.get("/api/admin/usage/summary?days=7")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["prompt_tokens"], 22_000)
        self.assertEqual(data["completion_tokens"], 2_200)
        self.assertEqual(data["active_users"], 1)
        self.assertEqual(data["turns"], 2)
        features = {f["feature"] for f in data["features"]}
        self.assertEqual(features, {"chat", "verification"})
        models = {m["model"] for m in data["models"]}
        self.assertEqual(models, {"gpt-5-mini", "gpt-4o"})

    def test_daily_is_zero_filled(self):
        self._seed()
        self.client.force_login(self.staff)
        data = self.client.get("/api/admin/usage/daily?days=7").json()
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(sum(d["prompt_tokens"] for d in data["days"]), 22_000)

    def test_users_table_row(self):
        self._seed()
        self.client.force_login(self.staff)
        data = self.client.get("/api/admin/usage/users?days=7").json()
        self.assertEqual(len(data["users"]), 1)
        row = data["users"][0]
        self.assertEqual(row["email"], "member@example.com")
        self.assertEqual(row["turns"], 2)
        self.assertEqual(row["tier"], "solo")
        # gpt-5-mini: 20k @ $0.25/M + 2k @ $2/M = $0.009;
        # gpt-4o: 2k @ $2.5/M + 200 @ $10/M = $0.007 → ~$0.016 of a $10
        # monthly budget: comfortably "ok".
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["budget_usd"], 10.0)

    def test_bad_window_rejected(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/api/admin/usage/summary?days=13")
        self.assertEqual(resp.status_code, 400)


class AdminUsageFilterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = make_user(email="admin2@example.com")
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.member = make_user(email="member2@example.com", tier=Tier.SOLO)
        self.client = Client()
        self.client.force_login(self.staff)
        with collect_usage(self.member):
            emit_usage(FEATURE_CHAT, "gpt-5-mini", 10_000, 1_000)
            emit_usage("verification", "gpt-4o", 2_000, 200)
        emit_usage("embedding", "voyage-law-2", 5_000, 0)  # unattributed
        # Second chat row at a different timestamp: guards the DISTINCT
        # against the model's default created_at ordering leaking in (which
        # makes every row "unique" and duplicates the filter options).
        emit_usage(FEATURE_CHAT, "gpt-5-mini", 1_000, 100)

    def test_filters_endpoint_lists_dimensions(self):
        data = self.client.get("/api/admin/usage/filters").json()
        self.assertEqual(data["features"], ["chat", "embedding", "verification"])
        self.assertEqual(data["models"], ["gpt-4o", "gpt-5-mini", "voyage-law-2"])

    def test_summary_feature_filter(self):
        data = self.client.get(
            "/api/admin/usage/summary?days=7&feature=verification"
        ).json()
        self.assertEqual(data["prompt_tokens"], 2_000)
        self.assertEqual([f["feature"] for f in data["features"]], ["verification"])
        # Conversational-turn count is zero under a non-chat filter.
        self.assertEqual(data["turns"], 0)

    def test_summary_model_filter(self):
        data = self.client.get(
            "/api/admin/usage/summary?days=7&model=voyage-law-2"
        ).json()
        self.assertEqual(data["prompt_tokens"], 5_000)
        # Embedding traffic was unattributed → no active users in this slice.
        self.assertEqual(data["active_users"], 0)

    def test_daily_respects_filter(self):
        data = self.client.get(
            "/api/admin/usage/daily?days=7&feature=chat"
        ).json()
        self.assertEqual(sum(d["prompt_tokens"] for d in data["days"]), 11_000)

    def test_users_filter_keeps_unfiltered_budget(self):
        data = self.client.get(
            "/api/admin/usage/users?days=7&feature=verification"
        ).json()
        row = data["users"][0]
        self.assertEqual(row["prompt_tokens"], 2_000)  # filtered slice
        self.assertEqual(row["budget_usd"], 10.0)  # whole-spend budget basis
        self.assertEqual(row["turns"], 0)


class SideCallPriceTests(TestCase):
    def test_voyage_and_anthropic_prices(self):
        self.assertEqual(price_for("voyage-law-2"), (0.12, 0.0))
        self.assertEqual(price_for("rerank-2.5"), (0.05, 0.0))
        self.assertEqual(price_for("rerank-2.5-lite"), (0.02, 0.0))
        self.assertEqual(price_for("claude-haiku-4-5-20251001"), (1.00, 5.00))

    def test_embedding_emission_costs_input_only(self):
        # 1M embed tokens on voyage-law-2 = $0.12 exactly.
        self.assertEqual(cost_microusd("voyage-law-2", 1_000_000, 0), 120_000)
