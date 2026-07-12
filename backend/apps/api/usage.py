"""Per-user LLM token/cost accounting + dollar-denominated budget caps.

Three jobs, one module:

* **Capture** — :func:`emit_usage` records one LLM round-trip (model +
  prompt/completion token counts). Call sites live next to every
  ``client.chat.completions.create(...)`` we own. Cost is snapshotted at
  write time from :data:`PRICES_PER_MTOK` so a later price change never
  rewrites history.

* **Attribution** — :func:`collect_usage` is a context manager the HTTP /
  worker entry points wrap around a turn. While active, emissions buffer
  into a per-request sink and flush as ``LlmUsage`` rows attributed to the
  user (and stamped with one shared ``request_id`` = one turn, plus the
  user's billing org for future org-level reporting — budgets stay per-user).
  Outside any collector (cron jobs, shell), emissions write immediately as
  unattributed rows so platform totals stay complete.

  Confidentiality: this table is deliberately CONTENT-FREE — numbers only,
  never the question or answer. That is what makes per-user attribution
  compatible with the unattributed-trace posture of ChatTrace et al.
  (apps/api/models.py): the traces keep the content without the user; this
  keeps the user without the content.

* **Enforcement** — :func:`enforce_token_budget` raises 429 when the user's
  daily or monthly dollar budget is exhausted (503 when the global platform
  ceiling is). Called from ``_enforce_chat_quota`` so every spend surface
  (chat, chat/stream, verify) is gated in one place. Budgets are DOLLARS,
  not tokens: one number stays meaningful when the model mix changes.
  Checks run pre-turn, so a turn in flight finishes — slight overshoot is
  accepted rather than cutting a stream off mid-answer.

Nothing in here may ever break a chat: capture swallows its own errors,
and only the explicit enforcement path raises (HttpError, on purpose).
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from ninja.errors import HttpError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Price table — USD per 1M tokens (input, output), matched by LONGEST prefix
# so dated variants ("gpt-5-mini-2025-08-07") resolve to their base price.
# Update when OpenAI reprices; existing rows keep their written-down cost.
# An unknown model records tokens with cost 0 and logs a warning — visible
# in the dashboard as "free" traffic, which is the prompt to add a price.
# ---------------------------------------------------------------------------
PRICES_PER_MTOK: list[tuple[str, float, float]] = sorted(
    [
        ("gpt-5-mini", 0.25, 2.00),
        ("gpt-5-nano", 0.05, 0.40),
        ("gpt-5", 1.25, 10.00),
        ("gpt-4o-mini", 0.15, 0.60),
        ("gpt-4o", 2.50, 10.00),
        # Anthropic (query expansion).
        ("claude-haiku-4-5", 1.00, 5.00),
        # Voyage: embeddings and rerank bill input-only (output price 0).
        ("voyage-law-2", 0.12, 0.0),
        ("voyage-3-large", 0.18, 0.0),
        ("rerank-2.5-lite", 0.02, 0.0),
        ("rerank-2.5", 0.05, 0.0),
    ],
    key=lambda row: -len(row[0]),
)

# Per-tier (daily, monthly) budgets in USD. Keyed by accounts.models.Tier
# values. ``User.monthly_budget_usd`` overrides the monthly figure per user;
# staff are exempt entirely. Tuned deliberately generous relative to observed
# spend (a heavy real user runs ~$10-20/mo) — the cap is a runaway-stop, not
# a metering business model.
TIER_BUDGETS_USD: dict[str, tuple[float, float]] = {
    "free": (0.25, 2.00),
    "solo": (0.50, 10.00),
    "firm": (1.00, 25.00),
    "custom": (2.00, 50.00),
}
_FALLBACK_BUDGET = TIER_BUDGETS_USD["free"]

# Feature slugs (free-form CharField on the row; centralized here so the
# dashboard's labels and the emitters can't drift silently).
FEATURE_CHAT = "chat"
FEATURE_EMAIL = "email"
FEATURE_VERIFICATION = "verification"
FEATURE_QUERY_REWRITE = "query_rewrite"
FEATURE_APPLICABILITY = "applicability"
FEATURE_WEB_CURRENCY = "web_currency"
FEATURE_QUERY_EXPANSION = "query_expansion"
FEATURE_EMBEDDING = "embedding"
FEATURE_RERANK = "rerank"
FEATURE_TREATMENT = "treatment"
FEATURE_RETRIEVAL_JUDGE = "retrieval_judge"


def price_for(model: str) -> tuple[float, float]:
    for prefix, inp, out in PRICES_PER_MTOK:
        if model.startswith(prefix):
            return inp, out
    logger.warning("no price entry for model %r — recording cost 0", model)
    return 0.0, 0.0


def cost_microusd(model: str, prompt_tokens: int, completion_tokens: int) -> int:
    """Cost in integer micro-dollars. With prices in USD/Mtok this is simply
    ``tokens * price`` — exact integer math, no float drift in storage."""
    inp, out = price_for(model)
    return int(round(prompt_tokens * inp + completion_tokens * out))


# ---------------------------------------------------------------------------
# Capture + attribution
# ---------------------------------------------------------------------------

# The active per-request sink. Sync Django: one request per thread, and the
# streaming generators are consumed on the request thread, so a ContextVar
# gives every nested service (chat loop, verification checker, query rewrite)
# the same sink without threading a parameter through five layers.
_sink: ContextVar[list | None] = ContextVar("llm_usage_sink", default=None)


def emit_usage(
    feature: str, model: str, prompt_tokens: int, completion_tokens: int
) -> None:
    """Record one LLM round-trip. Never raises. Inside a collector the event
    buffers for attributed flush; outside one it writes an unattributed row
    immediately (batch jobs still count toward platform totals)."""
    try:
        pt = int(prompt_tokens or 0)
        ct = int(completion_tokens or 0)
        if pt <= 0 and ct <= 0:
            return
        event = {
            "feature": feature,
            "model": (model or "")[:64],
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "cost_microusd": cost_microusd(model or "", pt, ct),
        }
        sink = _sink.get()
        if sink is not None:
            sink.append(event)
            return
        from apps.api.models import LlmUsage

        # Unattributed (cron/shell): no user, therefore no billing org.
        LlmUsage.objects.create(user=None, org=None, request_id=None, **event)
    except Exception:  # noqa: BLE001 — accounting must never break the caller
        logger.exception("emit_usage failed")


def emit_completion_usage(feature: str, completion, fallback_model: str = "") -> None:
    """Convenience: emit from an OpenAI chat-completion (or usage-bearing
    stream chunk). Tolerates SDK objects and dicts; never raises."""
    try:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return
        model = getattr(completion, "model", "") or fallback_model
        emit_usage(
            feature,
            model,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )
    except Exception:  # noqa: BLE001
        logger.exception("emit_completion_usage failed")


def _billing_org_id(user) -> int | None:
    """The user's billing org, stamped onto each row for future org-level
    reporting. Read-only and best-effort: a user without a personal org (a shell-
    created account) simply gets a null org, and any error here must not cost us
    the usage row."""
    try:
        from apps.tenancy.services import billing_org

        org = billing_org(user)
        return org.pk if org is not None else None
    except Exception:  # noqa: BLE001 — accounting must never break the caller
        logger.exception("billing_org lookup failed")
        return None


@contextmanager
def collect_usage(user, relabel: dict[str, str] | None = None):
    """Attribute every emission inside the block to ``user`` as one turn.

    ``relabel`` maps emitted feature slugs on flush — the mail worker reuses
    the chat loop verbatim, so it passes ``{"chat": "email"}`` and the rows
    land under the email feature without the loop knowing its caller.
    """
    events: list = []
    token = _sink.set(events)
    try:
        yield events
    finally:
        _sink.reset(token)
        if events:
            try:
                from apps.api.models import LlmUsage

                request_id = uuid.uuid4()
                relabel = relabel or {}
                org_id = _billing_org_id(user)
                LlmUsage.objects.bulk_create(
                    LlmUsage(
                        user=user,
                        org_id=org_id,
                        request_id=request_id,
                        feature=relabel.get(e["feature"], e["feature"]),
                        model=e["model"],
                        prompt_tokens=e["prompt_tokens"],
                        completion_tokens=e["completion_tokens"],
                        cost_microusd=e["cost_microusd"],
                    )
                    for e in events
                )
            except Exception:  # noqa: BLE001 — see module docstring
                logger.exception("collect_usage flush failed")


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


def budgets_for(user) -> tuple[float, float]:
    """(daily_usd, monthly_usd) for a user; monthly honours the per-user
    override column."""
    daily, monthly = TIER_BUDGETS_USD.get(user.tier, _FALLBACK_BUDGET)
    override = getattr(user, "monthly_budget_usd", None)
    if override is not None:
        monthly = float(override)
    return daily, monthly


def _spent_usd(user, since) -> float:
    from django.db.models import Sum

    from apps.api.models import LlmUsage

    total = (
        LlmUsage.objects.filter(user=user, created_at__gte=since).aggregate(
            s=Sum("cost_microusd")
        )["s"]
        or 0
    )
    return total / 1_000_000


def month_to_date_usd(user) -> float:
    now = timezone.now()
    return _spent_usd(user, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))


def enforce_token_budget(user) -> None:
    """Raise 429 (user daily/monthly budget) or 503 (global platform ceiling)
    BEFORE a turn starts. Staff are exempt from the per-user budgets but not
    from the global ceiling — the ceiling protects the OpenAI bill itself."""
    now = timezone.now()

    # Global ceiling: whole-platform month-to-date spend, cached briefly so
    # every chat request doesn't pay a full-table aggregate.
    global_budget = float(settings.CHAT_GLOBAL_MONTHLY_BUDGET_USD)
    if global_budget > 0:
        cache_key = f"usage:globalcost:{now:%Y-%m}"
        global_spent = cache.get(cache_key)
        if global_spent is None:
            from django.db.models import Sum

            from apps.api.models import LlmUsage

            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            global_spent = (
                LlmUsage.objects.filter(created_at__gte=month_start).aggregate(
                    s=Sum("cost_microusd")
                )["s"]
                or 0
            ) / 1_000_000
            cache.set(cache_key, global_spent, timeout=300)
        if global_spent >= global_budget:
            raise HttpError(
                503,
                "The assistant is temporarily unavailable (monthly capacity "
                "reached). Please try again next month or contact support.",
            )

    if user.is_staff:
        return

    daily_budget, monthly_budget = budgets_for(user)

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if monthly_budget > 0 and _spent_usd(user, month_start) >= monthly_budget:
        raise HttpError(
            429,
            "Monthly research budget reached. It resets on the 1st. Saved "
            "research and reading are unaffected — only new assistant "
            "questions are paused. Contact support to raise your limit.",
        )

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if daily_budget > 0 and _spent_usd(user, day_start) >= daily_budget:
        raise HttpError(
            429,
            "Daily research budget reached. It resets at midnight. Saved "
            "research and reading are unaffected — only new assistant "
            "questions are paused. Contact support if you need a higher limit.",
        )


def user_budget_status(user, month_spent_usd: float) -> tuple[float | None, float | None, str]:
    """(budget_usd, used_pct, status) for the admin dashboard — monthly basis.
    Status thresholds match the UI: >=100% capped, >=80% near."""
    if user.is_staff:
        return None, None, "exempt"
    _, monthly = budgets_for(user)
    if monthly <= 0:
        return None, None, "exempt"
    pct = month_spent_usd / monthly * 100
    if pct >= 100:
        status = "capped"
    elif pct >= 80:
        status = "near"
    else:
        status = "ok"
    return monthly, round(pct, 1), status


__all__ = [
    "FEATURE_APPLICABILITY",
    "FEATURE_CHAT",
    "FEATURE_EMAIL",
    "FEATURE_EMBEDDING",
    "FEATURE_QUERY_EXPANSION",
    "FEATURE_QUERY_REWRITE",
    "FEATURE_RERANK",
    "FEATURE_RETRIEVAL_JUDGE",
    "FEATURE_TREATMENT",
    "FEATURE_VERIFICATION",
    "FEATURE_WEB_CURRENCY",
    "collect_usage",
    "emit_completion_usage",
    "emit_usage",
    "enforce_token_budget",
    "month_to_date_usd",
    "user_budget_status",
]
