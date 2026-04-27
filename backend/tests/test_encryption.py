# tests/test_encryption.py
"""
Tests for utils/encryption.py — Fernet/PBKDF2 symmetric encryption.

Security properties verified:
1. Roundtrip correctness: decrypt(encrypt(x)) == x
2. Ciphertext differs from plaintext (not stored in plain)
3. Ciphertext randomness: two encryptions of the same value differ
4. Empty/falsy inputs handled gracefully (no exceptions)
5. Invalid/corrupted ciphertexts return '' (graceful degradation, no exceptions)
6. Key derivation is deterministic (same SECRET_KEY → same key → same decryptability)
7. No plaintext leakage in ciphertext
"""

import pytest
from django.test import TestCase, override_settings


# ===========================================================================
# 1. Basic Roundtrip Tests
# ===========================================================================


class EncryptionRoundtripTestCase(TestCase):
    """Fundamental correctness: encrypt then decrypt returns original value."""

    def test_roundtrip_api_key(self):
        """Standard API key value survives encrypt/decrypt roundtrip."""
        from utils.encryption import encrypt_value, decrypt_value

        original = "sk-abc123XYZ-very-long-api-key-value"
        ciphertext = encrypt_value(original)
        recovered = decrypt_value(ciphertext)

        self.assertEqual(
            recovered,
            original,
            "decrypt(encrypt(plaintext)) must equal plaintext",
        )

    def test_roundtrip_short_value(self):
        """Short values (e.g. short tokens) also survive roundtrip."""
        from utils.encryption import encrypt_value, decrypt_value

        original = "abc"
        self.assertEqual(decrypt_value(encrypt_value(original)), original)

    def test_roundtrip_long_value(self):
        """Long values (e.g. OAuth2 tokens, API keys) also survive roundtrip."""
        from utils.encryption import encrypt_value, decrypt_value

        original = "a" * 2048
        self.assertEqual(decrypt_value(encrypt_value(original)), original)

    def test_roundtrip_unicode(self):
        """Unicode strings survive roundtrip without corruption."""
        from utils.encryption import encrypt_value, decrypt_value

        original = "school_admin_token_こんにちは_🔑"
        self.assertEqual(decrypt_value(encrypt_value(original)), original)

    def test_roundtrip_special_characters(self):
        """Values containing special characters (=, +, /, newlines) survive."""
        from utils.encryption import encrypt_value, decrypt_value

        original = "tok=en+with/special==chars\nnewline"
        self.assertEqual(decrypt_value(encrypt_value(original)), original)


# ===========================================================================
# 2. Empty / Falsy Input Handling
# ===========================================================================


class EncryptionEmptyInputTestCase(TestCase):
    """Empty or falsy inputs must not raise and must return empty string."""

    def test_encrypt_empty_string_returns_empty(self):
        """encrypt_value('') must return '' (no ciphertext for empty input)."""
        from utils.encryption import encrypt_value

        result = encrypt_value("")
        self.assertEqual(
            result,
            "",
            "encrypt_value('') must return '' to avoid storing empty-string ciphertext",
        )

    def test_decrypt_empty_string_returns_empty(self):
        """decrypt_value('') must return '' (nothing to decrypt)."""
        from utils.encryption import decrypt_value

        result = decrypt_value("")
        self.assertEqual(
            result,
            "",
            "decrypt_value('') must return '' gracefully",
        )


# ===========================================================================
# 3. Ciphertext Security Properties
# ===========================================================================


class CiphertextSecurityTestCase(TestCase):
    """Verify ciphertext is not trivially reconstructible from plaintext."""

    def test_ciphertext_differs_from_plaintext(self):
        """The encrypted value must not equal the original plaintext."""
        from utils.encryption import encrypt_value

        plaintext = "my-secret-api-key"
        ciphertext = encrypt_value(plaintext)

        self.assertNotEqual(
            ciphertext,
            plaintext,
            "Ciphertext must not equal plaintext — indicates encryption is not applied",
        )

    def test_ciphertext_does_not_contain_plaintext(self):
        """The raw ciphertext string must not contain the original plaintext value."""
        from utils.encryption import encrypt_value

        plaintext = "supersecretkey123"
        ciphertext = encrypt_value(plaintext)

        self.assertNotIn(
            plaintext,
            ciphertext,
            "Ciphertext must not embed plaintext as a substring",
        )

    def test_two_encryptions_of_same_value_differ(self):
        """
        Fernet uses a random IV per encryption — encrypting the same value
        twice must produce different ciphertexts (probabilistic encryption).
        """
        from utils.encryption import encrypt_value

        value = "deterministic-test-api-key"
        cipher1 = encrypt_value(value)
        cipher2 = encrypt_value(value)

        self.assertNotEqual(
            cipher1,
            cipher2,
            "Two encryptions of the same plaintext must produce different ciphertexts "
            "(Fernet uses random IV per encryption — deterministic output indicates a bug)",
        )

    def test_ciphertext_is_non_empty_for_non_empty_input(self):
        """Non-empty input must produce a non-empty ciphertext."""
        from utils.encryption import encrypt_value

        ciphertext = encrypt_value("any-non-empty-value")
        self.assertGreater(len(ciphertext), 0, "Non-empty input must produce non-empty ciphertext")

    def test_ciphertext_is_url_safe_base64(self):
        """
        Fernet ciphertexts are URL-safe base64-encoded.
        They must not contain characters that break JSON/URL storage.
        """
        from utils.encryption import encrypt_value
        import re

        ciphertext = encrypt_value("test-value-for-url-safety")
        # URL-safe base64 uses [A-Za-z0-9_-] and = padding
        # The ciphertext must only contain these characters
        self.assertRegex(
            ciphertext,
            r'^[A-Za-z0-9_\-=]+$',
            "Ciphertext must be URL-safe base64 (no +, /, special chars)",
        )


