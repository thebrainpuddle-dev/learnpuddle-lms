# tests/tenants/test_tenant_emails.py
"""
Unit tests for apps/tenants/emails.py.

Tests:
  - send_onboard_welcome_email: happy path, SEND_ONBOARDING_EMAIL=False skip,
    email failure with fail_silently=True, email failure with fail_silently=False,
    subject contains platform name, admin first_name fallback.
  - send_trial_expiry_warning_email: happy path (7 days, 1 day — plural/singular),
    no admin (skip), email failure with fail_silently=True.
"""

from unittest.mock import MagicMock, patch, call

from django.test import TestCase, override_settings

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name="Email School", subdomain=None, domain_suffix="emailtest"):
    sub = subdomain or f"{domain_suffix}"
    return Tenant.objects.create(
        name=name,
        slug=sub,
        subdomain=sub,
        email=f"admin@{sub}.example.com",
        is_active=True,
    )


def _make_admin(tenant, email=None, first_name="Principal", last_name="User"):
    email = email or f"admin@{tenant.subdomain}.example.com"
    return User.objects.create_user(
        email=email,
        password="Pass!1234",
        first_name=first_name,
        last_name=last_name,
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _onboard_result(tenant, admin):
    """Build the dict shape returned by TenantService.create_tenant_with_admin()."""
    return {"tenant": tenant, "admin": admin}


# ===========================================================================
# 1. send_onboard_welcome_email
# ===========================================================================

@override_settings(
    PLATFORM_DOMAIN="lms.com",
    PLATFORM_NAME="LearnPuddle",
    SEND_ONBOARDING_EMAIL=True,
    EMAIL_FAIL_SILENTLY=False,
)
class SendOnboardWelcomeEmailTestCase(TestCase):
    """Tests for send_onboard_welcome_email()."""

    def setUp(self):
        self.tenant = _make_tenant("Onboard School", "onboard")
        self.admin = _make_admin(self.tenant, first_name="Jane")

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_sends_email_to_admin(self, mock_headers, mock_url, mock_send):
        """Happy path: email is dispatched to the admin's address."""
        from apps.tenants.emails import send_onboard_welcome_email
        result = _onboard_result(self.tenant, self.admin)
        send_onboard_welcome_email(result)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["to_email"], self.admin.email)

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_subject_contains_platform_name(self, mock_headers, mock_url, mock_send):
        """Subject line must include the platform name."""
        from apps.tenants.emails import send_onboard_welcome_email
        send_onboard_welcome_email(_onboard_result(self.tenant, self.admin))
        subject = mock_send.call_args[1]["subject"]
        self.assertIn("LearnPuddle", subject)

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_context_contains_first_name(self, mock_headers, mock_url, mock_send):
        """Email context must include the admin's first name."""
        from apps.tenants.emails import send_onboard_welcome_email
        send_onboard_welcome_email(_onboard_result(self.tenant, self.admin))
        context = mock_send.call_args[1]["context"]
        self.assertEqual(context["first_name"], "Jane")

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_context_first_name_fallback_when_empty(self, mock_headers, mock_url, mock_send):
        """When first_name is empty, context falls back to 'there'."""
        from apps.tenants.emails import send_onboard_welcome_email
        admin_no_name = _make_admin(
            self.tenant,
            email="noname@onboard.example.com",
            first_name="",
        )
        send_onboard_welcome_email(_onboard_result(self.tenant, admin_no_name))
        context = mock_send.call_args[1]["context"]
        self.assertEqual(context["first_name"], "there")

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_context_contains_school_name(self, mock_headers, mock_url, mock_send):
        """Email context must include the tenant's school name."""
        from apps.tenants.emails import send_onboard_welcome_email
        send_onboard_welcome_email(_onboard_result(self.tenant, self.admin))
        context = mock_send.call_args[1]["context"]
        self.assertEqual(context["school_name"], "Onboard School")

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_uses_admin_welcome_template(self, mock_headers, mock_url, mock_send):
        """Must use the 'admin_welcome.html' template."""
        from apps.tenants.emails import send_onboard_welcome_email
        send_onboard_welcome_email(_onboard_result(self.tenant, self.admin))
        template = mock_send.call_args[1]["template_name"]
        self.assertEqual(template, "admin_welcome.html")

    @override_settings(SEND_ONBOARDING_EMAIL=False)
    @patch("apps.tenants.emails.send_templated_email")
    def test_skips_when_send_onboarding_email_is_false(self, mock_send):
        """When SEND_ONBOARDING_EMAIL=False the function must not send anything."""
        from apps.tenants.emails import send_onboard_welcome_email
        send_onboard_welcome_email(_onboard_result(self.tenant, self.admin))
        mock_send.assert_not_called()

    @override_settings(EMAIL_FAIL_SILENTLY=True)
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    @patch("apps.tenants.emails.send_templated_email", side_effect=OSError("SMTP down"))
    def test_email_failure_silenced_when_fail_silently_true(
        self, mock_send, mock_headers, mock_url
    ):
        """When EMAIL_FAIL_SILENTLY=True an SMTP error must not propagate."""
        from apps.tenants.emails import send_onboard_welcome_email
        # Should NOT raise
        send_onboard_welcome_email(_onboard_result(self.tenant, self.admin))

    @override_settings(EMAIL_FAIL_SILENTLY=False)
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://onboard.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    @patch("apps.tenants.emails.send_templated_email", side_effect=OSError("SMTP down"))
    def test_email_failure_raises_when_fail_silently_false(
        self, mock_send, mock_headers, mock_url
    ):
        """When EMAIL_FAIL_SILENTLY=False an SMTP error must re-raise."""
        from apps.tenants.emails import send_onboard_welcome_email
        with self.assertRaises(OSError):
            send_onboard_welcome_email(_onboard_result(self.tenant, self.admin))


