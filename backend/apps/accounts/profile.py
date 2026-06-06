"""Per-user profile + app preferences — the ``/api/account/settings`` resource.

Split into its own module (re-exported from ``models.py``, the same way
``audit.py`` is) because the choice enums plus the field set are sizable. One
``UserProfile`` row per user — a OneToOne extension of the auth ``User`` — holds
three kinds of data that share a lifecycle (read together on load, written
together by the onboarding wizard / settings page):

  * **contact / professional PII** — phone, mailing address, organization,
    bar number, primary jurisdiction, time zone
  * **app preferences** — theme, default search scope, citation style, the
    verify-citations default, email digests
  * **onboarding / ToS state** — the *current* denormalized values only. The
    immutable acceptance history (which ToS version, when) lives in the
    append-only :class:`apps.accounts.audit.AuditEvent` log, not here.

The structured name (``first_name`` / ``last_name``) deliberately lives on
``User``, not here — it's identity, and ``User.full_name`` is derived from it.

A row is auto-created for every new user by a ``post_save`` signal
(``apps/accounts/signals.py``) and backfilled for pre-existing users by data
migration ``0004``. Choice values are the single source of truth the API
validates against and the frontend mirrors; the human labels match the
onboarding mockup's option lists.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    ATTORNEY = "attorney", "Attorney"
    PARALEGAL = "paralegal", "Paralegal"
    LAW_CLERK = "law_clerk", "Law clerk"
    LAW_STUDENT = "law_student", "Law student"
    RESEARCHER = "researcher", "Legal researcher"
    OTHER = "other", "Other"


class Theme(models.TextChoices):
    LIGHT = "light", "Light"
    DARK = "dark", "Dark"
    SYSTEM = "system", "System"


class SearchScope(models.TextChoices):
    ALL = "all", "Everything"
    CASES = "cases", "Case law only"
    STATUTES = "statutes", "Statutes & codes only"
    SECONDARY = "secondary", "Secondary sources only"


class CitationStyle(models.TextChoices):
    BLUEBOOK = "bluebook", "Bluebook (21st ed.)"
    ALWD = "alwd", "ALWD Guide"
    IOWA = "iowa", "Iowa local rules"


class UserProfile(models.Model):
    """1:1 extension of :class:`apps.accounts.models.User`.

    Uses the user FK as its primary key so there is exactly one row per user
    and no separate surrogate id to keep in sync. Deleting the user cascades
    the profile away (the PII goes with the account); the security audit trail,
    by contrast, is SET_NULL and survives.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        primary_key=True,
    )

    # ---- contact / PII ----------------------------------------------------
    phone = models.CharField(max_length=32, blank=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=64, blank=True)  # state / province
    postal_code = models.CharField(max_length=16, blank=True)
    country = models.CharField(max_length=2, blank=True, default="US")

    # ---- professional -----------------------------------------------------
    organization = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, blank=True)
    bar_number = models.CharField(max_length=64, blank=True)  # free text, optional
    # Jurisdiction is free text for now; it should ultimately be sourced from
    # the corpus, so it is intentionally not constrained to an enum here.
    primary_jurisdiction = models.CharField(max_length=64, blank=True)
    timezone = models.CharField(max_length=64, blank=True, default="America/Chicago")

    # ---- preferences ------------------------------------------------------
    theme = models.CharField(
        max_length=8, choices=Theme.choices, default=Theme.SYSTEM
    )
    default_search_scope = models.CharField(
        max_length=16, choices=SearchScope.choices, default=SearchScope.ALL
    )
    citation_style = models.CharField(
        max_length=16, choices=CitationStyle.choices, default=CitationStyle.BLUEBOOK
    )
    verify_citations = models.BooleanField(default=True)
    weekly_digest = models.BooleanField(default=True)
    product_news = models.BooleanField(default=False)

    # ---- onboarding / legal (current state; history in AuditEvent) --------
    onboarding_completed = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    tos_version = models.CharField(max_length=32, blank=True)
    tos_accepted_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"profile<{self.user_id}>"
