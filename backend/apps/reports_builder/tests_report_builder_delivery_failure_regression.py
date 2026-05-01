"""
Regression test — ReportRun.status must be a valid STATUS_CHOICES value when
all scheduled-report email deliveries fail.

Bug:
    apps/reports_builder/tasks.py:execute_scheduled_report set
    ``run.status = "failed"`` when every email recipient fails, but ``"failed"``
    is NOT in ``ReportRun.STATUS_CHOICES``.  The correct status is ``"error"``
    (consistent with every other failure path in the same task, e.g. lines
    91, 99, 113, 249).

Related:
    - tasks.py line 374 (the fix)
    - tests_report_builder.py:1035 (qa-tester: change assertion "failed" → "error")

Run (Docker):
    docker compose exec web pytest \\
        apps/reports_builder/tests_report_builder_delivery_failure_regression.py -v
    Expected: 2 PASS
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.reports_builder.models import ReportDefinition, ReportRun, ReportSchedule
from apps.tenants.models import Tenant

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_RUN_STATUSES = {choice[0] for choice in ReportRun.STATUS_CHOICES}


def _make_tenant(subdomain: str) -> Tenant:
    return Tenant.objects.create(
        name=f"Delivery Fail Regression {subdomain}",
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.test",
        is_active=True,
    )


def _make_user(tenant: Tenant, email: str, role: str = "TEACHER") -> User:
    user = User.objects.create_user(
        email=email,
        password="Pass@1234!",
        first_name="Test",
        last_name="User",
        role=role,
    )
    user.tenant = tenant
    user.save()
    return user


def _patch_csv_stack(schedule_id: str, send_mail_side_effect) -> None:
    """Run execute_scheduled_report with a mocked CSV pipeline and custom send_mail."""
    with patch(
        "apps.reports_builder.tasks.run_report",
        return_value=([{"id": "1", "title": "Course"}], 1),
    ), patch(
        "apps.reports_builder.tasks.rows_to_csv",
        return_value=(b"id,title\n1,Course\n", "deadbeef" * 8),
    ), patch(
        "apps.reports_builder.tasks._artifact_path",
    ) as mock_path, patch(
        "apps.reports_builder.tasks.send_mail",
        side_effect=send_mail_side_effect,
    ):
        mock_path.return_value.write_bytes = MagicMock()
        type(mock_path.return_value).__str__ = lambda self: "/tmp/regression_report.csv"

        from apps.reports_builder.tasks import execute_scheduled_report

        execute_scheduled_report(schedule_id)


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeliveryFailureRunStatusIsValidChoice(TestCase):
    """
    execute_scheduled_report must use a STATUS_CHOICES-valid value for
    run.status when all email deliveries fail.

    TDD regression for the bug where ``run.status = "failed"`` was written
    but ``"failed"`` is not in ReportRun.STATUS_CHOICES.
    """

    def setUp(self):
        self.tenant = _make_tenant("dfregr1")
        self.admin = _make_user(self.tenant, "admin@dfregr1.test", role="SCHOOL_ADMIN")
        self.teacher = _make_user(self.tenant, "teacher@dfregr1.test", role="TEACHER")

        self.definition = ReportDefinition.all_objects.create(
            tenant=self.tenant,
            created_by=self.admin,
            name="Regression Report",
            data_source="courses",
            filters_json=[],
            group_by_json=[],
            aggregates_json=[],
        )
        self.schedule = ReportSchedule.all_objects.create(
            definition=self.definition,
            tenant=self.tenant,
            cadence="daily",
            run_at_hour=9,
            recipients_json=["teacher@dfregr1.test"],
            enabled=True,
        )

    def _latest_run(self) -> ReportRun:
        return (
            ReportRun.all_objects.filter(
                tenant=self.tenant,
                definition=self.definition,
            )
            .order_by("-started_at")
            .first()
        )

    def test_all_deliveries_fail_sets_run_status_to_valid_choice(self):
        """
        run.status must be a member of ReportRun.STATUS_CHOICES when all
        email deliveries fail.

        RED phase: currently fails because code sets status = "failed" which
        is NOT in STATUS_CHOICES.

        After fix (run.status = "error"): this test goes GREEN.
        """
        _patch_csv_stack(
            str(self.schedule.id),
            send_mail_side_effect=OSError("SMTP connection refused"),
        )

        run = self._latest_run()
        self.assertIsNotNone(run, "A ReportRun should have been created")

        self.assertIn(
            run.status,
            VALID_RUN_STATUSES,
            f"run.status='{run.status}' is NOT in STATUS_CHOICES={VALID_RUN_STATUSES}. "
            f"Bug: tasks.py:execute_scheduled_report set 'failed' instead of a valid status.",
        )

    def test_all_deliveries_fail_sets_run_status_to_error(self):
        """
        run.status must be specifically 'error' when all deliveries fail.

        'error' is the only STATUS_CHOICES failure value for ReportRun.
        The schedule-level delivery failure is captured via
        ``schedule.last_run_status = 'delivery_failed'`` (a separate status
        vocabulary on ReportSchedule — correct and unchanged by this fix).
        """
        _patch_csv_stack(
            str(self.schedule.id),
            send_mail_side_effect=OSError("SMTP connection refused"),
        )

        run = self._latest_run()
        self.assertIsNotNone(run)
        self.assertEqual(
            run.status,
            "error",
            f"Expected run.status='error' (valid STATUS_CHOICES failure value), "
            f"got '{run.status}'. "
            f"The delivery error detail is captured in run.error and "
            f"schedule.last_run_status='delivery_failed'.",
        )

        # Confirm error field captures delivery failure detail
        self.assertIn("DELIVERY_FAILED", run.error or "", "run.error should log delivery failure")

        # Confirm schedule-level status uses its own 'delivery_failed' vocab (unchanged)
        self.schedule.refresh_from_db()
        self.assertEqual(
            self.schedule.last_run_status,
            "delivery_failed",
            "schedule.last_run_status should be 'delivery_failed'",
        )
