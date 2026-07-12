"""Stripe-backed billing endpoints (``/api/billing/*``).

Four routes, three of them boring and one that matters:

* ``GET /subscription`` — the billing page's whole state. **DB only.** It does not
  touch Stripe and so it keeps working with no Stripe account at all: a comped or
  backfilled subscription has no Stripe object behind it, and a dev box must still
  render the page. This is the one billing route that never 503s.
* ``POST /checkout`` / ``POST /portal`` — owner/admin only, and they *are* Stripe
  calls: with no ``STRIPE_SECRET_KEY`` they answer a clean 503 rather than blowing
  up with an auth error from inside the Stripe SDK.
* ``POST /webhook`` — ``auth=None`` and CSRF-exempt, because the caller is Stripe,
  not a browser. It is authenticated by *signature* instead: an unsigned or
  mis-signed body is a 400 and never reaches a handler. ``NinjaAPI`` is built with
  ``csrf=False`` (CSRF is attached per-router on the cookie surface — see
  ``apps/api/session_auth.py``), so ``auth=None`` here is genuinely exempt.

The response shapes in §6a of BILLING_PLAN.md are **frozen** — the SPA shipped
against these exact keys — so the schemas below are written out field by field
rather than derived, and ``grace_ends_at`` is computed server-side so the client
never has to know the grace-window length.

Authorization is ``tenancy.services.role_of``: owner/admin may spend money, a
member may only look. Nav gating in the SPA is decoration; this is the fence.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.api.session_auth import session_auth
from apps.tenancy import services as tenancy
from apps.tenancy.models import Organization, OrgMembership, Subscription

from . import plans, stripe_api, webhooks
from .stripe_api import BillingNotConfigured

logger = logging.getLogger(__name__)

billing_router = Router(tags=["billing"])

MANAGE_ROLES = {OrgMembership.Role.OWNER, OrgMembership.Role.ADMIN}

# Where Checkout and the Billing Portal send the browser back to.
BILLING_PAGE_PATH = "/account/billing"


# ---------------------------------------------------------------------------
# Schemas — §6a, frozen. Do not rename a key without changing the SPA.
# ---------------------------------------------------------------------------


class OrgOut(Schema):
    id: int
    name: str
    is_personal: bool
    status: str


class SubscriptionOut(Schema):
    org: OrgOut
    plan: str  # free | solo | firm | custom
    status: str  # trial | active | past_due | canceled | unpaid | none
    seats_used: int
    seats_purchased: int
    current_period_end: dt.datetime | None
    cancel_at_period_end: bool
    trial_end: dt.datetime | None
    past_due_since: dt.datetime | None
    grace_ends_at: dt.datetime | None
    can_manage: bool


class CheckoutIn(Schema):
    plan: str
    seats: int | None = None


class UrlOut(Schema):
    url: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _billing_org(request) -> Organization:
    """The org whose bill the caller is looking at.

    ``tenancy.billing_org`` — the caller's personal org — is the billing anchor by
    design (BILLING_PLAN §1: billing attaches to an org, always; a solo signup gets
    a one-person org, and a firm is that same org renamed with members invited into
    it). ``ensure_personal_org`` backstops accounts created before the registration
    hook landed, so this never returns None for a logged-in user.
    """
    user = request.user
    org = tenancy.billing_org(user)
    if org is None:
        org = tenancy.ensure_personal_org(user)
    return org


def _require_manage(request, org: Organization) -> None:
    """Owner/admin, or 403. The server-side half of the SPA's nav gating."""
    if tenancy.role_of(request.user, org) not in MANAGE_ROLES:
        raise HttpError(403, "only an owner or admin can manage billing")


def _require_stripe() -> None:
    if not stripe_api.is_configured():
        raise HttpError(503, "billing not configured")


def _grace_ends_at(sub: Subscription | None) -> dt.datetime | None:
    """``past_due_since`` + the grace window. The SPA renders the deadline from this
    so the window's length lives in one place (settings), not in two."""
    if sub is None or sub.past_due_since is None:
        return None
    days = int(getattr(settings, "BILLING_PAST_DUE_GRACE_DAYS", 7) or 0)
    return sub.past_due_since + dt.timedelta(days=days)


def _trial_days(org: Organization) -> int:
    """Trial length for this checkout: ``STRIPE_TRIAL_DAYS``, first subscription
    per org only.

    "Ever held a Stripe subscription" is the eligibility line — a canceled
    subscription keeps its ``stripe_subscription_id``, so cancel-and-resubscribe
    doesn't mint a fresh trial. A comped/backfilled subscription has no Stripe id
    and does NOT burn the trial: those orgs have never been through Checkout.
    """
    days = int(getattr(settings, "STRIPE_TRIAL_DAYS", 0) or 0)
    if days <= 0:
        return 0
    ever_billed = (
        Subscription.objects.filter(org=org)
        .exclude(stripe_subscription_id=None)
        .exclude(stripe_subscription_id="")
        .exists()
    )
    return 0 if ever_billed else days


