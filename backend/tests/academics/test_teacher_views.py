# tests/academics/test_teacher_views.py
"""
Tests for the academics teacher API endpoints.

Covers:
- GET /api/v1/teacher/academics/my-classes/
- GET /api/v1/teacher/academics/sections/{id}/dashboard/?tab=students|courses|analytics|assignments

Auth & access control:
- Teacher with valid teaching assignment can access
- Teacher without assignment is denied section dashboard
- Admin can access teacher endpoints (teacher_or_admin)
- Unauthenticated requests are rejected
- Student role is denied
"""

import uuid

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academics.models import Section, TeachingAssignment


BASE = "/api/v1/teacher/academics"


# ═══════════════════════════════════════════════════════════════════════════
# My Classes
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMyClasses:
    """GET /api/v1/teacher/academics/my-classes/"""

    def test_returns_assignments(self, teacher_client, teaching_assignment):
        response = teacher_client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_200_OK
        assert "assignments" in response.data
        assert "academic_year" in response.data
        assert "total_sections" in response.data
        assert len(response.data["assignments"]) >= 1

    def test_assignment_contains_subject_info(self, teacher_client, teaching_assignment, subject):
        response = teacher_client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_200_OK
        first_assignment = response.data["assignments"][0]
        assert "subject" in first_assignment
        assert first_assignment["subject"]["name"] == subject.name
        assert first_assignment["subject"]["code"] == subject.code

    def test_assignment_contains_sections(self, teacher_client, teaching_assignment, section):
        response = teacher_client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_200_OK
        first_assignment = response.data["assignments"][0]
        assert len(first_assignment["sections"]) >= 1
        section_data = first_assignment["sections"][0]
        assert "student_count" in section_data
        assert "course_count" in section_data
        assert "grade_name" in section_data
        assert "grade_band_name" in section_data

    def test_section_student_count(
        self, teacher_client, teaching_assignment, section, student_user,
    ):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = teacher_client.get(f"{BASE}/my-classes/")
        first_section = response.data["assignments"][0]["sections"][0]
        assert first_section["student_count"] >= 1

    def test_admin_can_access(self, admin_client, tenant, teacher_user, teaching_assignment):
        """my_classes uses @teacher_or_admin; admin should get their own assignments (likely empty)."""
        response = admin_client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_200_OK
        # Admin has no teaching assignments of their own, so assignments list is empty.
        assert "assignments" in response.data

    def test_requires_auth(self, api_client):
        response = api_client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_cannot_access(self, tenant, student_user):
        client = APIClient()
        client.force_authenticate(user=student_user)
        client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
        response = client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_with_no_assignments_gets_empty(self, tenant):
        """A teacher with no teaching assignments gets an empty list."""
        from apps.users.models import User

        lonely_teacher = User.objects.create_user(
            email="lonely@academics-test.com",
            password="Pass!123",
            first_name="Lonely",
            last_name="Teacher",
            tenant=tenant,
            role="TEACHER",
            is_active=True,
        )
        client = APIClient()
        client.force_authenticate(user=lonely_teacher)
        client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
        response = client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["assignments"]) == 0
        assert response.data["total_sections"] == 0

    def test_multiple_assignments(self, teacher_client, tenant, teacher_user, section, teaching_assignment):
        """Teacher with multiple subject assignments sees all of them."""
        from apps.academics.models import Subject

        subject2 = Subject.objects.create(
            tenant=tenant, name="English", code="ENG2", department="Languages",
        )
        ta2 = TeachingAssignment.objects.create(
            tenant=tenant, teacher=teacher_user, subject=subject2,
            academic_year="2026-27",
        )
        ta2.sections.add(section)

        response = teacher_client.get(f"{BASE}/my-classes/")
        assert response.status_code == status.HTTP_200_OK
        # Fixture assignment + the one we just created
        assert len(response.data["assignments"]) >= 2


