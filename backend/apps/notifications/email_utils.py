"""
Email template rendering utilities.
Provides helper functions to render HTML email templates and send both HTML and plain text versions.
"""

import logging
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


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


def build_login_url(subdomain: str, path: str = "/login") -> str:
    """Build a full URL for a tenant's login page."""
    domain = getattr(settings, "PLATFORM_DOMAIN", "learnpuddle.com")
    if subdomain:
        return f"https://{subdomain}.{domain}{path}"
    return f"https://{domain}{path}"
