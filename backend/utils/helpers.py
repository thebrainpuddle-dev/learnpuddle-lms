"""
Shared helpers extracted from duplicated patterns across the codebase.

This module centralises:
  - ``make_pagination_class``  -- factory for ``PageNumberPagination`` subclasses
  - ``tenant_teachers_qs``     -- active teachers for a tenant
  - ``course_assigned_teachers``-- teachers assigned to a course
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from rest_framework.pagination import PageNumberPagination

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from apps.courses.models import Course
    from apps.tenants.models import Tenant


# ---------------------------------------------------------------------------
# 1. Pagination factory
# ---------------------------------------------------------------------------

def make_pagination_class(
    page_size: int = 20,
    max_page_size: int = 100,
    page_size_query_param: str = "page_size",
) -> type[PageNumberPagination]:
    """Return a ``PageNumberPagination`` subclass with the given defaults.

    Eliminates the need to define near-identical pagination classes in every
    app.  Usage::

        from utils.helpers import make_pagination_class

        MyPagination = make_pagination_class(page_size=50, max_page_size=200)
    """
    return type(
        "DynamicPagination",
        (PageNumberPagination,),
        {
            "page_size": page_size,
            "page_size_query_param": page_size_query_param,
            "max_page_size": max_page_size,
        },
    )


# ---------------------------------------------------------------------------
# 2. Tenant-scoped teacher queries
# ---------------------------------------------------------------------------

_TEACHER_ROLES = ("TEACHER", "HOD", "IB_COORDINATOR")


def tenant_teachers_qs(tenant: "Tenant") -> "QuerySet":
    """Return active teachers (non-admin) for *tenant*.

    Previously duplicated in:
      - ``apps/reports/views._tenant_teachers_qs``
      - ``apps/reminders/services.tenant_teachers_qs``
      - inline filters in ``apps/notifications/views.py``
    """
    from apps.users.models import User

    return User.objects.all_tenants().filter(
        tenant=tenant,
        role__in=_TEACHER_ROLES,
        is_active=True,
    )


def tenant_students_qs(tenant: "Tenant") -> "QuerySet":
    """Return active students for *tenant*."""
    from apps.users.models import User

    return User.objects.all_tenants().filter(
        tenant=tenant,
        role="STUDENT",
        is_active=True,
    )


def course_assigned_teachers(course: "Course") -> "QuerySet":
    """Return the queryset of teachers assigned to *course*.

    Handles ``assigned_to_all``, explicit assignment, and group membership.

    Previously duplicated in:
      - ``apps/reports/views._course_assigned_teachers``
      - ``apps/reminders/services.course_assigned_teachers``
    """
    teachers = tenant_teachers_qs(course.tenant)
    if course.assigned_to_all:
        return teachers
    return teachers.filter(
        models.Q(teacher_groups__in=course.assigned_groups.all())
        | models.Q(assigned_courses=course)
    ).distinct()


def course_assigned_students(course: "Course") -> "QuerySet":
    """Return the queryset of students assigned to *course*.

    Handles ``assigned_to_all_students`` and explicit ``assigned_students``.
    """
    students = tenant_students_qs(course.tenant)
    if course.assigned_to_all_students:
        return students
    return students.filter(student_assigned_courses=course).distinct()
