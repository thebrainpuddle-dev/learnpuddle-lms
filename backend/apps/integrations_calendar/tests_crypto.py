"""
Tests for apps.integrations_calendar.crypto — domain-separated token
encryption wrappers around integrations_common.crypto.

Covers:
 - encrypt/decrypt round-trip
 - empty-string handling
 - domain-prefix isolation from webhook-URL ciphertexts (TASK-055 reuse)
 - tampered ciphertext returns empty
"""

from __future__ import annotations

from django.test import TestCase

from apps.integrations_calendar.crypto import (
    decrypt_calendar_token,
    encrypt_calendar_token,
    _CAL_PREFIX,
)
from apps.integrations_common.crypto import decrypt_secret, encrypt_secret


class TestCalendarCryptoRoundtrip(TestCase):
    def test_roundtrip_preserves_plaintext(self):
        plaintext = "ya29.a0AfH6SMBexample-access-token-value"
        ct = encrypt_calendar_token(plaintext)
        self.assertNotEqual(ct, plaintext)
        self.assertEqual(decrypt_calendar_token(ct), plaintext)

    def test_empty_string_roundtrip(self):
        self.assertEqual(encrypt_calendar_token(""), "")
        self.assertEqual(decrypt_calendar_token(""), "")

    def test_different_calls_produce_different_ciphertext(self):
        """Fernet IV-randomised; same plaintext → distinct ciphertexts."""
        ct1 = encrypt_calendar_token("same-token")
        ct2 = encrypt_calendar_token("same-token")
        self.assertNotEqual(ct1, ct2)
        self.assertEqual(decrypt_calendar_token(ct1), decrypt_calendar_token(ct2))


class TestCalendarCryptoDomainSeparation(TestCase):
    """
    Calendar tokens must be structurally distinct from webhook-URL
    ciphertexts so a chat integration ciphertext cannot be successfully
    decrypted as a calendar token (even if the DB is compromised).
    """

    def test_calendar_token_stored_with_prefix_under_the_hood(self):
        """
        Encrypt a calendar token, then decrypt it with the shared helper.
        The raw plaintext seen by the shared Fernet layer must carry the
        "cal:" sentinel (domain-separation prefix).
        """
        plaintext = "refresh-token-xyz"
        ct = encrypt_calendar_token(plaintext)
        raw = decrypt_secret(ct)
        self.assertTrue(raw.startswith(_CAL_PREFIX))
        self.assertEqual(raw[len(_CAL_PREFIX):], plaintext)

    def test_chat_ciphertext_decrypts_to_empty_as_calendar_token(self):
        """
        A chat-webhook ciphertext (no "cal:" prefix) must not decrypt as
        a calendar token — decrypt_calendar_token must return empty.
        """
        webhook_ct = encrypt_secret("https://hooks.slack.com/services/T/B/xxxx")
        # Now try to read it as if it were a calendar token.
        self.assertEqual(decrypt_calendar_token(webhook_ct), "")


class TestCalendarCryptoTampering(TestCase):
    def test_tampered_ciphertext_returns_empty(self):
        ct = encrypt_calendar_token("secret-access-token")
        tampered = ct[:-5] + "XXXXX"
        self.assertEqual(decrypt_calendar_token(tampered), "")

    def test_invalid_ciphertext_returns_empty(self):
        self.assertEqual(decrypt_calendar_token("garbage-not-base64"), "")
