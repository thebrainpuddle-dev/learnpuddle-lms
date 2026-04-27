"""
Unit tests for apps.integrations_common.crypto

These tests verify the HKDF-SHA256 key derivation and Fernet
encryption/decryption contract that TASK-054 will also rely on.
"""

from django.test import TestCase

from apps.integrations_common.crypto import (
    _derive_fernet_key,
    _hkdf_sha256,
    decrypt_secret,
    encrypt_secret,
    mask_secret,
)


class TestHKDF(TestCase):
    def test_hkdf_returns_32_bytes(self):
        result = _hkdf_sha256(b"input-key-material", length=32)
        self.assertEqual(len(result), 32)

    def test_hkdf_is_deterministic(self):
        r1 = _hkdf_sha256(b"same-ikm", length=32)
        r2 = _hkdf_sha256(b"same-ikm", length=32)
        self.assertEqual(r1, r2)

    def test_hkdf_different_ikm_different_output(self):
        r1 = _hkdf_sha256(b"ikm-alpha", length=32)
        r2 = _hkdf_sha256(b"ikm-beta", length=32)
        self.assertNotEqual(r1, r2)


class TestFernetKey(TestCase):
    def test_derived_key_is_44_bytes_base64(self):
        """URL-safe base64 of 32 bytes is always 44 chars."""
        key = _derive_fernet_key()
        self.assertEqual(len(key), 44)

    def test_derived_key_is_stable(self):
        """Same SECRET_KEY → same derived Fernet key."""
        k1 = _derive_fernet_key()
        k2 = _derive_fernet_key()
        self.assertEqual(k1, k2)


class TestEncryptDecrypt(TestCase):
    def test_roundtrip(self):
        plaintext = "https://hooks.slack.com/services/T999/B888/supersecrettoken"
        ct = encrypt_secret(plaintext)
        self.assertNotEqual(ct, plaintext)
        self.assertEqual(decrypt_secret(ct), plaintext)

    def test_empty_input(self):
        self.assertEqual(encrypt_secret(""), "")
        self.assertEqual(decrypt_secret(""), "")

    def test_ciphertext_non_empty(self):
        ct = encrypt_secret("some secret value")
        self.assertTrue(len(ct) > 20)

    def test_different_ciphertext_per_call(self):
        """Fernet randomises IV — repeat encryption differs."""
        ct1 = encrypt_secret("abc")
        ct2 = encrypt_secret("abc")
        self.assertNotEqual(ct1, ct2)

    def test_invalid_ciphertext_returns_empty(self):
        self.assertEqual(decrypt_secret("not-valid-ciphertext"), "")


class TestMaskSecret(TestCase):
    def test_last_4_visible(self):
        result = mask_secret("https://hooks.slack.com/services/TABCD/BXYZ/mysecret12345678")
        self.assertTrue(result.endswith("5678"))
        self.assertNotIn("hooks.slack.com", result)

    def test_short_string_returned_as_is(self):
        self.assertEqual(mask_secret("abc", visible=4), "abc")

    def test_empty_string(self):
        self.assertEqual(mask_secret(""), "")

    def test_exactly_4_chars(self):
        self.assertEqual(mask_secret("abcd", visible=4), "abcd")

    def test_5_chars(self):
        result = mask_secret("abcde", visible=4)
        self.assertTrue(result.endswith("bcde"))
