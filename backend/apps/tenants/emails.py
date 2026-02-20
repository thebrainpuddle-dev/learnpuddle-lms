# apps/tenants/emails.py
"""
Email helpers for tenant lifecycle events (onboarding, trial expiry, etc.).
Uses Django's send_mail which respects EMAIL_BACKEND in settings.
"""

from django.conf import settings
from django.core.mail import send_mail


def _build_login_url(subdomain: str) -> str:
    """Build the login URL for a tenant."""
    domain = getattr(settings, "PLATFORM_DOMAIN", "lms.com")
    scheme = "https" if not settings.DEBUG else "http"
    port = ":3000" if settings.DEBUG else ""
    return f"{scheme}://{subdomain}.{domain}{port}"


def send_onboard_welcome_email(result: dict) -> None:
    """
    Send a welcome email to the newly-created school admin.
    `result` is the dict returned by TenantService.create_tenant_with_admin().
    """
    tenant = result["tenant"]
    admin = result["admin"]
    subdomain = tenant.subdomain
    login_url = _build_login_url(subdomain)

    subject = f"Welcome to {getattr(settings, 'PLATFORM_NAME', 'LearnPuddle')} — Your school is ready!"
    body = (
        f"Hi {admin.first_name},\n\n"
        f"Your school \"{tenant.name}\" has been set up on our platform.\n\n"
        f"Here are your login details:\n"
        f"  URL:      {login_url}\n"
        f"  Email:    {admin.email}\n"
        f"  Password: (the one provided during onboarding)\n\n"
        f"Please change your password after your first login.\n\n"
        f"If you have any questions, reply to this email.\n\n"
        f"— The {getattr(settings, 'PLATFORM_NAME', 'LearnPuddle')} Team"
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[admin.email],
        fail_silently=True,
    )


def send_trial_expiry_warning_email(tenant, days_left: int) -> None:
    """Warn the school admin that their trial is expiring soon."""
    admin = tenant.users.filter(role="SCHOOL_ADMIN", is_active=True).first()
    if not admin:
        return

    login_url = _build_login_url(tenant.subdomain)
    subject = f"Your trial expires in {days_left} day{'s' if days_left != 1 else ''}"
    body = (
        f"Hi {admin.first_name},\n\n"
        f"Your trial for \"{tenant.name}\" on {getattr(settings, 'PLATFORM_NAME', 'LearnPuddle')} "
        f"will expire in {days_left} day{'s' if days_left != 1 else ''}.\n\n"
        f"Log in at {login_url} to continue using the platform.\n\n"
        f"To upgrade or extend your trial, please contact us by replying to this email.\n\n"
        f"— The {getattr(settings, 'PLATFORM_NAME', 'LearnPuddle')} Team"
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[admin.email],
        fail_silently=True,
    )
