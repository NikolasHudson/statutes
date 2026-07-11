import hashlib
import secrets

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager

# The append-only security audit model is defined in audit.py for readability;
# re-export it here so Django's app registry and makemigrations discover it as
# part of the accounts app.
from .audit import AuditEvent  # noqa: E402,F401

# Likewise the per-user profile / preferences model lives in profile.py.
from .profile import UserProfile  # noqa: E402,F401


class Tier(models.TextChoices):
    FREE = "free", "Free"
    SOLO = "solo", "Solo"
    FIRM = "firm", "Firm"
    CUSTOM = "custom", "Custom"


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    # Structured name is the source of truth; ``full_name`` is derived from it
    # (kept as a stored column so existing queries / admin / audit are unchanged).
    # Use ``set_name()`` to write any of the three and keep them consistent.
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    full_name = models.CharField(max_length=200, blank=True)
    tier = models.CharField(max_length=16, choices=Tier.choices, default=Tier.FREE)

    # Per-user override of the tier's monthly LLM spend budget (USD). Null =
    # use the tier default in apps.api.usage.TIER_BUDGETS_USD. Set via Django
    # admin when a customer needs a higher (or tighter) cap; staff accounts
    # are exempt from per-user budgets regardless of this value.
    monthly_budget_usd = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ("email",)

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name or self.email

    def get_short_name(self):
        if self.first_name:
            return self.first_name
        return self.full_name.split()[0] if self.full_name else self.email

    def set_name(self, *, first=None, last=None, full=None):
        """Keep ``first_name`` / ``last_name`` / ``full_name`` consistent.

        Pass structured ``first`` / ``last`` (from the settings form) and
        ``full_name`` is recomputed; or pass a single ``full`` (legacy callers)
        and it is split best-effort into first/last. Does not save — returns the
        list of fields it touched so the caller can pass ``update_fields``.
        """
        if first is not None or last is not None:
            if first is not None:
                self.first_name = first.strip()
            if last is not None:
                self.last_name = last.strip()
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        elif full is not None:
            self.full_name = full.strip()
            parts = self.full_name.split()
            self.first_name = parts[0] if parts else ""
            self.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        return ["first_name", "last_name", "full_name"]


def generate_key():
    """Return (raw_key, prefix, hashed_key). The raw key is shown to the user
    once at creation time and never persisted."""
    raw = secrets.token_urlsafe(32)
    prefix = raw[:8]
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, hashed


def verify_key(raw_key):
    """Look up an APIKey by its prefix and verify the SHA-256 hash. Returns
    the APIKey if valid and not revoked, otherwise None."""
    if not raw_key or len(raw_key) < 8:
        return None
    prefix = raw_key[:8]
    hashed = hashlib.sha256(raw_key.encode()).hexdigest()
    # user__is_active: deactivating an account must be a full kill-switch —
    # sessions already die via ModelBackend.get_user, and this keeps a still-
    # valid API key from surviving the deactivation.
    return APIKey.objects.filter(
        prefix=prefix,
        hashed_key=hashed,
        revoked_at__isnull=True,
        user__is_active=True,
    ).select_related("user").first()


class APIKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=8, unique=True, db_index=True)
    hashed_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} ({self.user.email})"

    @property
    def is_active(self):
        return self.revoked_at is None
