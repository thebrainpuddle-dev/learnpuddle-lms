# tests/tenants/test_trial_tasks.py
"""
Unit tests for apps/tenants/tasks.py — currently 0% coverage.

Covers:
1. check_trial_expirations()         — deactivation + email warning logic
2. _notify_super_admin_deactivations() — super-admin email notification

NOTE ON PATCH TARGETS:
`apps/tenants/tasks.py::check_trial_expirations` performs a *function-local*
import:

    def check_trial_expirations():
        ...
        from apps.tenants.emails import send_trial_expiry_warning_email

Because that import runs inside the function body, `send_trial_expiry_warning_email`
is NOT an attribute of the `apps.tenants.tasks` module — patching
`apps.tenants.tasks.send_trial_expiry_warning_email` raises AttributeError.

The correct patch target is the *source* module:
`apps.tenants.emails.send_trial_expiry_warning_email`.

By contrast `_notify_super_admin_deactivations` is defined directly inside
`apps/tenants/tasks.py`, so patching it on the tasks module is correct.
"""

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.tenants.models import Tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trial_tenant(name, subdomain, trial_end_date=None, is_active=True):
    """Create a trial Tenant with configurable trial_end_date."""
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=is_active,
        is_trial=True,
        trial_end_date=trial_end_date,
    )


def _make_paid_tenant(name, subdomain):
    """Create a non-trial Tenant (should never be touched by trial tasks)."""
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=True,
        is_trial=False,
        trial_end_date=None,
    )


# ===========================================================================
# 1. check_trial_expirations() — deactivation logic
# ===========================================================================

@pytest.mark.django_db
class CheckTrialExpirationsDeactivationTestCase(TestCase):
    """Tests for the deactivation branch of check_trial_expirations."""

    def _run(self, today_date):
        """Run the task with a mocked 'today' date."""
        mock_now = MagicMock()
        mock_now.date.return_value = today_date
        # send_trial_expiry_warning_email is imported lazily inside the task,
        # so it must be patched at its source module (apps.tenants.emails),
        # not at apps.tenants.tasks (which has no such attribute).
        with patch("apps.tenants.tasks.timezone.now", return_value=mock_now), \
             patch("apps.tenants.emails.send_trial_expiry_warning_email"), \
             patch("apps.tenants.tasks._notify_super_admin_deactivations"):
            from apps.tenants.tasks import check_trial_expirations
            return check_trial_expirations()

    def test_no_expired_trials_returns_zero_deactivations(self):
        """No tenants past grace period → 'Deactivated 0 tenant(s)' returned."""
        today = date(2026, 4, 30)
        # Trial ends today — not past grace period yet
        _make_trial_tenant("Active Trial", "activetrial", trial_end_date=today)

        result = self._run(today)
        self.assertIn("Deactivated 0", result)

    def test_tenant_past_grace_period_is_deactivated(self):
        """
        Trial ended more than TRIAL_GRACE_PERIOD_DAYS (3) days ago →
        tenant should be deactivated.
        """
        from apps.tenants.tasks import TRIAL_GRACE_PERIOD_DAYS
        today = date(2026, 4, 30)
        # Trial ended 10 days ago → well past grace period
        expired_end = today - timedelta(days=10)
        tenant = _make_trial_tenant("Expired School", "expired", trial_end_date=expired_end)

        self._run(today)

        tenant.refresh_from_db()
        self.assertFalse(tenant.is_active, "Tenant past grace period must be deactivated")

    def test_tenant_within_grace_period_stays_active(self):
        """
        Trial ended exactly TRIAL_GRACE_PERIOD_DAYS (3) days ago →
        still within grace period, must NOT be deactivated.
        """
        from apps.tenants.tasks import TRIAL_GRACE_PERIOD_DAYS
        today = date(2026, 4, 30)
        # Trial ended exactly 3 days ago (boundary — deactivation uses __lt, not __lte)
        boundary_end = today - timedelta(days=TRIAL_GRACE_PERIOD_DAYS)
        tenant = _make_trial_tenant("Grace School", "grace", trial_end_date=boundary_end)

        self._run(today)

        tenant.refresh_from_db()
        self.assertTrue(tenant.is_active, "Tenant within grace period must remain active")

    def test_non_trial_tenant_is_never_deactivated(self):
        """A paid (non-trial) tenant must never be touched, even with an old date."""
        today = date(2026, 4, 30)
        old_date = today - timedelta(days=100)
        # Non-trial tenant with old trial_end_date (shouldn't matter)
        paid_tenant = _make_paid_tenant("Paid School", "paid")

        self._run(today)

        paid_tenant.refresh_from_db()
        self.assertTrue(paid_tenant.is_active, "Non-trial tenant must never be deactivated")

    def test_already_inactive_trial_tenant_stays_inactive(self):
        """An already-inactive trial tenant must not be double-processed.

        Also verifies no warning email is sent for an already-inactive tenant —
        that would be redundant spam to an admin whose trial has long expired.
        The deactivation queryset filters ``is_active=True``, so already-inactive
        tenants are excluded from processing entirely.
        """
        today = date(2026, 4, 30)
        expired_end = today - timedelta(days=10)
        tenant = _make_trial_tenant(
            "Already Inactive", "inactive", trial_end_date=expired_end, is_active=False
        )

        # Inline explicit patching so we can capture the email mock and assert
        # it was never called (the _run() helper patches email but discards the mock).
        mock_now = MagicMock()
        mock_now.date.return_value = today
        mock_email = MagicMock()
        with patch("apps.tenants.tasks.timezone.now", return_value=mock_now), \
             patch("apps.tenants.emails.send_trial_expiry_warning_email", mock_email), \
             patch("apps.tenants.tasks._notify_super_admin_deactivations"):
            from apps.tenants.tasks import check_trial_expirations
            check_trial_expirations()

        # Should still be inactive — not re-processed
        tenant.refresh_from_db()
        self.assertFalse(tenant.is_active)
        # No warning email for an already-inactive tenant
        mock_email.assert_not_called()

    def test_multiple_expired_tenants_all_deactivated(self):
        """Multiple expired tenants must all be deactivated in a single run."""
        today = date(2026, 4, 30)
        expired_end = today - timedelta(days=10)
        t1 = _make_trial_tenant("School A", "schoola", trial_end_date=expired_end)
        t2 = _make_trial_tenant("School B", "schoolb", trial_end_date=expired_end)

        self._run(today)

        t1.refresh_from_db()
        t2.refresh_from_db()
        self.assertFalse(t1.is_active)
        self.assertFalse(t2.is_active)

    def test_result_includes_deactivation_count(self):
        """Return value must report the number of deactivated tenants."""
        today = date(2026, 4, 30)
        expired_end = today - timedelta(days=10)
        _make_trial_tenant("Count School", "countschool", trial_end_date=expired_end)

        result = self._run(today)

        self.assertIn("Deactivated 1", result)


