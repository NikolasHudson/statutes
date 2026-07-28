"""The crowdsource bucket: write-only object storage for opted-in filings.

This is the *only* place in the platform where a document a user gave us is
persisted, and everything about it is shaped by that:

* **Streaming, never buffered.** The request body goes to the bucket a chunk at
  a time. The container filesystem is ephemeral and small; the prototype's
  design (multipart upload → local ``FileField`` → worker) would have written
  client documents to a disk that survives nothing and is shared with the web
  process. Bytes here touch memory in 64 KB slices and nothing else.
* **Write-only by construction.** There is a put and a delete. There is no get,
  no list-for-display, no presign — because the product rule is that the bucket
  is inert until redaction and a contribution policy exist. Adding a read path
  is a product decision, not a refactor.
* **Metered.** The reader counts bytes and hashes as it goes, so the index row
  records a real size and digest without a second pass, and a client that lies
  about ``Content-Length`` still hits the cap.

boto3 is imported lazily, matching how ``apps/billing`` treats stripe: a deploy
without the dependency (or without ``SPACES_*`` configured) still boots and
still serves every other EDMSpro route — the contribute endpoint answers 503.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024
# Matches the Verify Document upload ceiling. A court filing that exceeds this
# is an exhibit dump, not a motion.
MAX_UPLOAD_BYTES = 40 * 1024 * 1024


class StorageNotConfigured(RuntimeError):
    """No bucket configured (or boto3 absent) — the intake path answers 503."""


class PayloadTooLarge(ValueError):
    """The stream exceeded :data:`MAX_UPLOAD_BYTES` mid-upload."""


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    key: str
    byte_size: int
    sha256: str


def is_configured() -> bool:
    return bool(
        settings.SPACES_BUCKET
        and settings.SPACES_KEY
        and settings.SPACES_SECRET
        and settings.SPACES_REGION
    )


def _client():
    if not is_configured():
        raise StorageNotConfigured("SPACES_* settings are not configured.")
    try:
        import boto3  # noqa: PLC0415 — lazy by design, see module docstring
    except ImportError as exc:  # pragma: no cover - dependency present in prod
        raise StorageNotConfigured("boto3 is not installed.") from exc
    return boto3.client(
        "s3",
        endpoint_url=settings.SPACES_ENDPOINT
        or f"https://{settings.SPACES_REGION}.digitaloceanspaces.com",
        region_name=settings.SPACES_REGION,
        aws_access_key_id=settings.SPACES_KEY,
        aws_secret_access_key=settings.SPACES_SECRET,
    )


class MeteredReader:
    """File-like wrapper that counts, hashes, and caps as bytes flow through.

    Deliberately not seekable: it wraps a live request body, and pretending
    otherwise would let a transfer library try to rewind a socket."""

    def __init__(self, stream, *, max_bytes: int | None = None):
        self._stream = stream
        # Resolved at call time, not bound as a default: the cap is a module
        # constant tests override, and a default argument would freeze it at
        # import.
        self._max = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
        self._digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(CHUNK_SIZE if size is None or size < 0 else size)
        if not chunk:
            return b""
        self.bytes_read += len(chunk)
        if self.bytes_read > self._max:
            raise PayloadTooLarge(
                f"upload exceeds the {self._max // (1024 * 1024)}MB limit"
            )
        self._digest.update(chunk)
        return chunk

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()


def object_key(user_id: int) -> str:
    """An opaque key. Nothing about the case is encoded in the path: the index
    row carries the metadata, and a bucket listing should not read as a client
    matter list to anyone who ever gets a listing."""
    return f"contributions/{user_id}/{uuid.uuid4().hex}.pdf"


def stream_to_bucket(stream, *, key: str, content_type: str = "application/pdf") -> StoredObject:
    """Stream ``stream`` into the private bucket under ``key``.

    Raises :class:`StorageNotConfigured` (→ 503) or :class:`PayloadTooLarge`
    (→ 413). On the latter the partial object is best-effort deleted, so a
    rejected upload does not leave a truncated PDF behind."""
    client = _client()
    bucket = settings.SPACES_BUCKET
    reader = MeteredReader(stream)
    try:
        client.upload_fileobj(
            reader,
            bucket,
            key,
            ExtraArgs={"ContentType": content_type, "ACL": "private"},
        )
    except PayloadTooLarge:
        _best_effort_delete(client, bucket, [key])
        raise
    return StoredObject(
        bucket=bucket, key=key, byte_size=reader.bytes_read, sha256=reader.sha256
    )


def delete_objects(keys: list[str]) -> int:
    """Delete objects by key. Returns how many were requested; raises if the
    bucket is unreachable, because a purge that silently no-ops is worse than a
    purge that fails loudly."""
    if not keys:
        return 0
    client = _client()
    bucket = settings.SPACES_BUCKET
    # S3 DeleteObjects caps at 1000 keys per call.
    for start in range(0, len(keys), 1000):
        batch = keys[start:start + 1000]
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
        )
    return len(keys)


def _best_effort_delete(client, bucket: str, keys: list[str]) -> None:
    try:
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True},
        )
    except Exception:  # noqa: BLE001 — cleanup must not mask the real error
        logger.warning("edms: could not clean up partial upload %s", keys)
