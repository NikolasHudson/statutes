"""Staff-only user management API for the admin SPA (/admin/users).

Companion to :mod:`apps.api.admin_usage` and built on the same posture:
session-cookie auth via :class:`StaffSessionAuth` (so django-ninja's cookie
auth enforces the CSRF token on every unsafe method) plus ``is_staff`` on
every route. Unlike the usage dashboard this surface WRITES, so two more
rules apply on top of staffness:

* **Superuser fence.** Editing a staff/superuser account, or changing the
  ``is_staff`` flag at all, requires ``is_superuser``. Ordinary staff manage
  customers; only superusers manage staff. ``is_superuser`` itself is never
  editable through the API (shell only).
* **No self-service lockout/escalation.** A staff member cannot change their
  own ``is_active`` or ``is_staff`` here — deactivating yourself bricks the
  session mid-request, and self-(de)escalation should never be one PATCH away.

Every mutation writes an ``AuditEvent`` (ADMIN_USER_CHANGE / API_KEY_REVOKE)
with the target and the old→new values, so the append-only trail answers
"who changed whose account". Deactivation is a full kill-switch: sessions die
via ``ModelBackend.get_user`` and API keys / MCP OAuth tokens are filtered on
``user.is_active`` at verification time.

**Comping.** ``User.tier`` is no longer writable here: since billing landed it is
a derived cache of :func:`apps.tenancy.services.effective_plan`, so setting the
column would grant nothing and be reverted by the ``reconcile_tiers`` cron. Staff
now grant a plan by comping — ``comped_plan`` on the PATCH writes a comped
Subscription on the user's personal org via :func:`apps.tenancy.comping.set_comped_plan`,
and the tier follows from it. A plan that Stripe owns is refused with a 409: real
customers' plans change in Stripe, never by hand.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.audit import AuditEvent, record_event
from apps.accounts.models import APIKey, Tier, User
from apps.api.accounts import _get_profile
from apps.api.admin_usage import StaffSessionAuth, _usd
from apps.api.usage import user_budget_status
from apps.tenancy.comping import CompingRefused, plan_state, set_comped_plan

admin_users_router = Router(auth=StaffSessionAuth())

_MAX_BUDGET_USD = Decimal("100000")
_LIST_MAX_LIMIT = 500


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AdminUserRow(Schema):
    id: int
    email: str
    name: str
    tier: str
    is_staff: bool
    is_superuser: bool
    is_active: bool
    date_joined: dt.datetime
    last_login: dt.datetime | None
    onboarding_completed: bool
    active_api_keys: int
    # Month-to-date spend against the monthly budget (same semantics as the
    # usage dashboard's per-user columns).
    month_cost_usd: float
    budget_usd: float | None
    budget_used_pct: float | None
    budget_status: str


class AdminUsersResponse(Schema):
    total: int
    users: list[AdminUserRow]


class AdminKeyOut(Schema):
    id: int
    name: str
    prefix: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None


class AdminProfileOut(Schema):
    """Read-only support view of the user's profile. Deliberately excludes
    street address + preferences — what staff need to identify/assist an
    account, not the whole PII bundle."""

    organization: str
    role: str
    bar_number: str
    primary_jurisdiction: str
    phone: str
    city: str
    region: str
    timezone: str
    tos_version: str
    tos_accepted_at: dt.datetime | None


class AdminEventOut(Schema):
    id: int
    event_type: str
    outcome: str
    created_at: dt.datetime
    source_ip: str | None
    detail: dict


class AdminUsageSnapshot(Schema):
    month_cost_usd: float
    days30_cost_usd: float
    days30_tokens: int
    last_llm_activity: dt.datetime | None


class AdminOrgGrantOut(Schema):
    """A plan the user gets from an org OTHER than their personal one."""

    org_id: int
    org_name: str
    plan: str


class AdminPlanOut(Schema):
    """The comped-vs-paid picture of the user's personal (billing) org.

    ``comped_plan`` is what a staff comp writes and is NOT ``user.tier``: the tier
    is the max plan across every org the user belongs to, so a firm's member is
    ``firm`` with no comp at all (``other_grants`` says why).
    """

    comped_plan: str  # "free" = not comped
    source: str  # comped | stripe | none
    status: str  # subscription status, "none" when there is no row
    editable: bool  # False = Stripe owns this plan; PATCHing it is a 409
    org_id: int | None
    org_name: str
    org_status: str
    other_grants: list[AdminOrgGrantOut]


class AdminUserDetail(Schema):
    user: AdminUserRow
    first_name: str
    last_name: str
    # Per-user override of the tier's monthly budget; null = tier default.
    monthly_budget_override_usd: float | None
    # Where user.tier comes from, and whether staff may change it here.
    plan: AdminPlanOut
    profile: AdminProfileOut
    api_keys: list[AdminKeyOut]
    usage: AdminUsageSnapshot
    events: list[AdminEventOut]
    # UI hints only — the server re-checks both on every write.
    can_edit: bool
    can_edit_staff_flag: bool


class AdminUserPatch(Schema):
    """All optional — the client sends only what changes (``exclude_unset``
    distinguishes "omitted" from "set to null", which clears the budget)."""

    # The staff-granted plan on the user's personal org. "free" un-comps.
    comped_plan: str | None = None
    monthly_budget_usd: float | None = None
    is_active: bool | None = None
    is_staff: bool | None = None
    # Retired. Declared only so a stale client that still sends it gets a loud
    # 400 instead of a silent no-op — tier is derived from billing now.
    tier: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_target(user_id: int) -> User:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise HttpError(404, "user not found") from exc


def _can_edit(actor: User, target: User) -> bool:
    """Ordinary staff manage customers; staff/superuser accounts are
    superuser-territory (including a superuser's own row, for tier/budget)."""
    if target.is_staff or target.is_superuser:
        return actor.is_superuser
    return True


def _month_start(now: dt.datetime) -> dt.datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _plan_out(user: User) -> AdminPlanOut:
    state = plan_state(user)
    return AdminPlanOut(
        comped_plan=state.comped_plan,
        source=state.source,
        status=state.status,
        editable=state.editable,
        org_id=state.org_id,
        org_name=state.org_name,
        org_status=state.org_status,
        other_grants=[
            AdminOrgGrantOut(org_id=g.org_id, org_name=g.org_name, plan=g.plan)
            for g in state.other_grants
        ],
    )


def _row(
    user: User,
    *,
    month_cost_microusd: int,
    active_keys: int,
    onboarding_completed: bool,
) -> AdminUserRow:
    month_spent = _usd(month_cost_microusd)
    budget, pct, status = user_budget_status(user, month_spent)
    return AdminUserRow(
        id=user.id,
        email=user.email,
        name=user.full_name,
        tier=user.tier,
        is_staff=user.is_staff,
        is_superuser=user.is_superuser,
        is_active=user.is_active,
        date_joined=user.date_joined,
        last_login=user.last_login,
        onboarding_completed=onboarding_completed,
        active_api_keys=active_keys,
        month_cost_usd=month_spent,
        budget_usd=budget,
        budget_used_pct=pct,
        budget_status=status,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@admin_users_router.get("", response=AdminUsersResponse)
def list_users(
    request,
    q: str = "",
    tier: str = "",
    status: str = "",
    limit: int = 200,
    offset: int = 0,
):
    """Directory of all accounts (unlike /admin/usage/users, which only lists
    users with LLM activity in the window). ``status`` is one of
    ``active`` / ``deactivated`` / ``staff``; empty = everyone."""
    from apps.api.models import LlmUsage

    limit = max(1, min(limit, _LIST_MAX_LIMIT))
    offset = max(0, offset)

    users = User.objects.all().order_by("email")
    if q.strip():
        needle = q.strip()
        users = users.filter(
            Q(email__icontains=needle) | Q(full_name__icontains=needle)
        )
    if tier:
        if tier not in Tier.values:
            raise HttpError(400, f"unknown tier {tier!r}")
        users = users.filter(tier=tier)
    if status == "active":
        users = users.filter(is_active=True)
    elif status == "deactivated":
        users = users.filter(is_active=False)
    elif status == "staff":
        users = users.filter(is_staff=True)
    elif status:
        raise HttpError(400, "status must be active, deactivated or staff")

    total = users.count()
    page = list(users[offset : offset + limit])
    ids = [u.id for u in page]

    month_costs = {
        r["user"]: r["cost"] or 0
        for r in LlmUsage.objects.filter(
            created_at__gte=_month_start(timezone.now()), user_id__in=ids
        )
        .values("user")
        .annotate(cost=Sum("cost_microusd"))
    }
    key_counts = {
        r["user"]: r["n"]
        for r in APIKey.objects.filter(user_id__in=ids, revoked_at__isnull=True)
        .values("user")
        .annotate(n=Count("id"))
    }
    onboarded = set(
        User.objects.filter(
            id__in=ids, profile__onboarding_completed=True
        ).values_list("id", flat=True)
    )

    return AdminUsersResponse(
        total=total,
        users=[
            _row(
                u,
                month_cost_microusd=month_costs.get(u.id, 0),
                active_keys=key_counts.get(u.id, 0),
                onboarding_completed=u.id in onboarded,
            )
            for u in page
        ],
    )


_DETAIL_EVENT_LIMIT = 20


@admin_users_router.get("/{user_id}", response=AdminUserDetail)
def user_detail(request, user_id: int):
    from apps.api.models import LlmUsage

    actor: User = request.auth
    target = _get_target(user_id)
    profile = _get_profile(target)
    now = timezone.now()

    month = LlmUsage.objects.filter(
        user=target, created_at__gte=_month_start(now)
    ).aggregate(cost=Sum("cost_microusd"))
    d30 = LlmUsage.objects.filter(
        user=target, created_at__gte=now - dt.timedelta(days=30)
    ).aggregate(
        cost=Sum("cost_microusd"),
        pt=Sum("prompt_tokens"),
        ct=Sum("completion_tokens"),
    )
    last_llm = LlmUsage.objects.filter(user=target).aggregate(
        last=Max("created_at")
    )["last"]

    keys = list(
        APIKey.objects.filter(user=target, revoked_at__isnull=True).order_by(
            "-created_at"
        )
    )
    # Three ways an event concerns this account: they did it (actor), they
    # presented its email pre-login (failed logins, lockouts), or an admin
    # did something TO it (admin changes / key revocations record the staff
    # member as actor and put the target in detail.target_user_id).
    events = list(
        AuditEvent.objects.filter(
            Q(actor=target)
            | Q(actor_email=target.email.lower())
            | Q(detail__target_user_id=target.id)
        ).order_by("-created_at")[:_DETAIL_EVENT_LIMIT]
    )

    return AdminUserDetail(
        user=_row(
            target,
            month_cost_microusd=month["cost"] or 0,
            active_keys=len(keys),
            onboarding_completed=profile.onboarding_completed,
        ),
        first_name=target.first_name,
        last_name=target.last_name,
        monthly_budget_override_usd=(
            float(target.monthly_budget_usd)
            if target.monthly_budget_usd is not None
            else None
        ),
        plan=_plan_out(target),
        profile=AdminProfileOut(
            organization=profile.organization,
            role=profile.role,
            bar_number=profile.bar_number,
            primary_jurisdiction=profile.primary_jurisdiction,
            phone=profile.phone,
            city=profile.city,
            region=profile.region,
            timezone=profile.timezone,
            tos_version=profile.tos_version,
            tos_accepted_at=profile.tos_accepted_at,
        ),
        api_keys=[
            AdminKeyOut(
                id=k.id,
                name=k.name,
                prefix=k.prefix,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
            )
            for k in keys
        ],
        usage=AdminUsageSnapshot(
            month_cost_usd=_usd(month["cost"]),
            days30_cost_usd=_usd(d30["cost"]),
            days30_tokens=(d30["pt"] or 0) + (d30["ct"] or 0),
            last_llm_activity=last_llm,
        ),
        events=[
            AdminEventOut(
                id=e.id,
                event_type=e.event_type,
                outcome=e.outcome,
                created_at=e.created_at,
                source_ip=e.source_ip,
                detail=e.detail or {},
            )
            for e in events
        ],
        can_edit=_can_edit(actor, target),
        can_edit_staff_flag=actor.is_superuser and actor.pk != target.pk,
    )


@admin_users_router.patch("/{user_id}", response=AdminUserDetail)
def update_user(request, user_id: int, payload: AdminUserPatch):
    actor: User = request.auth
    target = _get_target(user_id)
    data = payload.model_dump(exclude_unset=True)

    if not _can_edit(actor, target):
        raise HttpError(403, "only a superuser may modify a staff account")
    if "is_staff" in data and not actor.is_superuser:
        raise HttpError(403, "only a superuser may change the staff flag")
    if actor.pk == target.pk and ("is_staff" in data or "is_active" in data):
        raise HttpError(400, "you cannot change your own staff or active status")
    if target.is_superuser and data.get("is_active") is False:
        # A superuser account is deactivated from the shell, deliberately —
        # not from a browser tab where one click strands the whole admin.
        raise HttpError(400, "superuser accounts cannot be deactivated here")
    if "tier" in data:
        # A stale SPA bundle. Writing the column would grant nothing and be
        # reverted by reconcile_tiers, so fail loudly rather than lie.
        raise HttpError(
            400,
            "tier is derived from billing and is no longer writable — send "
            "comped_plan to grant (or revoke) a staff comp",
        )

    changes: dict[str, dict] = {}
    update_fields: list[str] = []

    # One transaction for the whole PATCH: the comp writes through the tenancy
    # service (a subscription row + every affected member's tier), so a later
    # validation error must not leave a plan granted with nothing else applied.
    with transaction.atomic():
        # --- The comp. First, because it is the only field that can 409. ---
        if "comped_plan" in data:
            new_plan = data["comped_plan"] or ""
            if new_plan not in Tier.values:
                raise HttpError(400, f"unknown plan {new_plan!r}")
            before = plan_state(target)
            if new_plan != before.comped_plan:
                if not before.editable:
                    # A Stripe-backed plan is Stripe's. (set_comped_plan refuses
                    # it too — same fence, with the HTTP status attached.)
                    raise HttpError(
                        409,
                        "this account's plan is billed through Stripe — change "
                        "or cancel it in Stripe, not here",
                    )
                old_tier = target.tier
                try:
                    set_comped_plan(target, new_plan, actor=actor)
                except CompingRefused as exc:
                    raise HttpError(409, str(exc)) from exc
                changes["comped_plan"] = {
                    "old": before.comped_plan,
                    "new": new_plan,
                    "org_id": before.org_id,
                }
                # ...and the tier it derived. set_comped_plan already wrote that
                # column (via sync_user_tier), so it is NOT in update_fields.
                if target.tier != old_tier:
                    changes["tier"] = {
                        "old": old_tier,
                        "new": target.tier,
                        "derived": True,
                    }

        if "monthly_budget_usd" in data:
            raw = data["monthly_budget_usd"]
            if raw is None:
                new_budget = None
            else:
                try:
                    new_budget = Decimal(str(raw)).quantize(Decimal("0.01"))
                except InvalidOperation as exc:
                    raise HttpError(400, "invalid budget amount") from exc
                if new_budget < 0 or new_budget > _MAX_BUDGET_USD:
                    raise HttpError(
                        400, f"budget must be between 0 and {_MAX_BUDGET_USD}"
                    )
            if new_budget != target.monthly_budget_usd:
                changes["monthly_budget_usd"] = {
                    "old": (
                        float(target.monthly_budget_usd)
                        if target.monthly_budget_usd is not None
                        else None
                    ),
                    "new": float(new_budget) if new_budget is not None else None,
                }
                target.monthly_budget_usd = new_budget
                update_fields.append("monthly_budget_usd")

        for flag in ("is_active", "is_staff"):
            if flag in data:
                new_val = bool(data[flag])
                if new_val != getattr(target, flag):
                    changes[flag] = {"old": getattr(target, flag), "new": new_val}
                    setattr(target, flag, new_val)
                    update_fields.append(flag)

        if update_fields:
            target.save(update_fields=update_fields)
        # `changes` can be non-empty with NO update_fields: a comp writes the
        # tier through the tenancy service, not through this row.
        if changes:
            record_event(
                event_type=AuditEvent.Event.ADMIN_USER_CHANGE,
                request=request,
                actor=actor,
                outcome=AuditEvent.Outcome.SUCCESS,
                detail={
                    "target_user_id": target.id,
                    "target_email": target.email,
                    "changes": changes,
                },
            )

    return user_detail(request, user_id)


@admin_users_router.post("/{user_id}/api-keys/{key_id}/revoke", response=dict)
def revoke_user_key(request, user_id: int, key_id: int):
    """Admin revocation of a user's API key — the incident-response lever
    (key leaked, account compromised) that doesn't require deactivating the
    whole account."""
    actor: User = request.auth
    target = _get_target(user_id)
    if not _can_edit(actor, target):
        raise HttpError(403, "only a superuser may modify a staff account")
    try:
        key = APIKey.objects.get(pk=key_id, user=target, revoked_at__isnull=True)
    except APIKey.DoesNotExist as exc:
        raise HttpError(404, "key not found") from exc
    key.revoked_at = timezone.now()
    key.save(update_fields=["revoked_at"])
    record_event(
        event_type=AuditEvent.Event.API_KEY_REVOKE,
        request=request,
        actor=actor,
        outcome=AuditEvent.Outcome.SUCCESS,
        detail={
            "key_id": key.id,
            "prefix": key.prefix,
            "target_user_id": target.id,
            "target_email": target.email,
            "by_admin": True,
        },
    )
    return {"status": "revoked", "id": key_id}
