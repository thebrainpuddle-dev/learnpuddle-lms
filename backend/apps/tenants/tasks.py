# apps/tenants/tasks.py
"""
Periodic Celery tasks for tenant lifecycle management.
"""

from celery import shared_task
from django.utils import timezone

from apps.tenants.models import Tenant


@shared_task(name="tenants.check_trial_expirations")
def check_trial_expirations():
    """
    Runs daily. Deactivates tenants whose trial has expired and sends
    warning emails to tenants whose trial expires in 3 or 7 days.
    """
    today = timezone.now().date()

    # ── Expire overdue trials ──────────────────────────────────────────
    expired = Tenant.objects.filter(
        is_trial=True,
        is_active=True,
        trial_end_date__lt=today,
    )
    count = expired.update(is_active=False)
    if count:
        # Log or notify super admin
        pass

    # ── Warn tenants expiring in 7 or 3 days ──────────────────────────
    from apps.tenants.emails import send_trial_expiry_warning_email

    for days in (7, 3):
        target_date = today + timezone.timedelta(days=days)
        tenants = Tenant.objects.filter(
            is_trial=True,
            is_active=True,
            trial_end_date=target_date,
        )
        for tenant in tenants:
            try:
                send_trial_expiry_warning_email(tenant, days_left=days)
            except Exception:
                pass  # best effort

    return f"Expired {count} tenant(s). Checked warnings for 7d and 3d."
