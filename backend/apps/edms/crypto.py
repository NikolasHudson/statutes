"""Symmetric encryption for the cloud-provider tokens EDMSpro stores.

A user's OneDrive refresh token is the most sensitive row this platform holds:
it is standing, offline access to that attorney's document store. It is
therefore encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256, from
``cryptography``, already a transitive dependency) rather than stored as plain
text in a column any DB dump would carry.

Key resolution, in order:

1. ``EDMS_CRYPTO_KEY`` — a urlsafe-base64 32-byte Fernet key. This is the
   intended production setting; generate one with
   ``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``.
2. Derived from ``SECRET_KEY`` when (1) is unset, so dev boxes, CI and the test
   suite work with no extra configuration.

The fallback is deliberate but not free: rotating ``SECRET_KEY`` makes every
stored token undecryptable. That degrades to "every user must reconnect
OneDrive" — noisy, never silent (:func:`decrypt_secret` returns ``""``, which
the integration layer surfaces as *needs reconnect*), and never a data leak.
Set ``EDMS_CRYPTO_KEY`` in production so the two secrets rotate independently.

What this module is NOT: a substitute for keeping the ciphertext out of API
responses. No serializer anywhere in ``apps/edms`` emits a token field, encrypted
or not — that rule is asserted by test.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    configured = (getattr(settings, "EDMS_CRYPTO_KEY", "") or "").strip()
    if configured:
        return Fernet(configured.encode())
    # Derived fallback — see module docstring. sha256 of SECRET_KEY gives the
    # exact 32 bytes Fernet wants; the domain-separation prefix keeps this key
    # from colliding with any other SECRET_KEY-derived material.
    digest = hashlib.sha256(f"edms-token-encryption:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def reset_key_cache() -> None:
    """Drop the memoized key. Tests use this after overriding settings."""
    _fernet.cache_clear()


def encrypt_secret(raw: str) -> str:
    """Ciphertext for ``raw``, or ``""`` for an empty input (never encrypt
    nothing — an empty column reads unambiguously as "no token stored")."""
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_secret(blob: str) -> str:
    """Plaintext for ``blob``.

    Returns ``""`` — not an exception — when the ciphertext cannot be opened
    (key rotated, row copied between environments, corruption). Callers treat a
    missing token as "not connected", which is exactly the right recovery: the
    user reconnects. Raising here would instead turn a rotated key into 500s on
    every EDMSpro page."""
    if not blob:
        return ""
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except (InvalidToken, ValueError):
        logger.warning("edms: stored token could not be decrypted (key rotated?)")
        return ""