# ===========================================================================
# 4. Invalid / Corrupted Ciphertext Handling
# ===========================================================================


class InvalidCiphertextTestCase(TestCase):
    """Corrupted or invalid ciphertexts must be handled gracefully."""

    def test_corrupted_ciphertext_returns_empty_string(self):
        """
        decrypt_value() with a corrupted ciphertext must return '' without raising.
        This prevents DoS via crafted inputs.
        """
        from utils.encryption import decrypt_value

        result = decrypt_value("this-is-not-a-valid-fernet-token")
        self.assertEqual(
            result,
            "",
            "Corrupted ciphertext must return '' (graceful degradation, not exception)",
        )

    def test_random_bytes_as_ciphertext_returns_empty(self):
        """Random binary-like string must be handled gracefully."""
        from utils.encryption import decrypt_value

        result = decrypt_value("aGVsbG8gd29ybGQ=")  # base64("hello world") — not Fernet
        self.assertEqual(result, "")

    def test_truncated_ciphertext_returns_empty(self):
        """Truncating a valid ciphertext makes it invalid — must return ''."""
        from utils.encryption import encrypt_value, decrypt_value

        ciphertext = encrypt_value("some-value")
        truncated = ciphertext[: len(ciphertext) // 2]
        result = decrypt_value(truncated)
        self.assertEqual(
            result,
            "",
            "Truncated ciphertext must return '' without raising",
        )

    def test_wrong_secret_key_cannot_decrypt(self):
        """
        A value encrypted under SECRET_KEY A cannot be decrypted under SECRET_KEY B.
        Simulates SECRET_KEY rotation risk.
        """
        from utils.encryption import encrypt_value, decrypt_value

        # Encrypt under current SECRET_KEY
        ciphertext = encrypt_value("sensitive-tenant-api-key")

        # Override SECRET_KEY to simulate rotation
        with override_settings(SECRET_KEY="completely-different-secret-key-xyz"):
            result = decrypt_value(ciphertext)

        self.assertEqual(
            result,
            "",
            "Decrypting under a different SECRET_KEY must return '' "
            "(not an exception, and not the original plaintext)",
        )


# ===========================================================================
# 5. Key Derivation Consistency
# ===========================================================================


class KeyDerivationTestCase(TestCase):
    """Key derivation must be deterministic for the same SECRET_KEY."""

    def test_same_key_can_encrypt_and_decrypt_across_calls(self):
        """
        Multiple calls with the same SECRET_KEY must work together:
        encrypt in one call, decrypt in another — same logical key.
        """
        from utils.encryption import encrypt_value, decrypt_value

        plaintext = "cross-call-consistency-test"
        # These two calls simulate two separate requests / code paths
        ciphertext = encrypt_value(plaintext)
        recovered = decrypt_value(ciphertext)

        self.assertEqual(recovered, plaintext)

    def test_different_secret_keys_produce_independent_ciphertexts(self):
        """
        Ciphertexts from different SECRET_KEY values must not be cross-decryptable.
        Verifies that the key derivation is keyed correctly.
        """
        from utils.encryption import encrypt_value, decrypt_value

        plaintext = "key-isolation-test"

        with override_settings(SECRET_KEY="first-secret-key-111"):
            ct_a = encrypt_value(plaintext)

        with override_settings(SECRET_KEY="second-secret-key-222"):
            ct_b = encrypt_value(plaintext)

        # ct_a must not decrypt under key B
        with override_settings(SECRET_KEY="second-secret-key-222"):
            result = decrypt_value(ct_a)
        self.assertEqual(result, "", "ct_a should not decrypt under key B")

        # ct_b must not decrypt under key A
        with override_settings(SECRET_KEY="first-secret-key-111"):
            result = decrypt_value(ct_b)
        self.assertEqual(result, "", "ct_b should not decrypt under key A")