def _return_base_url(request) -> str:
    """Base URL Stripe returns the browser to.

    Explicit setting wins. Then ``APP_URL`` if some other module has defined it,
    then the first CORS origin (the SPA's dev origin), then the email link base —
    which is already the app's public URL in prod. Belt and braces, because a
    Checkout session with a broken return URL strands a customer who has just paid.
    """
    for candidate in (
        getattr(settings, "STRIPE_RETURN_BASE_URL", ""),
        getattr(settings, "APP_URL", ""),
        *(getattr(settings, "CORS_ALLOWED_ORIGINS", []) or []),
        getattr(settings, "EMAIL_LINK_BASE_URL", ""),
    ):
        if candidate:
            return str(candidate).rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


# ---------------------------------------------------------------------------
# GET /subscription — DB only, never 503s.
# ---------------------------------------------------------------------------


@billing_router.get("/subscription", response=SubscriptionOut, auth=session_auth)
def get_subscription(request):
    org = _billing_org(request)
    sub = tenancy.flagship_subscription(org)

    return {
        "org": {
            "id": org.pk,
            "name": org.name,
            "is_personal": org.is_personal,
            "status": org.status,
        },
        # What they bought, and what state it is in. Enforcement is a separate
        # question (services.effective_plan) — the SPA renders the state and the
        # grace deadline, and the gates enforce it from User.tier.
        "plan": sub.plan if sub else "free",
        "status": sub.status if sub else "none",
        "seats_used": tenancy.seat_count(org),
        "seats_purchased": sub.seats if sub else 0,
        "current_period_end": sub.current_period_end if sub else None,
        "cancel_at_period_end": bool(sub.cancel_at_period_end) if sub else False,
        "trial_end": sub.trial_end if sub else None,
        "past_due_since": sub.past_due_since if sub else None,
        "grace_ends_at": _grace_ends_at(sub),
        "can_manage": tenancy.role_of(request.user, org) in MANAGE_ROLES,
    }


# ---------------------------------------------------------------------------
# POST /checkout
# ---------------------------------------------------------------------------


@billing_router.post("/checkout", response=UrlOut, auth=session_auth)
def create_checkout(request, payload: CheckoutIn):
    """A Stripe Checkout Session URL for ``plan``. Owner/admin only.

    ``client_reference_id`` AND ``metadata.org_id`` carry the org, and
    ``subscription_data.metadata`` copies both onto the *subscription* — without
    that, ``customer.subscription.*`` events arrive with no way home except the
    customer id. ``metadata.plan`` rides along so a webhook can still name the plan
    if the price ID is one we don't recognise.
    """
    _require_stripe()
    org = _billing_org(request)
    _require_manage(request, org)

    plan = (payload.plan or "").strip().lower()
    if plan not in plans.PURCHASABLE_PLANS:
        raise HttpError(400, f"plan must be one of: {', '.join(plans.PURCHASABLE_PLANS)}")

    # Never sell fewer seats than the org already has members for — the seats they
    # asked for, floored by reality.
    quantity = max(int(payload.seats or 0), tenancy.seat_count(org), 1)

    try:
        line_items = plans.line_items_for(plan, quantity)
    except ValueError as exc:
        # A missing STRIPE_PRICE_* is a deployment gap, not a client error.
        logger.error("checkout refused for org %s: %s", org.pk, exc)
        raise HttpError(503, "billing not configured") from exc

    client = _client()
    customer_id = _ensure_customer(client, org, request.user)

    base = _return_base_url(request)
    metadata = {"org_id": str(org.pk), "plan": plan}
    subscription_data: dict = {"metadata": metadata}
    trial_days = _trial_days(org)
    if trial_days:
        # Card-up-front trial (PRICING_STRATEGY §2): the card is collected at
        # Checkout and the subscription starts as ``trialing`` — the webhook maps
        # that to our ``trial`` status, which grants the plan like ``active``.
        # Stripe emails the pre-charge trial reminder (enable "trial ending"
        # emails in the dashboard) — that's the honest-framing requirement.
        subscription_data["trial_period_days"] = trial_days
    try:
        session = client.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(org.pk),
            line_items=line_items,
            metadata=metadata,
            subscription_data=subscription_data,
            # Explicit: a trial must still collect the card up front — "card
            # required" is the intent-filter half of the trial decision.
            payment_method_collection="always",
            allow_promotion_codes=True,
            success_url=(
                f"{base}{BILLING_PAGE_PATH}?checkout=success"
                "&session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=f"{base}{BILLING_PAGE_PATH}?checkout=canceled",
        )
    except BillingNotConfigured as exc:  # pragma: no cover — guarded above
        raise HttpError(503, "billing not configured") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("stripe checkout session failed for org %s", org.pk)
        raise HttpError(502, "could not start checkout") from exc

    url = session.get("url") if hasattr(session, "get") else getattr(session, "url", None)
    if not url:
        raise HttpError(502, "could not start checkout")
    return {"url": url}