# ===========================================================================
# 2. send_trial_expiry_warning_email
# ===========================================================================

@override_settings(
    PLATFORM_DOMAIN="lms.com",
    PLATFORM_NAME="LearnPuddle",
    EMAIL_FAIL_SILENTLY=False,
)
class SendTrialExpiryWarningEmailTestCase(TestCase):
    """Tests for send_trial_expiry_warning_email()."""

    def setUp(self):
        self.tenant = _make_tenant("Trial School", "trial")
        self.admin = _make_admin(self.tenant, first_name="Bob")

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_sends_email_to_school_admin(self, mock_headers, mock_url, mock_send):
        """Happy path: sends email to the SCHOOL_ADMIN for the tenant."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        send_trial_expiry_warning_email(self.tenant, days_left=7)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["to_email"], self.admin.email)

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_subject_plural_days_when_more_than_one(self, mock_headers, mock_url, mock_send):
        """Subject must use plural 'days' when days_left > 1."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        send_trial_expiry_warning_email(self.tenant, days_left=7)
        subject = mock_send.call_args[1]["subject"]
        self.assertIn("7 days", subject)

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_subject_singular_day_when_one_day_left(self, mock_headers, mock_url, mock_send):
        """Subject must use singular 'day' when days_left == 1."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        send_trial_expiry_warning_email(self.tenant, days_left=1)
        subject = mock_send.call_args[1]["subject"]
        self.assertIn("1 day", subject)
        self.assertNotIn("1 days", subject)

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_context_contains_days_left(self, mock_headers, mock_url, mock_send):
        """Email context must include days_left."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        send_trial_expiry_warning_email(self.tenant, days_left=3)
        context = mock_send.call_args[1]["context"]
        self.assertEqual(context["days_left"], 3)

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_context_contains_first_name(self, mock_headers, mock_url, mock_send):
        """Email context must include admin first_name."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        send_trial_expiry_warning_email(self.tenant, days_left=7)
        context = mock_send.call_args[1]["context"]
        self.assertEqual(context["first_name"], "Bob")

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_uses_trial_expiry_template(self, mock_headers, mock_url, mock_send):
        """Must use the 'trial_expiry.html' template."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        send_trial_expiry_warning_email(self.tenant, days_left=7)
        template = mock_send.call_args[1]["template_name"]
        self.assertEqual(template, "trial_expiry.html")

    @patch("apps.tenants.emails.send_templated_email")
    def test_skips_when_no_active_admin(self, mock_send):
        """If the tenant has no active SCHOOL_ADMIN, the email is silently skipped."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        tenant_no_admin = _make_tenant("No Admin School", "noadmin")
        # No SCHOOL_ADMIN user created
        send_trial_expiry_warning_email(tenant_no_admin, days_left=7)
        mock_send.assert_not_called()

    @patch("apps.tenants.emails.send_templated_email")
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    def test_skips_when_admin_is_inactive(self, mock_headers, mock_url, mock_send):
        """Inactive SCHOOL_ADMINs must be ignored (the query filters is_active=True)."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        self.admin.is_active = False
        self.admin.save()
        send_trial_expiry_warning_email(self.tenant, days_left=7)
        mock_send.assert_not_called()

    @override_settings(EMAIL_FAIL_SILENTLY=True)
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    @patch("apps.tenants.emails.send_templated_email", side_effect=OSError("SMTP timeout"))
    def test_email_failure_silenced_when_fail_silently_true(
        self, mock_send, mock_headers, mock_url
    ):
        """When EMAIL_FAIL_SILENTLY=True SMTP errors must not propagate."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        # Must NOT raise even when SMTP fails
        send_trial_expiry_warning_email(self.tenant, days_left=7)

    @override_settings(EMAIL_FAIL_SILENTLY=False)
    @patch("apps.tenants.emails.build_tenant_url", return_value="https://trial.lms.com/login")
    @patch("apps.tenants.emails.build_bucket_headers", return_value={})
    @patch("apps.tenants.emails.send_templated_email", side_effect=OSError("SMTP timeout"))
    def test_email_failure_raises_when_fail_silently_false(
        self, mock_send, mock_headers, mock_url
    ):
        """When EMAIL_FAIL_SILENTLY=False SMTP errors must re-raise."""
        from apps.tenants.emails import send_trial_expiry_warning_email
        with self.assertRaises(OSError):
            send_trial_expiry_warning_email(self.tenant, days_left=7)
