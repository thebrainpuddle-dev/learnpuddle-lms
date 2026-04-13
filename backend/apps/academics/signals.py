# apps/academics/signals.py
"""
Course auto-assignment signals for the academic structure.

Three triggers:
1. Student section change  → assign courses targeting that section
2. Course publish          → populate assigned_students from targets
3. Course target M2M change → re-populate students (connected in apps.py)

All handlers are idempotent — M2M .add() is a no-op for existing entries.
"""

import logging

from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ─── 1. Student section/grade change → reassign courses ─────────────────────

@receiver(post_save, sender='users.User')
def on_student_section_change(sender, instance, **kwargs):
    """
    When a student's section_fk changes, auto-assign published academic
    courses that target the new section.

    Only fires for:
    - STUDENT role
    - New students created with a section_fk
    - Existing students with save(update_fields=['section_fk', ...])

    Does NOT fire on generic save() without update_fields to avoid
    running on every unrelated user update.
    """
    if instance.role != 'STUDENT':
        return

    update_fields = kwargs.get('update_fields')
    created = kwargs.get('created', False)

    if not created and update_fields is None:
        # Full save() without update_fields — skip
        return

    if update_fields and 'section_fk' not in update_fields and 'grade_fk' not in update_fields:
        return

    if not instance.section_fk_id:
        return

    from apps.academics.services import reassign_student_courses
    reassign_student_courses(instance)


# ─── 2. Course publish → populate assigned_students ──────────────────────────

@receiver(post_save, sender='courses.Course')
def on_course_publish(sender, instance, **kwargs):
    """
    When an ACADEMIC course transitions to is_published=True,
    auto-assign students based on target_sections or target_grades.
    """
    if instance.course_type != 'ACADEMIC':
        return

    if not instance.is_published or not instance.is_active:
        return

    update_fields = kwargs.get('update_fields')
    created = kwargs.get('created', False)

    should_assign = False
    if created and instance.is_published:
        should_assign = True
    elif update_fields and 'is_published' in update_fields:
        should_assign = True

    if not should_assign:
        return

    from apps.academics.services import auto_assign_course_students
    count = auto_assign_course_students(instance)
    if count:
        logger.info(
            "Signal: auto-assigned %d students on publish for '%s'",
            count, instance.title,
        )


# ─── 3. Course target M2M change → re-populate students ─────────────────────
# Connected programmatically in AcademicsConfig.ready() because
# m2m_changed requires the actual through-model class, not a string.

def on_course_targets_changed(sender, instance, action, **kwargs):
    """
    When target_sections or target_grades are added to a published
    ACADEMIC course, auto-assign students from the new targets.

    Only fires on post_add (additive, never removes).
    """
    if action != 'post_add':
        return

    if instance.course_type != 'ACADEMIC':
        return

    if not instance.is_published or not instance.is_active:
        return

    from apps.academics.services import auto_assign_course_students
    count = auto_assign_course_students(instance)
    if count:
        logger.info(
            "Signal: auto-assigned %d students after M2M change on '%s'",
            count, instance.title,
        )