# ---------------------------------------------------------------------------
# POST /portal
# ---------------------------------------------------------------------------


@billing_router.post("/portal", response=UrlOut, auth=session_auth)
def create_portal(request):
    """A Stripe Billing Portal URL — card updates, invoices, cancellation.

    Cancellation happens *there*, not here: the portal fires
    ``customer.subscription.updated/deleted`` and the webhook is what changes our
    state. There is deliberately no cancel endpoint in this API.
    """
    _require_stripe()
    org = _billing_org(request)
    _require_manage(request, org)

    if not org.stripe_customer_id:
        raise HttpError(400, "this organization has no billing account yet")

    client = _client()
    base = _return_base_url(request)
    try:
        session = client.billing_portal.Session.create(
            customer=org.stripe_customer_id,
            return_url=f"{base}{BILLING_PAGE_PATH}",
        )
    except BillingNotConfigured as exc:  # pragma: no cover — guarded above
        raise HttpError(503, "billing not configured") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("stripe portal session failed for org %s", org.pk)
        raise HttpError(502, "could not open the billing portal") from exc

    url = session.get("url") if hasattr(session, "get") else getattr(session, "url", None)
    if not url:
        raise HttpError(502, "could not open the billing portal")
    return {"url": url}


# ---------------------------------------------------------------------------
# POST /webhook — auth=None, signature-verified.
# ---------------------------------------------------------------------------


@billing_router.post("/webhook", auth=None)
def stripe_webhook(request):
    """Stripe → us. Signature is the authentication; the ledger is the idempotency.

    Returns 200 for everything it manages to verify — including events it does not
    handle — because a non-2xx makes Stripe retry, and retrying an event we ignore
    on purpose just burns the endpoint's error budget. A *bug* in a handler raises,
    becomes a 500, and earns the redelivery it deserves.
    """
    secret = stripe_api.webhook_secret()
    if not stripe_api.is_configured() or not secret:
        raise HttpError(503, "billing not configured")

    payload: bytes = request.body
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    if not signature:
        raise HttpError(400, "missing Stripe-Signature header")

    client = _client()
    try:
        # Verification only — we hand the handlers the parsed raw body, so nothing
        # downstream depends on Stripe's object types (and the ledger stores plain
        # JSON). Anything that fails here never reaches a handler.
        client.Webhook.construct_event(payload, signature, secret)
        event = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HttpError(400, "invalid payload") from exc
    except ValueError as exc:  # malformed payload, per stripe's own contract
        raise HttpError(400, "invalid payload") from exc
    except Exception as exc:  # noqa: BLE001 — stripe.SignatureVerificationError
        if type(exc).__name__ == "SignatureVerificationError":
            logger.warning("rejected Stripe webhook with a bad signature")
            raise HttpError(400, "invalid signature") from exc
        raise

    result = webhooks.handle_event(event)
    return {"received": True, "result": result}


# ---------------------------------------------------------------------------
# Stripe plumbing
# ---------------------------------------------------------------------------


def _client():
    try:
        return stripe_api.get_stripe()
    except BillingNotConfigured as exc:
        raise HttpError(503, "billing not configured") from exc


def _ensure_customer(client, org: Organization, user) -> str:
    """The org's Stripe customer id, creating the customer on first checkout.

    ``metadata.org_id`` on the customer means even an event that carries nothing
    else of ours (a bare invoice) can be walked back to the org.
    """
    if org.stripe_customer_id:
        return org.stripe_customer_id

    try:
        customer = client.Customer.create(
            email=getattr(user, "email", "") or None,
            name=org.name,
            metadata={"org_id": str(org.pk)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("stripe customer creation failed for org %s", org.pk)
        raise HttpError(502, "could not create a billing account") from exc

    customer_id = (
        customer.get("id") if hasattr(customer, "get") else getattr(customer, "id", None)
    )
    if not customer_id:
        raise HttpError(502, "could not create a billing account")

    Organization.objects.filter(pk=org.pk).update(stripe_customer_id=customer_id)
    org.stripe_customer_id = customer_id
    return customer_id