# ═══════════════════════════════════════════════════════════════════════════
# Section Dashboard — Students Tab
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionDashboardStudents:
    """GET /api/v1/teacher/academics/sections/{id}/dashboard/?tab=students"""

    def test_students_tab(self, teacher_client, section, teaching_assignment):
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "students"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["tab"] == "students"
        assert "students" in response.data
        assert "total" in response.data
        assert "section" in response.data

    def test_students_tab_with_data(
        self, teacher_client, section, teaching_assignment, student_user,
    ):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "students"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] >= 1
        student_data = response.data["students"][0]
        assert "first_name" in student_data
        assert "last_name" in student_data
        assert "email" in student_data

    def test_students_tab_default(self, teacher_client, section, teaching_assignment):
        """Default tab should be 'students' when no tab param is given."""
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["tab"] == "students"

    def test_students_search(
        self, teacher_client, section, teaching_assignment, student_user,
    ):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "students", "search": student_user.first_name},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] >= 1

    def test_students_search_no_match(
        self, teacher_client, section, teaching_assignment, student_user,
    ):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "students", "search": "ZZZNONEXISTENT"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Section Dashboard — Courses Tab
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionDashboardCourses:
    """GET /api/v1/teacher/academics/sections/{id}/dashboard/?tab=courses"""

    def test_courses_tab(self, teacher_client, section, teaching_assignment):
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "courses"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["tab"] == "courses"
        assert "courses" in response.data
        assert "total" in response.data

    def test_courses_tab_with_course(
        self, teacher_client, section, teaching_assignment, tenant, teacher_user,
    ):
        from apps.courses.models import Course

        course = Course.objects.create(
            tenant=tenant, title="Teacher Course", course_type="ACADEMIC",
            created_by=teacher_user,
        )
        course.target_sections.add(section)
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "courses"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] >= 1
        course_data = response.data["courses"][0]
        assert "title" in course_data
        assert "is_published" in course_data

    def test_teacher_sees_only_own_courses(
        self, teacher_client, section, teaching_assignment, tenant, admin_user, teacher_user,
    ):
        """Teacher should only see courses they created, not admin's courses."""
        from apps.courses.models import Course

        admin_course = Course.objects.create(
            tenant=tenant, title="Admin Course", course_type="ACADEMIC",
            created_by=admin_user,
        )
        admin_course.target_sections.add(section)

        teacher_course = Course.objects.create(
            tenant=tenant, title="My Course", course_type="ACADEMIC",
            created_by=teacher_user,
        )
        teacher_course.target_sections.add(section)

        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "courses"},
        )
        assert response.status_code == status.HTTP_200_OK
        titles = [c["title"] for c in response.data["courses"]]
        assert "My Course" in titles
        assert "Admin Course" not in titles

    def test_admin_sees_all_courses(
        self, admin_client, section, tenant, admin_user, teacher_user,
    ):
        """Admin should see all courses for the section."""
        from apps.courses.models import Course

        admin_course = Course.objects.create(
            tenant=tenant, title="Admin Course", course_type="ACADEMIC",
            created_by=admin_user,
        )
        admin_course.target_sections.add(section)

        teacher_course = Course.objects.create(
            tenant=tenant, title="Teacher Course", course_type="ACADEMIC",
            created_by=teacher_user,
        )
        teacher_course.target_sections.add(section)

        response = admin_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "courses"},
        )
        assert response.status_code == status.HTTP_200_OK
        titles = [c["title"] for c in response.data["courses"]]
        assert "Admin Course" in titles
        assert "Teacher Course" in titles


# ═══════════════════════════════════════════════════════════════════════════
# Section Dashboard — Analytics Tab
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionDashboardAnalytics:
    """GET /api/v1/teacher/academics/sections/{id}/dashboard/?tab=analytics"""

    def test_analytics_tab(self, teacher_client, section, teaching_assignment):
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "analytics"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["tab"] == "analytics"
        assert "stats" in response.data
        stats = response.data["stats"]
        assert "total_students" in stats
        assert "active_students_7d" in stats
        assert "inactive_students" in stats
        assert "total_courses" in stats

    def test_analytics_with_students(
        self, teacher_client, section, teaching_assignment, student_user,
    ):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "analytics"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["stats"]["total_students"] >= 1

    def test_analytics_inactive_count(
        self, teacher_client, section, teaching_assignment, student_user,
    ):
        """A student with no recent login should appear in inactive count."""
        student_user.section_fk = section
        student_user.last_login = None
        student_user.save(update_fields=["section_fk", "last_login"])
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "analytics"},
        )
        assert response.status_code == status.HTTP_200_OK
        stats = response.data["stats"]
        assert stats["inactive_students"] >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Section Dashboard — Assignments Tab
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionDashboardAssignments:
    """GET /api/v1/teacher/academics/sections/{id}/dashboard/?tab=assignments"""

    def test_assignments_tab(self, teacher_client, section, teaching_assignment):
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "assignments"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["tab"] == "assignments"
        assert "assignments" in response.data
        assert "total" in response.data

    def test_assignments_tab_empty(self, teacher_client, section, teaching_assignment):
        """With no courses/assignments, should return empty list gracefully."""
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "assignments"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Section Dashboard — Invalid Tab
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionDashboardInvalidTab:
    """GET /api/v1/teacher/academics/sections/{id}/dashboard/?tab=invalid"""

    def test_invalid_tab_returns_error(self, teacher_client, section, teaching_assignment):
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "nonexistent"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid tab" in response.data["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Section Dashboard — Access Control
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionDashboardAccess:
    """Access control for section dashboard."""

    def test_requires_auth(self, api_client, section):
        response = api_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_cannot_access(self, tenant, section, student_user):
        client = APIClient()
        client.force_authenticate(user=student_user)
        client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
        response = client.get(f"{BASE}/sections/{section.id}/dashboard/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_without_assignment_denied(self, tenant, section):
        """A teacher with no assignment to this section is denied."""
        from apps.users.models import User

        other_teacher = User.objects.create_user(
            email="other-teacher@academics-test.com",
            password="Pass!123",
            first_name="Other",
            last_name="Teacher",
            tenant=tenant,
            role="TEACHER",
            is_active=True,
        )
        client = APIClient()
        client.force_authenticate(user=other_teacher)
        client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
        response = client.get(f"{BASE}/sections/{section.id}/dashboard/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_access_without_assignment(self, admin_client, section):
        """Admin can access any section dashboard without a teaching assignment."""
        response = admin_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "students"},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_nonexistent_section(self, teacher_client):
        fake_id = uuid.uuid4()
        response = teacher_client.get(
            f"{BASE}/sections/{fake_id}/dashboard/",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_section_info_in_response(self, teacher_client, section, teaching_assignment):
        response = teacher_client.get(
            f"{BASE}/sections/{section.id}/dashboard/",
            {"tab": "students"},
        )
        assert response.status_code == status.HTTP_200_OK
        section_info = response.data["section"]
        assert section_info["id"] == str(section.id)
        assert section_info["name"] == section.name
        assert "grade_name" in section_info
        assert "grade_band_name" in section_info
        assert "academic_year" in section_info
