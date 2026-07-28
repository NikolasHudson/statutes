"""Token encryption at rest.

The stored refresh token is standing, offline access to an attorney's document
store — the most sensitive row the platform holds. Two properties matter: it is
not readable from the column, and a key that no longer opens it degrades to
"reconnect", never to a 500 and never to a silent plaintext fallback.
"""

from __future__ import annotations

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings

from apps.edms import crypto
from apps.edms.models import CloudIntegration, Provider

from ._factories import make_user


class CryptoTests(TestCase):
    def setUp(self):
        crypto.reset_key_cache()
        self.addCleanup(crypto.reset_key_cache)

    def test_round_trip(self):
        blob = crypto.encrypt_secret("s3cret-refresh-token")
        self.assertNotIn("s3cret", blob)
        self.assertEqual(crypto.decrypt_secret(blob), "s3cret-refresh-token")

    def test_empty_stays_empty(self):
        self.assertEqual(crypto.encrypt_secret(""), "")
        self.assertEqual(crypto.decrypt_secret(""), "")

    def test_explicit_key_is_preferred(self):
        with override_settings(EDMS_CRYPTO_KEY=Fernet.generate_key().decode()):
            crypto.reset_key_cache()
            blob = crypto.encrypt_secret("abc")
            self.assertEqual(crypto.decrypt_secret(blob), "abc")

    def test_unopenable_ciphertext_reads_as_missing_not_as_an_error(self):
        with override_settings(EDMS_CRYPTO_KEY=Fernet.generate_key().decode()):
            crypto.reset_key_cache()
            blob = crypto.encrypt_secret("abc")
        with override_settings(EDMS_CRYPTO_KEY=Fernet.generate_key().decode()):
            crypto.reset_key_cache()
            # A rotated key means every user reconnects — noisy, but never a
            # crash and never a leak.
            self.assertEqual(crypto.decrypt_secret(blob), "")


class StoredTokenTests(TestCase):
    def test_column_holds_ciphertext_not_the_token(self):
        user = make_user()
        integration = CloudIntegration(user=user, provider=Provider.ONEDRIVE)
        integration.refresh_token = "plain-refresh"
        integration.save()

        raw_column = CloudIntegration.objects.filter(pk=integration.pk).values_list(
            "refresh_token_enc", flat=True
        )[0]
        self.assertNotIn("plain-refresh", raw_column)
        self.assertEqual(
            CloudIntegration.objects.get(pk=integration.pk).refresh_token,
            "plain-refresh",
        )
