# tests/test_course_access.py
"""
Tests for utils/course_access.py — access control helpers.

These functions use duck-typed model objects, so we mock them.

Covers:
1. is_teacher_assigned_to_course() — all access paths
2. is_student_assigned_to_course() — all access paths
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import TestCase


# ===========================================================================
# Helpers
# ===========================================================================


def _make_user(role: str, user_id: int = 1) -> MagicMock:
    """Create a mock User with a given role."""
    user = MagicMock()
    user.role = role
    user.id = user_id
    return user


def _make_course(
    assigned_to_all: bool = False,
    assigned_teachers_has: bool = False,
    assigned_groups_has: bool = False,
    assigned_to_all_students: bool = False,
    assigned_students_has: bool = False,
) -> MagicMock:
    """Create a mock Course with configurable access settings."""
    course = MagicMock()
    course.assigned_to_all = assigned_to_all
    course.assigned_to_all_students = assigned_to_all_students

    # assigned_teachers.filter().exists()
    teacher_qs = MagicMock()
    teacher_qs.exists.return_value = assigned_teachers_has
    course.assigned_teachers.filter.return_value = teacher_qs

    # assigned_students.filter().exists()
    student_qs = MagicMock()
    student_qs.exists.return_value = assigned_students_has
    course.assigned_students.filter.return_value = student_qs

    # assigned_groups.filter().exists()
    groups_qs = MagicMock()
    groups_qs.exists.return_value = assigned_groups_has
    course.assigned_groups.filter.return_value = groups_qs

    # user.teacher_groups.values_list()
    return course


# ===========================================================================
# 1. is_teacher_assigned_to_course() Tests
# ===========================================================================


class IsTeacherAssignedToCourseTestCase(TestCase):
    """is_teacher_assigned_to_course() access path tests."""

    def _check(self, user, course) -> bool:
        from utils.course_access import is_teacher_assigned_to_course
        return is_teacher_assigned_to_course(user, course)

    def test_school_admin_always_has_access(self):
        """SCHOOL_ADMIN must always return True regardless of assignment."""
        user = _make_user("SCHOOL_ADMIN")
        course = _make_course(assigned_to_all=False)

        result = self._check(user, course)
        self.assertTrue(
            result,
            "SCHOOL_ADMIN must always have access to any course",
        )

    def test_super_admin_always_has_access(self):
        """SUPER_ADMIN must always return True."""
        user = _make_user("SUPER_ADMIN")
        course = _make_course(assigned_to_all=False)

        result = self._check(user, course)
        self.assertTrue(result, "SUPER_ADMIN must always have access")

    def test_assigned_to_all_grants_access_to_teacher(self):
        """When assigned_to_all=True, any TEACHER must have access."""
        user = _make_user("TEACHER")
        course = _make_course(assigned_to_all=True)

        result = self._check(user, course)
        self.assertTrue(
            result,
            "assigned_to_all=True must grant access to any teacher",
        )

    def test_explicitly_assigned_teacher_has_access(self):
        """A TEACHER explicitly in assigned_teachers must have access."""
        user = _make_user("TEACHER")
        # assigned_to_all=False, but teacher IS in assigned_teachers
        course = _make_course(assigned_teachers_has=True)

        result = self._check(user, course)
        self.assertTrue(
            result,
            "Teacher explicitly assigned to course must have access",
        )

    def test_group_member_teacher_has_access(self):
        """A TEACHER in an assigned group must have access."""
        user = _make_user("TEACHER")
        user.teacher_groups = MagicMock()
        user.teacher_groups.values_list.return_value = [1, 2, 3]
        course = _make_course(assigned_groups_has=True)

        result = self._check(user, course)
        self.assertTrue(
            result,
            "Teacher belonging to an assigned group must have access",
        )

    def test_unassigned_teacher_no_access(self):
        """TEACHER with no assignment must NOT have access."""
        user = _make_user("TEACHER")
        user.teacher_groups = MagicMock()
        user.teacher_groups.values_list.return_value = []
        course = _make_course(
            assigned_to_all=False,
            assigned_teachers_has=False,
            assigned_groups_has=False,
        )

        result = self._check(user, course)
        self.assertFalse(
            result,
            "Unassigned teacher must NOT have access to the course",
        )

    def test_hod_role_follows_same_rules(self):
        """HOD role is not admin, so must follow normal access rules."""
        user = _make_user("HOD")
        user.teacher_groups = MagicMock()
        user.teacher_groups.values_list.return_value = []

        # Assigned to all — should get access
        course_all = _make_course(assigned_to_all=True)
        self.assertTrue(self._check(user, course_all))

        # Not assigned — should not get access
        course_none = _make_course(assigned_to_all=False, assigned_teachers_has=False, assigned_groups_has=False)
        self.assertFalse(self._check(user, course_none))


# ===========================================================================
# 2. is_student_assigned_to_course() Tests
# ===========================================================================


class IsStudentAssignedToCourseTestCase(TestCase):
    """is_student_assigned_to_course() access path tests."""

    def _check(self, user, course) -> bool:
        from utils.course_access import is_student_assigned_to_course
        return is_student_assigned_to_course(user, course)

    def test_school_admin_always_has_access(self):
        """SCHOOL_ADMIN must always return True."""
        user = _make_user("SCHOOL_ADMIN")
        course = _make_course(assigned_to_all_students=False)

        self.assertTrue(self._check(user, course))

    def test_super_admin_always_has_access(self):
        """SUPER_ADMIN must always return True."""
        user = _make_user("SUPER_ADMIN")
        course = _make_course(assigned_to_all_students=False)

        self.assertTrue(self._check(user, course))

    def test_assigned_to_all_students_grants_access(self):
        """When assigned_to_all_students=True, any student must have access."""
        user = _make_user("STUDENT")
        course = _make_course(assigned_to_all_students=True)

        self.assertTrue(
            self._check(user, course),
            "assigned_to_all_students=True must grant access to any student",
        )

    def test_explicitly_assigned_student_has_access(self):
        """Student explicitly in assigned_students must have access."""
        user = _make_user("STUDENT")
        course = _make_course(
            assigned_to_all_students=False,
            assigned_students_has=True,
        )

        self.assertTrue(
            self._check(user, course),
            "Explicitly assigned student must have access",
        )

    def test_unassigned_student_no_access(self):
        """Student with no assignment must NOT have access."""
        user = _make_user("STUDENT")
        course = _make_course(
            assigned_to_all_students=False,
            assigned_students_has=False,
        )

        self.assertFalse(
            self._check(user, course),
            "Unassigned student must NOT have access",
        )