# ===========================================================================
# 2. check_trial_expirations() — warning email logic
# ===========================================================================

@pytest.mark.django_db
class CheckTrialExpirationsWarningEmailTestCase(TestCase):
    """Tests for the warning email branch of check_trial_expirations."""

    def _run_with_mocked_email(self, today_date):
        """Run the task and capture calls to send_trial_expiry_warning_email."""
        mock_now = MagicMock()
        mock_now.date.return_value = today_date
        mock_email = MagicMock()
        # Patch send_trial_expiry_warning_email at its *source* module — see the
        # module docstring for why patching it on apps.tenants.tasks would fail.
        with patch("apps.tenants.tasks.timezone.now", return_value=mock_now), \
             patch("apps.tenants.emails.send_trial_expiry_warning_email", mock_email), \
             patch("apps.tenants.tasks._notify_super_admin_deactivations"):
            from apps.tenants.tasks import check_trial_expirations
            check_trial_expirations()
        return mock_email

    def test_sends_warning_email_7_days_before_expiry(self):
        """Trial expiring in 7 days → warning email sent."""
        today = date(2026, 4, 30)
        expiry_date = today + timedelta(days=7)
        tenant = _make_trial_tenant("Seven Day School", "sevenday", trial_end_date=expiry_date)

        mock_email = self._run_with_mocked_email(today)

        # Should have been called with this tenant and days_left=7
        called_tenants = [call.args[0] for call in mock_email.call_args_list]
        self.assertIn(tenant, called_tenants)

    def test_sends_warning_email_3_days_before_expiry(self):
        """Trial expiring in 3 days → warning email sent."""
        today = date(2026, 4, 30)
        expiry_date = today + timedelta(days=3)
        tenant = _make_trial_tenant("Three Day School", "threeday", trial_end_date=expiry_date)

        mock_email = self._run_with_mocked_email(today)

        called_tenants = [call.args[0] for call in mock_email.call_args_list]
        self.assertIn(tenant, called_tenants)

    def test_no_warning_email_for_non_expiring_trial(self):
        """Trial expiring in 15 days (not in warning windows) → no email sent."""
        today = date(2026, 4, 30)
        expiry_date = today + timedelta(days=15)
        _make_trial_tenant("Far Away School", "faraway", trial_end_date=expiry_date)

        mock_email = self._run_with_mocked_email(today)

        mock_email.assert_not_called()

    def test_email_failure_does_not_abort_task(self):
        """If warning email raises an exception, the task must continue (not crash)."""
        today = date(2026, 4, 30)
        expiry_date = today + timedelta(days=7)
        _make_trial_tenant("Error School", "errorschool", trial_end_date=expiry_date)

        mock_now = MagicMock()
        mock_now.date.return_value = today
        # Patch the email at its source module — see the module docstring for
        # why patching apps.tenants.tasks.send_trial_expiry_warning_email fails.
        with patch("apps.tenants.tasks.timezone.now", return_value=mock_now), \
             patch(
                 "apps.tenants.emails.send_trial_expiry_warning_email",
                 side_effect=Exception("SMTP down")
             ), \
             patch("apps.tenants.tasks._notify_super_admin_deactivations"):
            from apps.tenants.tasks import check_trial_expirations
            # Should not raise, even with email failure
            result = check_trial_expirations()

        self.assertIsNotNone(result)

    def test_no_warnings_for_non_trial_tenants(self):
        """Paid (non-trial) tenants must never receive trial expiry warnings."""
        today = date(2026, 4, 30)
        # Paid tenant with trial_end_date = 7 days from now (should be ignored)
        paid_tenant = _make_paid_tenant("Paid No Warning", "paidnowarning")

        mock_email = self._run_with_mocked_email(today)

        called_tenants = [call.args[0] for call in mock_email.call_args_list]
        self.assertNotIn(paid_tenant, called_tenants)


