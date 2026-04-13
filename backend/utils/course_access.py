# utils/course_access.py
"""
Shared helpers for determining whether a user has access to a course.

Centralises the ``_teacher_assigned_to_course`` logic that was previously
duplicated in:
  - apps/courses/teacher_views.py
  - apps/progress/teacher_views.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.courses.models import Course
    from apps.users.models import User


def is_teacher_assigned_to_course(user: "User", course: "Course") -> bool:
    """Return True if *user* has access to *course* as a teacher or admin.

    Access rules (any one is sufficient):
    1. User is SCHOOL_ADMIN or SUPER_ADMIN.
    2. Course is assigned to all teachers (``assigned_to_all=True``).
    3. User is explicitly in ``course.assigned_teachers``.
    4. User belongs to a group that is in ``course.assigned_groups``.
    """
    if user.role in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        return True
    if course.assigned_to_all:
        return True
    if course.assigned_teachers.filter(id=user.id).exists():
        return True
    if course.assigned_groups.filter(
        id__in=user.teacher_groups.values_list("id", flat=True)
    ).exists():
        return True
    return False


def is_student_assigned_to_course(user: "User", course: "Course") -> bool:
    """Return True if *user* has access to *course* as a student or admin.

    Access rules (any one is sufficient):
    1. User is SCHOOL_ADMIN or SUPER_ADMIN.
    2. Course assigns to all students (``assigned_to_all_students=True``).
    3. User is explicitly in ``course.assigned_students``.
    """
    if user.role in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        return True
    if course.assigned_to_all_students:
        return True
    if course.assigned_students.filter(id=user.id).exists():
        return True
    return False
