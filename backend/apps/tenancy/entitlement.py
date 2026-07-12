"""Entitlement — does a user have access to a given :class:`Product`?

Access is a UNION of two independent grants, one per go-to-market motion:

  1. **Org subscription** — the user belongs to an organization that licensed this
     product. That org may be a bar association (a site license) or their own
     personal org (a solo purchase — billing always attaches to an org, so an
     "individual subscription" is just a subscription held by a personal org).
  2. **Full-corpus superset** — a subscriber on a paid full-corpus PLAN gets the
     scoped apps for free, because the scoped corpus is a subset of theirs.

Grant (2) is now decided by :func:`apps.tenancy.services.effective_plan`, not by the
raw ``user.tier`` column: that is what makes ``canceled`` / ``unpaid`` / ``suspended``
/ expired-grace ``past_due`` actually revoke access (``user.tier`` is only a derived
cache of the same function, kept in step by the webhooks + membership mutations).

Belonging to several orgs is a non-issue: the check is one existence query across
all of them, so there is nothing to "pick". This is the single gate the scoped,
host-pinned apps (e.g. ``clerk.<domain>``) enforce server-side. The unlocked
flagship app keeps its existing behaviour for now (no new gate).
"""

from __future__ import annotations

from apps.accounts.models import Tier

from .models import Organization, OrgMembership, Subscription
from .services import effective_plan

# Full-corpus plans. A paid full-product subscriber is entitled to every scoped
# app (superset); FREE is not.
FULL_CORPUS_PLANS = frozenset({Tier.SOLO, Tier.FIRM, Tier.CUSTOM})

# Kept as an alias: the old name is referenced from docs/notes and reads the same
# vocabulary (Tier == plan choices).
FULL_CORPUS_TIERS = FULL_CORPUS_PLANS


def is_entitled(user, product) -> bool:
    """True if ``user`` may access ``product``. See module docstring for the rules."""
    if product is None or user is None or not user.is_authenticated:
        return False

    # (2) full-corpus plan → every scoped app.
    if effective_plan(user) in FULL_CORPUS_PLANS:
        return True

    # (1) an ACTIVE subscription to THIS product held by any org the user belongs
    # to — and the org must not be suspended/canceled (the kill-switch bites here
    # too, not just on the plan path).
    org_ids = list(
        OrgMembership.objects.filter(user=user).values_list("org_id", flat=True)
    )
    return Subscription.objects.filter(
        product=product,
        status=Subscription.Status.ACTIVE,
        org_id__in=org_ids,
        org__status__in=tuple(Organization.LIVE_STATUSES),
    ).exists()