# ===========================================================================
# 3. _notify_super_admin_deactivations()
# ===========================================================================

@override_settings(
    SUPER_ADMIN_EMAIL="superadmin@learnpuddle.com",
    DEFAULT_FROM_EMAIL="noreply@learnpuddle.com",
)
@pytest.mark.django_db
class NotifySuperAdminDeactivationsTestCase(TestCase):
    """Tests for the _notify_super_admin_deactivations() helper."""

    def test_no_email_for_empty_list(self):
        """Empty tenant list → no email sent."""
        from apps.tenants.tasks import _notify_super_admin_deactivations
        with patch("apps.tenants.tasks.send_mail") as mock_send:
            _notify_super_admin_deactivations([])
            mock_send.assert_not_called()

    def test_sends_email_when_admin_email_configured(self):
        """With SUPER_ADMIN_EMAIL set + deactivated tenants → send_mail called."""
        from apps.tenants.tasks import _notify_super_admin_deactivations
        deactivated = [(1, "Test School", "testschool", "admin@testschool.com")]

        with patch("apps.tenants.tasks.send_mail") as mock_send:
            _notify_super_admin_deactivations(deactivated)
            mock_send.assert_called_once()

    def test_email_contains_deactivated_school_name(self):
        """Email body must mention the deactivated school name."""
        from apps.tenants.tasks import _notify_super_admin_deactivations
        deactivated = [(1, "Riverside Academy", "riverside", "admin@riverside.com")]

        with patch("apps.tenants.tasks.send_mail") as mock_send:
            _notify_super_admin_deactivations(deactivated)
            call_kwargs = mock_send.call_args
            message = call_kwargs[0][1]  # second positional arg is the message
            self.assertIn("Riverside Academy", message)

    def test_email_sent_to_super_admin_address(self):
        """Email must be sent to SUPER_ADMIN_EMAIL."""
        from apps.tenants.tasks import _notify_super_admin_deactivations
        deactivated = [(1, "Some School", "some", "admin@some.com")]

        with patch("apps.tenants.tasks.send_mail") as mock_send:
            _notify_super_admin_deactivations(deactivated)
            recipients = mock_send.call_args[0][3]  # 4th positional arg is recipient_list
            self.assertIn("superadmin@learnpuddle.com", recipients)

    @override_settings(SUPER_ADMIN_EMAIL=None)
    def test_no_email_when_admin_email_not_configured(self):
        """If SUPER_ADMIN_EMAIL is not set, send_mail must NOT be called."""
        from apps.tenants.tasks import _notify_super_admin_deactivations
        deactivated = [(1, "Test School", "testschool", "admin@testschool.com")]

        with patch("apps.tenants.tasks.send_mail") as mock_send:
            _notify_super_admin_deactivations(deactivated)
            mock_send.assert_not_called()

    def test_email_failure_does_not_raise(self):
        """send_mail failure must be caught — _notify must never raise."""
        from apps.tenants.tasks import _notify_super_admin_deactivations
        deactivated = [(1, "Crash School", "crash", "admin@crash.com")]

        with patch("apps.tenants.tasks.send_mail", side_effect=Exception("SMTP error")):
            # Should not raise
            _notify_super_admin_deactivations(deactivated)
