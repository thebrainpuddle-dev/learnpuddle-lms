from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.courses.maic_models import MAICClassroom

from .models import AIQuotaReservation, OpenMAICJob
from .services import AIQuotaError, transition_reservation


@shared_task(name="ai_classroom.reconcile_stale_openmaic_jobs")
def reconcile_stale_openmaic_jobs() -> int:
    """Fail abandoned jobs without replaying an uncertain provider request."""
    cutoff = timezone.now() - timedelta(hours=2)
    stale = OpenMAICJob.all_objects.filter(
        status__in=["queued", "running"],
        updated_at__lt=cutoff,
    ).select_related("classroom")
    reconciled = 0
    for candidate in stale.iterator():
        with transaction.atomic():
            job = OpenMAICJob.all_objects.select_for_update().get(id=candidate.id)
            if job.status not in {"queued", "running"} or job.updated_at >= cutoff:
                continue
            job.status = "failed"
            job.error = "Generation worker stopped before a durable completion callback"
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error", "completed_at", "updated_at"])
            try:
                transition_reservation(job, "released")
            except (AIQuotaError, AIQuotaReservation.DoesNotExist):
                pass
            if job.classroom_id:
                MAICClassroom.all_objects.filter(id=job.classroom_id).update(
                    status="FAILED",
                    error_message=job.error,
                    updated_at=timezone.now(),
                )
            reconciled += 1
    return reconciled
