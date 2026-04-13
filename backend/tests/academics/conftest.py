# tests/academics/conftest.py
"""
Pytest fixtures for the academics app test suite.

Provides reusable fixtures for:
- Tenant with academic-structure fields (id_prefix, counters, academic year)
- Users across all relevant roles (admin, teacher, student)
- Full academic hierarchy: GradeBand -> Grade -> Section
- Subject and TeachingAssignment linking
- Pre-authenticated API clients
"""

import pytest
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.academics.models import GradeBand, Grade, Section, Subject, TeachingAssignment


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant(db):
    """An active ENTERPRISE tenant with academic-structure fields populated."""
    return Tenant.objects.create(
        name="Test School",
        slug="test-school-academics",
        subdomain="test",
        email="academics@testschool.com",
        plan="ENTERPRISE",
        is_active=True,
        current_academic_year="2026-27",
        id_prefix="TST",
        student_id_counter=1,
        teacher_id_counter=1,
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db, tenant):
    """A SCHOOL_ADMIN user belonging to the test tenant."""
    return User.objects.create_user(
        email="admin@academics-test.com",
        password="AdminPass!123",
        first_name="Admin",
        last_name="Academics",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


@pytest.fixture
def teacher_user(db, tenant):
    """A TEACHER user belonging to the test tenant."""
    return User.objects.create_user(
        email="teacher@academics-test.com",
        password="TeacherPass!123",
        first_name="Teacher",
        last_name="Academics",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def student_user(db, tenant):
    """A STUDENT user belonging to the test tenant."""
    return User.objects.create_user(
        email="student@academics-test.com",
        password="StudentPass!123",
        first_name="Student",
        last_name="Academics",
        tenant=tenant,
        role="STUDENT",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Academic hierarchy
# ---------------------------------------------------------------------------

@pytest.fixture
def grade_band(db, tenant):
    """A Primary-level GradeBand using CAMBRIDGE_PRIMARY curriculum."""
    return GradeBand.objects.create(
        tenant=tenant,
        name="Primary",
        short_code="PRI",
        order=1,
        curriculum_framework="CAMBRIDGE_PRIMARY",
    )


@pytest.fixture
def grade(db, tenant, grade_band):
    """Grade 5 within the Primary grade band."""
    return Grade.objects.create(
        tenant=tenant,
        grade_band=grade_band,
        name="Grade 5",
        short_code="G5",
        order=5,
    )


@pytest.fixture
def section(db, tenant, grade):
    """Section A of Grade 5 for the 2026-27 academic year."""
    return Section.objects.create(
        tenant=tenant,
        grade=grade,
        name="A",
        academic_year="2026-27",
    )


# ---------------------------------------------------------------------------
# Subject & TeachingAssignment
# ---------------------------------------------------------------------------

@pytest.fixture
def subject(db, tenant):
    """Mathematics subject in the Sciences department."""
    return Subject.objects.create(
        tenant=tenant,
        name="Mathematics",
        code="MATH",
        department="Sciences",
    )


@pytest.fixture
def teaching_assignment(db, tenant, teacher_user, subject, section):
    """
    A TeachingAssignment linking the teacher to Mathematics in Section A
    for academic year 2026-27.
    """
    ta = TeachingAssignment.objects.create(
        tenant=tenant,
        teacher=teacher_user,
        subject=subject,
        academic_year="2026-27",
    )
    ta.sections.add(section)
    return ta


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    """Unauthenticated DRF APIClient."""
    return APIClient()


@pytest.fixture
def admin_client(admin_user, tenant):
    """DRF APIClient pre-authenticated as the SCHOOL_ADMIN user."""
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


@pytest.fixture
def teacher_client(teacher_user, tenant):
    """DRF APIClient pre-authenticated as the TEACHER user."""
    client = APIClient()
    client.force_authenticate(user=teacher_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client
