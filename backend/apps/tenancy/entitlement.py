"""Entitlement — does a user have access to a given :class:`Product`?

Access is a UNION of three independent grants, one per go-to-market motion:

  1. **Individual subscription** — the user bought this product directly.
  2. **Org subscription** — the user is a member of an organization (e.g. a bar
     association) that licensed it; every member inherits access.
  3. **Full-corpus superset** — a paid full-product subscriber gets the scoped
     apps for free, because the scoped corpus is a subset of theirs.

Belonging to several orgs is a non-issue: the check is one existence query across
all of them, so there is nothing to "pick". This is the single gate the scoped,
host-pinned apps (e.g. ``clerk.<domain>``) enforce server-side. The unlocked
flagship app keeps its existing behaviour for now (no new gate).
"""

from __future__ import annotations

from django.db.models import Q

from apps.accounts.models import Tier

from .models import OrgMembership, Subscription

# Full-corpus tiers. A paid full-product subscriber is entitled to every scoped
# app (superset); FREE is not. When billing moves onto Subscription (Phase 2),
# replace this with "has an active full-corpus subscription".
FULL_CORPUS_TIERS = frozenset({Tier.SOLO, Tier.FIRM, Tier.CUSTOM})


def is_entitled(user, product) -> bool:
    """True if ``user`` may access ``product``. See module docstring for the rules."""
    if product is None or user is None or not user.is_authenticated:
        return False

    # (3) full-corpus subscriber → every scoped app.
    if user.tier in FULL_CORPUS_TIERS:
        return True

    # (1) + (2) an active subscription to THIS product, held by the user directly
    # or by any org they belong to.
    org_ids = list(
        OrgMembership.objects.filter(user=user).values_list("org_id", flat=True)
    )
    return (
        Subscription.objects.filter(
            product=product, status=Subscription.Status.ACTIVE
        )
        .filter(Q(user=user) | Q(org_id__in=org_ids))
        .exists()
    )
