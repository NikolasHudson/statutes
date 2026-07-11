"""Staff-only usage/spend API for the admin dashboard (/admin/usage in the SPA).

First staff-gated JSON surface in the app: session-cookie auth (so CSRF rules
match the rest of the browser API) plus an ``is_staff`` check on every route.
Read-only aggregates over :class:`apps.api.models.LlmUsage` — numbers only, by
construction, since the underlying table stores no content.

Window semantics: ``days`` covers today plus the (days-1) preceding calendar
days. Budget columns in ``/users`` are month-to-date against the MONTHLY
budget regardless of ``days`` — budgets are monthly objects; mixing them into
an arbitrary window would misread as "over budget for the last 7 days".
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Count, Max, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import SessionAuth

from apps.accounts.models import User
from apps.api.usage import FEATURE_CHAT, FEATURE_EMAIL, user_budget_status


class StaffSessionAuth(SessionAuth):
    """Session auth that additionally requires ``is_staff``.

    Returning ``None`` from authenticate yields a 401 for both "not signed
    in" and "signed in but not staff" — deliberately not a 403, so the
    endpoint doesn't confirm to a curious non-staff user that it exists.
    """

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None or not getattr(user, "is_staff", False):
            return None
        return user


staff_auth = StaffSessionAuth()
admin_usage_router = Router(auth=staff_auth)

_ALLOWED_WINDOWS = {7, 30, 90}
_TURN_FEATURES = (FEATURE_CHAT, FEATURE_EMAIL)


class FeatureSpend(Schema):
    feature: str
    cost_usd: float
    total_tokens: int


class ModelSpend(Schema):
    model: str
    total_tokens: int
    cost_usd: float


class UsageSummary(Schema):
    days: int
    start: dt.date
    end: dt.date
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    prev_cost_usd: float
    active_users: int
    registered_users: int
    turns: int
    features: list[FeatureSpend]
    models: list[ModelSpend]


class DailyUsage(Schema):
    date: dt.date
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class DailyResponse(Schema):
    days: list[DailyUsage]


class UserUsage(Schema):
    id: int
    email: str
    name: str
    tier: str
    is_staff: bool
    turns: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    budget_usd: float | None
    budget_used_pct: float | None
    status: str
    last_active: dt.datetime | None


class UsersResponse(Schema):
    users: list[UserUsage]


class FilterOptions(Schema):
    features: list[str]
    models: list[str]


def _apply_filters(qs, feature: str | None, model: str | None):
    """Exact-match dimension filters shared by all three aggregate routes.
    Empty string and None both mean "no filter" (the SPA sends nothing)."""
    if feature:
        qs = qs.filter(feature=feature)
    if model:
        qs = qs.filter(model=model)
    return qs


def _window(days: int) -> tuple[dt.datetime, dt.date, dt.date]:
    if days not in _ALLOWED_WINDOWS:
        raise HttpError(400, f"days must be one of {sorted(_ALLOWED_WINDOWS)}")
    now = timezone.now()
    end = now.date()
    start_date = end - dt.timedelta(days=days - 1)
    start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(
        days=days - 1
    )
    return start_dt, start_date, end


def _usd(microusd: int | None) -> float:
    return round((microusd or 0) / 1_000_000, 4)


@admin_usage_router.get("/filters", response=FilterOptions)
def usage_filters(request):
    """Distinct dimension values for the dashboard's filter dropdowns —
    all-time, so a filter that matches only old traffic still appears."""
    from apps.api.models import LlmUsage

    # .order_by() clears the model's default ordering — otherwise Django adds
    # created_at to the DISTINCT projection and every row comes back "unique".
    return FilterOptions(
        features=sorted(
            LlmUsage.objects.order_by().values_list("feature", flat=True).distinct()
        ),
        models=sorted(
            m
            for m in LlmUsage.objects.order_by()
            .values_list("model", flat=True)
            .distinct()
            if m
        ),
    )


@admin_usage_router.get("/summary", response=UsageSummary)
def usage_summary(request, days: int = 30, feature: str | None = None, model: str | None = None):
    from apps.api.models import LlmUsage

    start_dt, start_date, end_date = _window(days)
    rows = _apply_filters(LlmUsage.objects.filter(created_at__gte=start_dt), feature, model)

    totals = rows.aggregate(
        pt=Sum("prompt_tokens"),
        ct=Sum("completion_tokens"),
        cost=Sum("cost_microusd"),
        users=Count("user", distinct=True),
    )
    # Turns = distinct collected turns on the conversational features only
    # (verification side-calls share their turn's request_id already; the
    # standalone verify tool gets its own request_id and is excluded here).
    turns = (
        rows.filter(feature__in=_TURN_FEATURES)
        .exclude(request_id=None)
        .values("request_id")
        .distinct()
        .count()
    )

    prev = _apply_filters(
        LlmUsage.objects.filter(
            created_at__gte=start_dt - dt.timedelta(days=days),
            created_at__lt=start_dt,
        ),
        feature,
        model,
    ).aggregate(cost=Sum("cost_microusd"))

    features = [
        FeatureSpend(
            feature=r["feature"],
            cost_usd=_usd(r["cost"]),
            total_tokens=(r["pt"] or 0) + (r["ct"] or 0),
        )
        for r in rows.values("feature")
        .annotate(cost=Sum("cost_microusd"), pt=Sum("prompt_tokens"), ct=Sum("completion_tokens"))
        .order_by("-cost")
    ]
    models = [
        ModelSpend(
            model=r["model"] or "(unknown)",
            total_tokens=(r["pt"] or 0) + (r["ct"] or 0),
            cost_usd=_usd(r["cost"]),
        )
        for r in rows.values("model")
        .annotate(cost=Sum("cost_microusd"), pt=Sum("prompt_tokens"), ct=Sum("completion_tokens"))
        .order_by("-pt")
    ]

    pt = totals["pt"] or 0
    ct = totals["ct"] or 0
    return UsageSummary(
        days=days,
        start=start_date,
        end=end_date,
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=pt + ct,
        cost_usd=_usd(totals["cost"]),
        prev_cost_usd=_usd(prev["cost"]),
        active_users=totals["users"] or 0,
        registered_users=User.objects.filter(is_active=True).count(),
        turns=turns,
        features=features,
        models=models,
    )


@admin_usage_router.get("/daily", response=DailyResponse)
def usage_daily(request, days: int = 30, feature: str | None = None, model: str | None = None):
    from apps.api.models import LlmUsage

    start_dt, start_date, end_date = _window(days)
    by_day = {
        r["day"]: r
        for r in _apply_filters(
            LlmUsage.objects.filter(created_at__gte=start_dt), feature, model
        )
        .values(day=TruncDate("created_at"))
        .annotate(
            pt=Sum("prompt_tokens"),
            ct=Sum("completion_tokens"),
            cost=Sum("cost_microusd"),
        )
    }
    out: list[DailyUsage] = []
    d = start_date
    while d <= end_date:
        r = by_day.get(d)
        out.append(
            DailyUsage(
                date=d,
                prompt_tokens=(r or {}).get("pt") or 0,
                completion_tokens=(r or {}).get("ct") or 0,
                cost_usd=_usd((r or {}).get("cost")),
            )
        )
        d += dt.timedelta(days=1)
    return DailyResponse(days=out)


@admin_usage_router.get("/users", response=UsersResponse)
def usage_users(request, days: int = 30, feature: str | None = None, model: str | None = None):
    """Per-user aggregates for the window (honouring feature/model filters).
    Budget columns stay UNFILTERED month-to-date figures — a budget is a
    property of the user's whole spend, not of the currently filtered slice."""
    from apps.api.models import LlmUsage

    start_dt, _, _ = _window(days)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    window_rows = (
        _apply_filters(
            LlmUsage.objects.filter(created_at__gte=start_dt, user__isnull=False),
            feature,
            model,
        )
        .values("user")
        .annotate(
            pt=Sum("prompt_tokens"),
            ct=Sum("completion_tokens"),
            cost=Sum("cost_microusd"),
            last=Max("created_at"),
        )
    )
    turn_counts = {
        r["user"]: r["n"]
        for r in _apply_filters(
            LlmUsage.objects.filter(
                created_at__gte=start_dt,
                user__isnull=False,
                feature__in=_TURN_FEATURES,
                request_id__isnull=False,
            ),
            feature,
            model,
        )
        .values("user")
        .annotate(n=Count("request_id", distinct=True))
    }
    month_costs = {
        r["user"]: r["cost"] or 0
        for r in LlmUsage.objects.filter(
            created_at__gte=month_start, user__isnull=False
        )
        .values("user")
        .annotate(cost=Sum("cost_microusd"))
    }

    stats = {r["user"]: r for r in window_rows}
    users = User.objects.filter(id__in=stats).only(
        "id", "email", "full_name", "tier", "is_staff", "monthly_budget_usd"
    )

    out: list[UserUsage] = []
    for u in users:
        r = stats[u.id]
        month_spent = _usd(month_costs.get(u.id, 0))
        budget, pct, status = user_budget_status(u, month_spent)
        out.append(
            UserUsage(
                id=u.id,
                email=u.email,
                name=u.full_name,
                tier=u.tier,
                is_staff=u.is_staff,
                turns=turn_counts.get(u.id, 0),
                prompt_tokens=r["pt"] or 0,
                completion_tokens=r["ct"] or 0,
                cost_usd=_usd(r["cost"]),
                budget_usd=budget,
                budget_used_pct=pct,
                status=status,
                last_active=r["last"],
            )
        )
    out.sort(key=lambda x: -x.cost_usd)
    return UsersResponse(users=out)
