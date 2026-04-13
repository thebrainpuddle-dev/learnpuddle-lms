"""
Signals that connect learning activities to the XP engine.

Connect these in the AppConfig.ready() method of the progress app.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='progress.TeacherProgress')
def on_teacher_progress_save(sender, instance, created, **kwargs):
    """Award XP when a teacher completes content or a course."""
    # Only award on status change to COMPLETED
    if instance.status != 'COMPLETED':
        return

    # Avoid duplicate awards — check if XP already given for this reference.
    # Use all_objects (not objects / TenantManager) for cross-tenant visibility.
    from .gamification_models import XPTransaction

    teacher = instance.teacher
    tenant = instance.tenant or getattr(teacher, 'tenant', None)
    if not tenant:
        logger.debug(
            "on_teacher_progress_save: no tenant for TeacherProgress %s — skipping",
            instance.id,
        )
        return

    if instance.content_id:
        # Content completion
        already_awarded = XPTransaction.all_objects.filter(
            teacher=teacher,
            reason='content_completion',
            reference_id=instance.content_id,
            reference_type='content',
        ).exists()
        if not already_awarded:
            from .gamification_engine import award_xp, update_streak

            award_xp(
                teacher=teacher,
                reason='content_completion',
                reference_id=instance.content_id,
                reference_type='content',
                description=f'Completed content in {instance.course}',
            )
            update_streak(teacher, tenant)

    # Check if entire course is now complete
    if instance.content_id:
        from apps.courses.models import Content
        from .models import TeacherProgress as TP

        course = instance.course
        total_content = Content.objects.filter(
            module__course=course, is_active=True,
        ).count()
        if total_content > 0:
            completed_content = TP.all_objects.filter(
                teacher=teacher,
                course=course,
                content__isnull=False,
                status='COMPLETED',
            ).count()
            if completed_content >= total_content:
                already_awarded = XPTransaction.all_objects.filter(
                    teacher=teacher,
                    reason='course_completion',
                    reference_id=instance.course_id,
                    reference_type='course',
                ).exists()
                if not already_awarded:
                    from .gamification_engine import award_xp

                    award_xp(
                        teacher=teacher,
                        reason='course_completion',
                        reference_id=instance.course_id,
                        reference_type='course',
                        description=f'Completed course: {course}',
                    )


@receiver(post_save, sender='progress.AssignmentSubmission')
def on_assignment_submission(sender, instance, created, **kwargs):
    """Award XP when a teacher submits an assignment."""
    if not created:
        return
    if instance.status not in ('SUBMITTED', 'GRADED'):
        return

    teacher = instance.teacher
    tenant = instance.tenant or getattr(teacher, 'tenant', None)
    if not tenant:
        logger.debug(
            "on_assignment_submission: no tenant for AssignmentSubmission %s — skipping",
            instance.id,
        )
        return

    from .gamification_engine import award_xp, update_streak

    award_xp(
        teacher=teacher,
        reason='assignment_submission',
        reference_id=instance.id,
        reference_type='assignment_submission',
        description=f'Submitted assignment: {instance.assignment.title}',
    )
    update_streak(teacher, tenant)


@receiver(post_save, sender='progress.QuizSubmission')
def on_quiz_submission(sender, instance, created, **kwargs):
    """Award XP when a teacher submits a quiz."""
    if not created:
        return

    teacher = instance.teacher
    tenant = instance.tenant or getattr(teacher, 'tenant', None)
    if not tenant:
        logger.debug(
            "on_quiz_submission: no tenant for QuizSubmission %s — skipping",
            instance.id,
        )
        return

    from .gamification_engine import award_xp, update_streak

    award_xp(
        teacher=teacher,
        reason='quiz_submission',
        reference_id=instance.id,
        reference_type='quiz_submission',
        description='Completed quiz',
    )
    update_streak(teacher, tenant)
