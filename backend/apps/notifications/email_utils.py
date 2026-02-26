"""
Email template rendering utilities.
Provides helper functions to render HTML email templates and send both HTML and plain text versions.
"""

import logging
from email.utils import parseaddr
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def get_base_sender_address() -> str:
    """Return envelope sender address without display name."""
    _name, address = parseaddr(getattr(settings, "DEFAULT_FROM_EMAIL", ""))
    if address:
        return address
    return f"noreply@{getattr(settings, 'PLATFORM_DOMAIN', 'localhost')}"


def build_school_sender_email(tenant) -> str:
    """Return school-facing display sender while preserving platform domain."""
    school_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")
    if tenant:
        configured_name = (getattr(tenant, "notification_from_name", "") or "").strip()
        school_name = configured_name or tenant.name
    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")
    return f"{school_name} via {platform_name} <{get_base_sender_address()}>"


def build_tenant_reply_to(tenant) -> list[str]:
    """Return tenant-specific reply-to address fallback chain."""
    if tenant:
        configured = (getattr(tenant, "notification_reply_to", "") or "").strip()
        if configured:
            return [configured]
        if getattr(tenant, "email", ""):
            return [tenant.email]
    return []


def build_bucket_headers(tenant, bucket: str, template_name: str, event: str) -> dict[str, str]:
    """Return deterministic internal headers for mail analytics/bucketization."""
    bucket_prefix = ""
    if tenant:
        bucket_prefix = (getattr(tenant, "email_bucket_prefix", "") or "").strip()
        if not bucket_prefix:
            bucket_prefix = (getattr(tenant, "subdomain", "") or "").strip()
    if not bucket_prefix:
        bucket_prefix = "platform"

    return {
        "X-LP-Bucket": f"{bucket_prefix}:{bucket}",
        "X-LP-Template": template_name,
        "X-LP-Tenant": str(getattr(tenant, "id", "")) or "platform",
        "X-LP-Event": event,
    }


def get_base_context() -> dict:
    """Return common context variables for all email templates."""
    return {
        "platform_name": getattr(settings, "PLATFORM_NAME", "LearnPuddle"),
        "platform_domain": getattr(settings, "PLATFORM_DOMAIN", "learnpuddle.com"),
        "year": datetime.now().year,
    }


def render_email_template(template_name: str, context: dict) -> tuple[str, str]:
    """
    Render an email template and return both HTML and plain text versions.
    
    Args:
        template_name: Name of the template file (e.g., 'teacher_welcome.html')
        context: Dictionary of context variables for the template
    
    Returns:
        Tuple of (html_content, text_content)
    """
    full_context = {**get_base_context(), **context}
    
    html_content = render_to_string(f"emails/{template_name}", full_context)
    text_content = strip_tags(html_content)
    text_content = "\n".join(line.strip() for line in text_content.split("\n") if line.strip())
    
    return html_content, text_content


def send_templated_email(
    to_email: str,
    subject: str,
    template_name: str,
    context: dict,
    from_email: Optional[str] = None,
    reply_to: Optional[list[str]] = None,
    headers: Optional[dict[str, str]] = None,
    fail_silently: bool = False,
) -> bool:
    """
    Send an email using an HTML template with plain text fallback.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        template_name: Template file name (e.g., 'teacher_welcome.html')
        context: Context variables for the template
        from_email: Sender email (defaults to DEFAULT_FROM_EMAIL)
        fail_silently: Whether to suppress exceptions
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    if from_email is None:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"noreply@{getattr(settings, 'PLATFORM_DOMAIN', 'localhost')}"
    
    try:
        html_content, text_content = render_email_template(template_name, context)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[to_email],
            reply_to=reply_to or [],
            headers=headers or {},
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=fail_silently)
        
        logger.info("Templated email sent to=%s template=%s subject=%s", to_email, template_name, subject)
        return True
        
    except Exception as exc:
        logger.error("Templated email failed to=%s template=%s err=%s", to_email, template_name, exc)
        if not fail_silently:
            raise
        return False


def build_tenant_url(tenant=None, path: str = "/login") -> str:
    """Build a tenant-aware URL preferring verified custom domains."""
    domain = getattr(settings, "PLATFORM_DOMAIN", "learnpuddle.com").strip().lower()
    normalized_path = path if path.startswith("/") else f"/{path}"

    if tenant is not None:
        custom_domain = (getattr(tenant, "custom_domain", "") or "").strip().lower().rstrip(".")
        if custom_domain and bool(getattr(tenant, "custom_domain_verified", False)):
            return f"https://{custom_domain}{normalized_path}"

        subdomain = (getattr(tenant, "subdomain", "") or "").strip().lower()
        if subdomain:
            return f"https://{subdomain}.{domain}{normalized_path}"

    return f"https://{domain}{normalized_path}"


def build_login_url(subdomain: str, path: str = "/login") -> str:
    """Backward-compatible wrapper around tenant-aware URL building."""
    class _TenantProxy:
        def __init__(self, subdomain_value: str):
            self.subdomain = subdomain_value
            self.custom_domain = ""
            self.custom_domain_verified = False

    tenant = _TenantProxy(subdomain or "")
    return build_tenant_url(tenant=tenant, path=path)
