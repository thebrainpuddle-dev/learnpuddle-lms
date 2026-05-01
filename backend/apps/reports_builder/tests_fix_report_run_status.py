"""
Tests for the fix_report_run_status management command.

Covers the data-integrity repair command that updates stale
``ReportRun.status = "failed"`` rows to ``"error"``.

Bug context: tasks.py:execute_scheduled_report previously set
``run.status = "failed"`` on delivery-failure paths.  ``"failed"`` is
NOT in ``ReportRun.STATUS_CHOICES``; ``"error"`` is the correct value.

Run (Docker):
    docker compose exec web pytest \\
        apps/reports_builder/tests_fix_report_run_status.py -v
    Expected: 10 PASS
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.reports_builder.models import ReportDefinition, ReportRun
from apps.tenants.models import Tenant

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tenant(subdomain: str) -> Tenant:
    return Tenant.objects.create(
        name=f"Fix Status Test Tenant {subdomain}",
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.test",
        is_active=True,
    )


def _definition(tenant: Tenant, name: str = "Report A") -> ReportDefinition:
    return ReportDefinition.all_objects.create(
        tenant=tenant,
        name=name,
        data_source="courses",
        filters_json=[],
        group_by_json=[],
        aggregates_json=[],
    )


def _run(tenant: Tenant, definition: ReportDefinition, status: str) -> ReportRun:
    return ReportRun.all_objects.create(
        tenant=tenant,
        definition=definition,
        status=status,
    )


def _call(args: list[str] | None = None) -> tuple[str, str]:
    """Call the command and return (stdout, stderr) as strings."""
    out, err = StringIO(), StringIO()
    call_command("fix_report_run_status", *(args or []), stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFixReportRunStatusCommand(TestCase):
    """Functional tests for the fix_report_run_status management command."""

    def setUp(self):
        self.tenant = _tenant("fixstatus-a")
        self.definition = _definition(self.tenant)

    # ------------------------------------------------------------------
    # Happy path: stale rows exist
    # ------------------------------------------------------------------

    def test_updates_failed_rows_to_error(self):
        """Stale rows with status='failed' are updated to 'error'."""
        run = _run(self.tenant, self.definition, "failed")

        _call()

        run.refresh_from_db()
        self.assertEqual(run.status, "error")

    def test_updates_all_failed_rows_across_tenants(self):
        """All stale rows across all tenants are updated when no tenant filter."""
        tenant_b = _tenant("fixstatus-b")
        def_b = _definition(tenant_b, "Report B")
        run_a = _run(self.tenant, self.definition, "failed")
        run_b = _run(tenant_b, def_b, "failed")

        _call()

        run_a.refresh_from_db()
        run_b.refresh_from_db()
        self.assertEqual(run_a.status, "error")
        self.assertEqual(run_b.status, "error")

    def test_stdout_reports_count_updated(self):
        """Command stdout reports how many rows were updated."""
        _run(self.tenant, self.definition, "failed")
        _run(self.tenant, self.definition, "failed")

        out, _ = _call()

        self.assertIn("2", out, "stdout should mention the count of updated rows")
        self.assertIn("error", out, "stdout should confirm the target status")

    # ------------------------------------------------------------------
    # Clean table: no stale rows
    # ------------------------------------------------------------------

    def test_no_op_when_table_clean(self):
        """No writes occur when there are no 'failed' rows."""
        _run(self.tenant, self.definition, "success")
        _run(self.tenant, self.definition, "error")
        _run(self.tenant, self.definition, "running")

        _call()

        # All rows untouched
        statuses = set(
            ReportRun.all_objects.filter(tenant=self.tenant)
            .values_list("status", flat=True)
        )
        self.assertNotIn("failed", statuses)
        # Originals preserved
        self.assertIn("success", statuses)

    def test_no_op_stdout_message(self):
        """Stdout says 'nothing to do' when table is already clean."""
        _run(self.tenant, self.definition, "success")

        out, _ = _call()

        self.assertIn("nothing to do", out.lower(),
                      "stdout should confirm no rows needed repair")

    # ------------------------------------------------------------------
    # Dry-run
    # ------------------------------------------------------------------

    def test_dry_run_does_not_write(self):
        """--dry-run previews the count but does not write to the DB."""
        run = _run(self.tenant, self.definition, "failed")

        _call(["--dry-run"])

        run.refresh_from_db()
        self.assertEqual(
            run.status, "failed",
            "--dry-run must not modify the row",
        )

    def test_dry_run_stdout_mentions_count(self):
        """--dry-run stdout reports the number of rows that would be updated."""
        _run(self.tenant, self.definition, "failed")

        out, _ = _call(["--dry-run"])

        self.assertIn("1", out, "dry-run stdout should mention the affected row count")
        self.assertIn("dry run", out.lower(), "stdout should identify this as a dry run")

    # ------------------------------------------------------------------
    # --tenant-id filter
    # ------------------------------------------------------------------

    def test_tenant_filter_limits_update(self):
        """--tenant-id restricts updates to the specified tenant only."""
        tenant_b = _tenant("fixstatus-c")
        def_b = _definition(tenant_b, "Report C")
        run_a = _run(self.tenant, self.definition, "failed")
        run_b = _run(tenant_b, def_b, "failed")

        _call(["--tenant-id", str(self.tenant.id)])

        run_a.refresh_from_db()
        run_b.refresh_from_db()
        self.assertEqual(run_a.status, "error", "tenant A row should be updated")
        self.assertEqual(run_b.status, "failed", "tenant B row must NOT be updated")

    def test_invalid_tenant_id_raises_command_error(self):
        """An invalid --tenant-id (non-UUID) raises CommandError."""
        with self.assertRaises(CommandError):
            call_command(
                "fix_report_run_status",
                "--tenant-id", "not-a-valid-uuid",
            )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def test_idempotent_on_second_run(self):
        """Running the command twice is safe — the second run is a no-op."""
        run = _run(self.tenant, self.definition, "failed")

        _call()          # first run — updates 'failed' → 'error'
        _call()          # second run — 'error' row is not touched again

        run.refresh_from_db()
        self.assertEqual(run.status, "error")
