import hashlib
import secrets

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class Tier(models.TextChoices):
    FREE = "free", "Free"
    SOLO = "solo", "Solo"
    FIRM = "firm", "Firm"
    CUSTOM = "custom", "Custom"


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    tier = models.CharField(max_length=16, choices=Tier.choices, default=Tier.FREE)

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
        return self.full_name.split()[0] if self.full_name else self.email


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
    return APIKey.objects.filter(
        prefix=prefix, hashed_key=hashed, revoked_at__isnull=True
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
