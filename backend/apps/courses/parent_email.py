"""
Parent portal email utilities.

Sends magic link emails to parents for authentication.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_parent_magic_link(parent_email, tenant, token):
    """
    Send a magic link email to a parent.

    Args:
        parent_email: The parent's email address.
        tenant: The Tenant instance.
        token: The magic link token string.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    tenant_name = tenant.name or 'LearnPuddle'
    # Build the magic link URL
    subdomain = tenant.subdomain
    domain = getattr(settings, 'PLATFORM_DOMAIN', 'learnpuddle.com')
    debug = getattr(settings, 'DEBUG', False)

    if debug:
        # Local development — use localhost with frontend dev server port
        frontend_port = getattr(settings, 'FRONTEND_DEV_PORT', '3000')
        base_url = f"http://{subdomain}.localhost:{frontend_port}"
    else:
        base_url = f"https://{subdomain}.{domain}"
    magic_url = f"{base_url}/parent/verify?token={token}"

    subject = f"Your {tenant_name} Parent Portal Access"

    message = (
        f"Hi,\n\n"
        f"Click the link below to view your child's learning progress on {tenant_name}:\n\n"
        f"{magic_url}\n\n"
        f"This link expires in 15 minutes. If you didn't request this, "
        f"you can safely ignore this email.\n\n"
        f"— {tenant_name}"
    )

    html_message = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px;">
        <p style="color: #374151; font-size: 15px; line-height: 1.6;">Hi,</p>
        <p style="color: #374151; font-size: 15px; line-height: 1.6;">
            Click the button below to view your child's learning progress on <strong>{tenant_name}</strong>:
        </p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{magic_url}"
               style="display: inline-block; padding: 12px 32px; background-color: #4F46E5; color: #ffffff;
                      text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px;">
                View Dashboard &rarr;
            </a>
        </div>
        <p style="color: #6B7280; font-size: 13px; line-height: 1.5;">
            This link expires in 15 minutes. If you didn't request this, you can safely ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 24px 0;" />
        <p style="color: #9CA3AF; font-size: 12px;">&mdash; {tenant_name}</p>
    </div>
    """

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[parent_email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("Parent magic link sent to %s for tenant %s", parent_email, tenant.subdomain)
        return True
    except Exception:
        logger.exception("Failed to send parent magic link to %s", parent_email)
        return False
