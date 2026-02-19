# apps/tenants/tasks.py
"""
Periodic Celery tasks for tenant lifecycle management.
"""

import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

# Grace period: tenants are deactivated this many days AFTER trial_end_date
TRIAL_GRACE_PERIOD_DAYS = 3


@shared_task(name="tenants.check_trial_expirations")
def check_trial_expirations():
    """
    Runs daily. Deactivates tenants whose trial + grace period has expired and sends
    warning emails to tenants whose trial expires soon.
    
    Timeline:
    - 7 days before trial_end: warning email
    - 3 days before trial_end: warning email  
    - trial_end_date: trial expires (grace period starts)
    - trial_end_date + GRACE_PERIOD: tenant deactivated
    """
    today = timezone.now().date()
    deactivation_cutoff = today - timezone.timedelta(days=TRIAL_GRACE_PERIOD_DAYS)

    # ── Deactivate trials past grace period ─────────────────────────────
    # Only deactivate if trial_end_date + grace_period has passed
    expired_tenants = list(Tenant.objects.filter(
        is_trial=True,
        is_active=True,
        trial_end_date__lt=deactivation_cutoff,
    ).values_list('id', 'name', 'subdomain', 'email'))
    
    if expired_tenants:
        expired_ids = [t[0] for t in expired_tenants]
        count = Tenant.objects.filter(id__in=expired_ids).update(is_active=False)
        
        # Log each deactivated tenant
        for tenant_id, name, subdomain, email in expired_tenants:
            logger.warning(
                "Trial expired: deactivated tenant '%s' (subdomain=%s, email=%s)",
                name, subdomain, email
            )
        
        # Notify super admin
        _notify_super_admin_deactivations(expired_tenants)
    else:
        count = 0

    # ── Warn tenants expiring soon ──────────────────────────────────────
    from apps.tenants.emails import send_trial_expiry_warning_email

    for days in (7, 3, 1, 0):  # Added day 1 and day 0 (expiry day) warnings
        target_date = today + timezone.timedelta(days=days)
        tenants = Tenant.objects.filter(
            is_trial=True,
            is_active=True,
            trial_end_date=target_date,
        )
        for tenant in tenants:
            try:
                send_trial_expiry_warning_email(tenant, days_left=days)
                logger.info("Sent trial expiry warning to %s (%d days left)", tenant.subdomain, days)
            except Exception as e:
                logger.error("Failed to send trial warning to %s: %s", tenant.subdomain, e)

    return f"Deactivated {count} tenant(s). Sent warnings for 7d, 3d, 1d, 0d."


def _notify_super_admin_deactivations(deactivated_tenants):
    """Send email to super admin about deactivated tenants."""
    if not deactivated_tenants:
        return
    
    try:
        tenant_list = "\n".join([
            f"  - {name} ({subdomain}.learnpuddle.com) - {email}"
            for _, name, subdomain, email in deactivated_tenants
        ])
        
        subject = f"[LearnPuddle] {len(deactivated_tenants)} tenant(s) deactivated due to trial expiration"
        message = f"""The following tenants have been deactivated because their trial period (plus {TRIAL_GRACE_PERIOD_DAYS}-day grace period) has expired:

{tenant_list}

These tenants can no longer access the platform until reactivated.

To reactivate a tenant:
1. Log in to the Super Admin dashboard
2. Navigate to Schools > [School Name]
3. Toggle "Active" to ON and optionally extend the trial or upgrade their plan

---
LearnPuddle LMS
"""
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@learnpuddle.com')
        admin_email = getattr(settings, 'SUPER_ADMIN_EMAIL', None)
        
        if admin_email:
            send_mail(subject, message, from_email, [admin_email], fail_silently=True)
            logger.info("Sent deactivation notification to super admin: %s", admin_email)
        else:
            logger.warning("SUPER_ADMIN_EMAIL not configured; skipping deactivation notification")
    except Exception as e:
        logger.error("Failed to notify super admin of deactivations: %s", e)
