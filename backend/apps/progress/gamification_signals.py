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
        from .models import QuizSubmission, TeacherProgress as TP

        course = instance.course
        total_content = Content.objects.filter(
            module__course=course, is_active=True,
        ).count()
        has_course_assessment_activity = QuizSubmission.all_objects.filter(
            teacher=teacher,
            quiz__assignment__course=course,
        ).exists()
        if total_content > 1 or has_course_assessment_activity:
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
                    # TASK-018: course-level mastery bonus when avg quiz
                    # score meets the threshold.
                    try:
                        from .mastery_engine import award_course_mastery_bonus

                        award_course_mastery_bonus(teacher, course)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "award_course_mastery_bonus failed for "
                            "course %s, teacher %s",
                            instance.course_id, teacher.id,
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
    """Award XP when a teacher completes (submits) a quiz attempt.

    With multiple-attempt support, a QuizSubmission row is created when the
    teacher opens the quiz (score IS NULL, in-progress).  XP must only be
    awarded once the teacher actually submits answers (score IS NOT NULL).

    We guard against double-award using XPTransaction deduplication keyed on
    instance.id, so re-saves (e.g. admin manual grade) do not earn extra XP.
    """
    # Skip in-progress attempts — score is set only when quiz is submitted.
    if instance.score is None:
        return

    # Skip abandoned timed attempts.  quiz_helpers.start_quiz_attempt() closes
    # out an expired in-progress row by setting time_expired=True, score=0.
    # The teacher did not submit answers — do not award XP.  Guard runs BEFORE
    # dedup lookup so we don't record a zero-XP transaction either.
    # NOTE: only the XP-engine side-effects in THIS receiver are skipped
    # (award_xp / update_streak / mastery bonus).  Notification, leaderboard,
    # and admin-grade side-effects live in other signals/handlers and still
    # fire — the QuizSubmission row itself is real and persisted.
    if getattr(instance, 'time_expired', False) and instance.score in (None, 0):
        logger.info(
            "Skipping XP for abandoned timed quiz attempt id=%s",
            instance.pk,
            extra={
                "metric": "quiz_xp_skipped_on_timeout",
                "attempt_id": str(instance.pk),
                "quiz_id": str(getattr(instance, 'quiz_id', '') or ''),
                "teacher_id": str(getattr(instance, 'teacher_id', '') or ''),
                "tenant_id": str(getattr(instance, 'tenant_id', '') or ''),
                "attempt_number": getattr(instance, 'attempt_number', None),
            },
        )
        return

    teacher = instance.teacher
    tenant = instance.tenant or getattr(teacher, 'tenant', None)
    if not tenant:
        logger.debug(
            "on_quiz_submission: no tenant for QuizSubmission %s — skipping",
            instance.id,
        )
        return

    # Deduplicate: only award XP once per submission row (instance.id).
    from .gamification_models import XPTransaction

    already_awarded = XPTransaction.all_objects.filter(
        teacher=teacher,
        reason='quiz_submission',
        reference_id=instance.id,
        reference_type='quiz_submission',
    ).exists()
    if already_awarded:
        return

    from .gamification_engine import award_xp, update_streak

    award_xp(
        teacher=teacher,
        reason='quiz_submission',
        reference_id=instance.id,
        reference_type='quiz_submission',
        description=f'Completed quiz (attempt {instance.attempt_number})',
    )
    update_streak(teacher, tenant)

    # TASK-018: Mastery Points for quiz scores above the configured threshold.
    # The engine is defensive (catches duplicate / opt-out / inactive) so we
    # invoke it unconditionally here and never let an MP failure break XP.
    try:
        from .mastery_engine import award_quiz_mastery

        award_quiz_mastery(instance)
    except Exception:  # noqa: BLE001 — MP errors must not break XP path
        logger.exception(
            "award_quiz_mastery failed for QuizSubmission %s", instance.id,
        )


@receiver(post_save, sender='progress.AssignmentSubmission')
def on_assignment_submission_mastery(sender, instance, created, **kwargs):
    """
    Award Mastery Points when an AssignmentSubmission transitions to
    GRADED with a passing score. Separate from the XP signal because MP
    fires on re-saves (grade changes) whereas XP fires once on creation.
    """
    if instance.status != 'GRADED' or instance.score is None:
        return
    try:
        from .mastery_engine import award_assignment_mastery

        award_assignment_mastery(instance)
    except Exception:  # noqa: BLE001
        logger.exception(
            "award_assignment_mastery failed for AssignmentSubmission %s",
            instance.id,
        )
