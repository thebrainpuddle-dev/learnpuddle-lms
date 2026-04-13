# apps/progress/tasks.py

import logging
from datetime import timedelta

from celery import shared_task
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="progress.check_certification_expiry_and_autorenew")
def check_certification_expiry_and_autorenew():
    """
    Periodic Celery task that:
    1. Marks expired certifications (active -> expired).
    2. Auto-renews certifications where certification_type.auto_renew is True
       and all required courses have been completed by the teacher.
    3. Sets certifications expiring within 14 days to 'pending_renewal' status.

    Returns a summary dict.
    """
    from apps.progress.certification_models import TeacherCertification
    from apps.progress.completion_metrics import build_teacher_course_snapshots

    now = timezone.now()
    summary = {"expired": 0, "auto_renewed": 0, "pending_renewal": 0}
    renewed_ids = []

    # 1. Find certifications that are active but past their expiry date
    expired_certs = TeacherCertification.all_objects.filter(
        status='active',
        expires_at__lte=now,
    ).select_related('certification_type', 'teacher')

    for tc in expired_certs:
        try:
            cert_type = tc.certification_type

            if cert_type.auto_renew:
                # Check if teacher completed all required courses
                required_courses = list(cert_type.required_courses.all())
                can_renew = True

                if required_courses:
                    course_ids = [c.id for c in required_courses]
                    snapshots = build_teacher_course_snapshots(course_ids, [tc.teacher_id])
                    for course in required_courses:
                        key = (str(course.id), str(tc.teacher_id))
                        snapshot = snapshots.get(key)
                        if not snapshot or snapshot.status != 'COMPLETED':
                            can_renew = False
                            break

                if can_renew:
                    with transaction.atomic():
                        tc.expires_at = now + relativedelta(months=cert_type.validity_months)
                        tc.status = 'active'
                        tc.renewal_count += 1
                        tc.save(update_fields=['expires_at', 'status', 'renewal_count', 'updated_at'])
                    renewed_ids.append(tc.id)
                    summary["auto_renewed"] += 1
                    logger.info(
                        "Auto-renewed certification: cert=%s teacher=%s cert_type=%s",
                        tc.id, tc.teacher.email, cert_type.name,
                    )
                    continue

            # Not auto-renewable or requirements not met: mark as expired
            tc.status = 'expired'
            tc.save(update_fields=['status', 'updated_at'])
            summary["expired"] += 1
        except Exception:
            logger.exception(
                "Error processing certification cert=%s teacher=%s",
                tc.id, getattr(tc, 'teacher_id', None),
            )
            continue

    # 2. Mark certifications expiring within 14 days as pending_renewal
    #    Exclude just-renewed certs so they are not immediately set to pending_renewal
    pending_threshold = now + timedelta(days=14)
    pending_certs = TeacherCertification.all_objects.filter(
        status='active',
        expires_at__gt=now,
        expires_at__lte=pending_threshold,
    )
    if renewed_ids:
        pending_certs = pending_certs.exclude(id__in=renewed_ids)
    updated_count = pending_certs.update(status='pending_renewal')
    summary["pending_renewal"] = updated_count

    logger.info("Certification expiry check complete: %s", summary)
    return summary
