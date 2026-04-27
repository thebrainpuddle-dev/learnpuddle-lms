"""
Tests for ``apps.semantic_search.checks`` — TASK-INFRA-001 L3.

Hardens the system-check probe against fail-open regression:

  1. ``test_cursor_raises_returns_check_ok_or_warning`` — verifies that when
     ``connection.cursor()`` raises a generic Exception (e.g. DB unreachable,
     build container without a live DB), the check returns an empty list (no
     crash, fail-open / no-op behaviour as documented).

  2. ``test_extension_missing_surfaces_W001_debug_and_E001_nondebug`` — verifies
     that when the ``pg_extension`` query returns ``None`` (extension not
     installed), the check emits ``semantic_search.W001`` (WARNING) under
     ``DEBUG=True`` and ``semantic_search.E001`` (ERROR) under ``DEBUG=False``.

Both tests mock ``django.db.connection.cursor`` so no real DB is required.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.core import checks
from django.test import TestCase, override_settings

from apps.semantic_search.checks import pgvector_extension_installed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cursor_context(fetchone_return):
    """
    Return a context-manager mock that yields a cursor whose ``fetchone``
    returns ``fetchone_return``.
    """
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_return
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


# ---------------------------------------------------------------------------
# Test 1: cursor raises → fail-open (no crash, empty list)
# ---------------------------------------------------------------------------


class TestCursorRaisesFailOpen(TestCase):
    """
    When ``connection.cursor()`` raises on __enter__, the check must return []
    (fail-open) rather than propagating the exception.

    This mirrors the documented behaviour in checks.py:
      "any DB access error (e.g. ``makemigrations --no-database``,
       ``collectstatic`` in a build container without a live DB) causes the
       check to no-op."
    """

    def test_cursor_raises_returns_check_ok_or_warning(self):
        broken_cursor = MagicMock()
        broken_cursor.__enter__ = MagicMock(side_effect=Exception("DB unreachable"))
        broken_cursor.__exit__ = MagicMock(return_value=False)

        with patch("django.db.connection.cursor", return_value=broken_cursor):
            result = pgvector_extension_installed(None)

        self.assertEqual(
            result,
            [],
            "check must return [] (no-op) when cursor raises on entry, "
            "not propagate the exception (fail-open behaviour)",
        )


# ---------------------------------------------------------------------------
# Test 2: extension missing → W001 under DEBUG=True, E001 under DEBUG=False
# ---------------------------------------------------------------------------


class TestExtensionMissingSurfacesCorrectCheckLevel(TestCase):
    """
    When the ``SELECT 1 FROM pg_extension WHERE extname='vector'`` query
    returns ``None`` (extension absent), severity must be environment-aware:

    * ``DEBUG=True``  → ``semantic_search.W001`` at ``checks.WARNING`` level
    * ``DEBUG=False`` → ``semantic_search.E001`` at ``checks.ERROR`` level
    """

    def _run_check_with_missing_extension(self):
        """Run the check with a cursor that reports the extension as absent."""
        cursor_ctx = _make_cursor_context(fetchone_return=None)
        with patch("django.db.connection.cursor", return_value=cursor_ctx):
            return pgvector_extension_installed(None)

    @override_settings(DEBUG=True)
    def test_extension_missing_emits_W001_in_debug(self):
        result = self._run_check_with_missing_extension()

        self.assertEqual(len(result), 1, "expected exactly one check message")
        msg = result[0]
        self.assertEqual(
            msg.id,
            "semantic_search.W001",
            f"expected W001, got {msg.id!r}",
        )
        self.assertEqual(
            msg.level,
            checks.WARNING,
            "DEBUG=True must emit a WARNING (not ERROR)",
        )

    @override_settings(DEBUG=False)
    def test_extension_missing_emits_E001_in_nondebug(self):
        result = self._run_check_with_missing_extension()

        self.assertEqual(len(result), 1, "expected exactly one check message")
        msg = result[0]
        self.assertEqual(
            msg.id,
            "semantic_search.E001",
            f"expected E001, got {msg.id!r}",
        )
        self.assertEqual(
            msg.level,
            checks.ERROR,
            "DEBUG=False must emit an ERROR (not WARNING)",
        )
