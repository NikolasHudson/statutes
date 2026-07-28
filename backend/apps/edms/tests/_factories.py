"""Test helpers for EDMSpro: users with each credential shape, a connected
OneDrive, and a fake S3 that behaves like the bucket without touching one."""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.accounts.models import APIKey, Tier, User, generate_key
from apps.edms.models import CloudIntegration, Provider
from apps.oauth_server.models import OAuthClient, OAuthToken


def make_user(email: str = "attorney@example.com", *, tier: str = Tier.SOLO) -> User:
    return User.objects.create_user(email=email, password="x", tier=tier)


def make_api_key(user: User) -> str:
    """Returns the raw key for the ``X-API-Key`` header."""
    raw, prefix, hashed = generate_key()
    APIKey.objects.create(user=user, name="test", prefix=prefix, hashed_key=hashed)
    return raw


def make_bearer(user: User, *, scope: str = "edms") -> str:
    """Returns a raw OAuth access token for ``Authorization: Bearer``."""
    client, _ = OAuthClient.objects.get_or_create(
        client_id="test-extension",
        defaults={
            "client_name": "Test Extension",
            "token_endpoint_auth_method": OAuthClient.AuthMethod.NONE,
            "redirect_uris": ["https://abc.chromiumapp.org/"],
            "grant_types": ["authorization_code", "refresh_token"],
        },
    )
    _, raw_access, _ = OAuthToken.issue(client=client, user=user, scope=scope)
    return raw_access


def connect_onedrive(user: User, *, email: str = "attorney@firm.com") -> CloudIntegration:
    integration = CloudIntegration(
        user=user,
        provider=Provider.ONEDRIVE,
        expires_at=timezone.now() + dt.timedelta(hours=1),
        account_email=email,
        account_name="A Attorney",
    )
    integration.access_token = "access-token"
    integration.refresh_token = "refresh-token"
    integration.save()
    return integration


class FakeS3:
    """Stands in for the boto3 client. Records what would have been stored so a
    test can assert on bytes without a bucket, and honours the streaming
    contract (it *reads* the file object rather than expecting bytes) so the
    metering/cap logic is genuinely exercised."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):  # noqa: N803
        chunks = []
        while True:
            chunk = fileobj.read(64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        self.objects[key] = b"".join(chunks)

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        for item in Delete["Objects"]:
            self.deleted.append(item["Key"])
            self.objects.pop(item["Key"], None)


SPACES_SETTINGS = {
    "SPACES_KEY": "key",
    "SPACES_SECRET": "secret",
    "SPACES_BUCKET": "hudson-edms-contributions",
    "SPACES_REGION": "nyc3",
}
