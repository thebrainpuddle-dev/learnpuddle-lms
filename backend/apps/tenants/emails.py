# apps/tenants/emails.py
"""
Email helpers for tenant lifecycle events (onboarding, trial expiry, etc.).
Uses HTML templates for professional-looking emails.
"""

import logging

from django.conf import settings

from apps.notifications.email_utils import send_templated_email, build_tenant_url, build_bucket_headers

logger = logging.getLogger(__name__)


def send_onboard_welcome_email(result: dict) -> None:
    """
    Send a welcome email to the newly-created school admin.
    `result` is the dict returned by TenantService.create_tenant_with_admin().
    """
    if not getattr(settings, "SEND_ONBOARDING_EMAIL", True):
        logger.info("Onboarding email skipped (SEND_ONBOARDING_EMAIL=False)")
        return

    tenant = result["tenant"]
    admin = result["admin"]
    login_url = build_tenant_url(tenant=tenant, path="/login")
    forgot_password_url = build_tenant_url(tenant=tenant, path="/forgot-password")
    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")

    subject = f"Welcome to {platform_name} — Your school is ready!"

    context = {
        "first_name": admin.first_name or "there",
        "email": admin.email,
        "school_name": tenant.name,
        "login_url": login_url,
        "forgot_password_url": forgot_password_url,
    }

    fail_silently = getattr(settings, "EMAIL_FAIL_SILENTLY", False)

    try:
        send_templated_email(
            to_email=admin.email,
            subject=subject,
            template_name="admin_welcome.html",
            context=context,
            headers=build_bucket_headers(tenant, "onboarding", "admin_welcome.html", "admin_welcome"),
            fail_silently=fail_silently,
        )
        logger.info(
            "Onboarding welcome email sent tenant=%s to=%s subdomain=%s",
            tenant.id, admin.email, tenant.subdomain,
        )
    except Exception as exc:
        logger.error(
            "Onboarding welcome email failed tenant=%s to=%s err=%s",
            tenant.id, admin.email, exc,
        )
        if not fail_silently:
            raise


def send_trial_expiry_warning_email(tenant, days_left: int) -> None:
    """Warn the school admin that their trial is expiring soon."""
    admin = tenant.users.filter(role="SCHOOL_ADMIN", is_active=True).first()
    if not admin:
        return

    login_url = build_tenant_url(tenant=tenant, path="/login")
    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")

    subject = f"Your trial expires in {days_left} day{'s' if days_left != 1 else ''}"

    context = {
        "first_name": admin.first_name or "there",
        "school_name": tenant.name,
        "days_left": days_left,
        "login_url": login_url,
    }

    fail_silently = getattr(settings, "EMAIL_FAIL_SILENTLY", False)

    try:
        send_templated_email(
            to_email=admin.email,
            subject=subject,
            template_name="trial_expiry.html",
            context=context,
            headers=build_bucket_headers(tenant, "onboarding", "trial_expiry.html", "trial_expiry"),
            fail_silently=fail_silently,
        )
        logger.info(
            "Trial expiry email sent tenant=%s to=%s days_left=%d",
            tenant.id, admin.email, days_left,
        )
    except Exception as exc:
        logger.error(
            "Trial expiry email failed tenant=%s to=%s err=%s",
            tenant.id, admin.email, exc,
        )
        if not fail_silently:
            raise
