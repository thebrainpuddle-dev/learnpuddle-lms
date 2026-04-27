"""
Signal wiring for the daily/weekly challenge system (TASK-017).

Connected in ``ProgressConfig.ready()``.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="progress.TeacherProgress")
def on_progress_bump_challenges(sender, instance, created, **kwargs):
    """Advance ``complete_lessons`` and ``finish_course`` challenges."""
    if instance.status != "COMPLETED":
        return

    teacher = instance.teacher
    tenant = instance.tenant or getattr(teacher, "tenant", None)
    if not tenant:
        return

    from .challenge_engine import record_event

    # Only count per-content completions — a parent "course-level" row
    # (content is NULL) is a different row we don't count as a lesson.
    if instance.content_id:
        record_event(
            teacher=teacher,
            event_type="content_completion",
            reference_id=instance.content_id,
            reference_type="content",
            amount=1,
        )

    # If whole course done, fire course_completion once per course.
    if instance.content_id:
        from apps.courses.models import Content
        from .models import TeacherProgress as TP

        course = instance.course
        total = Content.objects.filter(module__course=course, is_active=True).count()
        if total > 0:
            done = TP.all_objects.filter(
                teacher=teacher, course=course,
                content__isnull=False, status="COMPLETED",
            ).count()
            if done >= total:
                record_event(
                    teacher=teacher,
                    event_type="course_completion",
                    reference_id=course.id,
                    reference_type="course",
                    amount=1,
                )


@receiver(post_save, sender="progress.AssignmentSubmission")
def on_assignment_bump_challenges(sender, instance, created, **kwargs):
    """Advance ``submit_assignments`` challenges on new submissions."""
    if not created:
        return
    if instance.status not in ("SUBMITTED", "GRADED"):
        return

    teacher = instance.teacher
    tenant = instance.tenant or getattr(teacher, "tenant", None)
    if not tenant:
        return

    from .challenge_engine import record_event

    record_event(
        teacher=teacher,
        event_type="assignment_submission",
        reference_id=instance.id,
        reference_type="assignment_submission",
        amount=1,
    )
