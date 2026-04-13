# tests/academics/test_admin_views.py
"""
Tests for the academics admin API endpoints.

Covers:
- GradeBand CRUD (list, create, retrieve, update, delete)
- Grade CRUD
- Section CRUD + detail views (students, teachers, courses)
- Subject CRUD
- TeachingAssignment CRUD
- School Overview
- Section add-student / import-students
- Student transfer
- Course cloning
- Promotion preview / execute
- Auth & permission guards (unauthenticated, wrong role, cross-tenant)
"""

import io
import uuid

import pytest
from rest_framework import status

from apps.academics.models import GradeBand, Grade, Section, Subject, TeachingAssignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/academics"


def _csv_file(rows: list[str], filename: str = "students.csv"):
    """Build an in-memory CSV file suitable for DRF's MultiPartParser."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    content = "\n".join(rows).encode("utf-8")
    return SimpleUploadedFile(filename, content, content_type="text/csv")


# ═══════════════════════════════════════════════════════════════════════════
# GradeBand CRUD
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGradeBandList:
    """GET /api/v1/academics/grade-bands/"""

    def test_requires_auth(self, api_client, tenant):
        response = api_client.get(f"{BASE}/grade-bands/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_teacher_cannot_access(self, teacher_client):
        response = teacher_client.get(f"{BASE}/grade-bands/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_returns_grade_bands(self, admin_client, grade_band):
        response = admin_client.get(f"{BASE}/grade-bands/")
        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert "total" in response.data
        assert len(response.data["data"]) >= 1
        names = [b["name"] for b in response.data["data"]]
        assert grade_band.name in names

    def test_includes_grade_count(self, admin_client, grade_band, grade):
        response = admin_client.get(f"{BASE}/grade-bands/")
        assert response.status_code == status.HTTP_200_OK
        band_data = next(b for b in response.data["data"] if str(b["id"]) == str(grade_band.id))
        assert band_data["grade_count"] >= 1

    def test_ordered_by_order_field(self, admin_client, tenant):
        GradeBand.objects.create(tenant=tenant, name="ZZ Last", short_code="ZZ", order=99)
        GradeBand.objects.create(tenant=tenant, name="AA First", short_code="AA", order=0)
        response = admin_client.get(f"{BASE}/grade-bands/")
        orders = [b["order"] for b in response.data["data"]]
        assert orders == sorted(orders)


@pytest.mark.django_db
class TestGradeBandCreate:
    """POST /api/v1/academics/grade-bands/"""

    def test_create_grade_band(self, admin_client, tenant):
        payload = {
            "name": "High School",
            "short_code": "HS",
            "order": 4,
            "curriculum_framework": "IGCSE",
        }
        response = admin_client.post(f"{BASE}/grade-bands/", payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "High School"
        assert response.data["curriculum_framework"] == "IGCSE"
        assert GradeBand.all_objects.filter(tenant=tenant, name="High School").exists()

    def test_teacher_cannot_create(self, teacher_client):
        response = teacher_client.post(f"{BASE}/grade-bands/", {
            "name": "X", "short_code": "X", "order": 1,
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_name_rejected(self, admin_client, grade_band, tenant):
        response = admin_client.post(f"{BASE}/grade-bands/", {
            "name": grade_band.name,
            "short_code": "DUP",
            "order": 10,
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_required_fields(self, admin_client):
        response = admin_client.post(f"{BASE}/grade-bands/", {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestGradeBandDetail:
    """GET/PATCH/DELETE /api/v1/academics/grade-bands/{id}/"""

    def test_retrieve(self, admin_client, grade_band):
        response = admin_client.get(f"{BASE}/grade-bands/{grade_band.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == grade_band.name

    def test_update(self, admin_client, grade_band):
        response = admin_client.patch(
            f"{BASE}/grade-bands/{grade_band.id}/",
            {"name": "Updated Band"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        grade_band.refresh_from_db()
        assert grade_band.name == "Updated Band"

    def test_delete_empty_band(self, admin_client, tenant):
        band = GradeBand.objects.create(
            tenant=tenant, name="Deletable", short_code="DEL", order=99,
        )
        response = admin_client.delete(f"{BASE}/grade-bands/{band.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not GradeBand.all_objects.filter(pk=band.id).exists()

    def test_delete_band_with_grades_rejected(self, admin_client, grade_band, grade):
        response = admin_client.delete(f"{BASE}/grade-bands/{grade_band.id}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "grades" in response.data["error"].lower()

    def test_not_found(self, admin_client):
        fake_id = uuid.uuid4()
        response = admin_client.get(f"{BASE}/grade-bands/{fake_id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ═══════════════════════════════════════════════════════════════════════════
# Grade CRUD
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGradeListCreate:
    """GET/POST /api/v1/academics/grades/"""

    def test_list_grades(self, admin_client, grade):
        response = admin_client.get(f"{BASE}/grades/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_filter_by_grade_band(self, admin_client, grade_band, grade, tenant):
        other_band = GradeBand.objects.create(
            tenant=tenant, name="Other Band", short_code="OB", order=10,
        )
        Grade.objects.create(
            tenant=tenant, grade_band=other_band, name="Other Grade",
            short_code="OG", order=20,
        )
        response = admin_client.get(f"{BASE}/grades/", {"grade_band": str(grade_band.id)})
        assert response.status_code == status.HTTP_200_OK
        grade_ids = [g["id"] for g in response.data["data"]]
        assert str(grade.id) in grade_ids

    def test_create_grade(self, admin_client, grade_band):
        response = admin_client.post(f"{BASE}/grades/", {
            "grade_band": str(grade_band.id),
            "name": "Grade 6",
            "short_code": "G6",
            "order": 6,
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Grade 6"

    def test_teacher_cannot_create_grade(self, teacher_client, grade_band):
        response = teacher_client.post(f"{BASE}/grades/", {
            "grade_band": str(grade_band.id),
            "name": "G99",
            "short_code": "G99",
            "order": 99,
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestGradeDetail:
    """GET/PATCH/DELETE /api/v1/academics/grades/{id}/"""

    def test_retrieve(self, admin_client, grade):
        response = admin_client.get(f"{BASE}/grades/{grade.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == grade.name

    def test_patch(self, admin_client, grade):
        response = admin_client.patch(
            f"{BASE}/grades/{grade.id}/",
            {"name": "Updated Grade"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        grade.refresh_from_db()
        assert grade.name == "Updated Grade"

    def test_delete_empty_grade(self, admin_client, tenant, grade_band):
        g = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="Empty",
            short_code="EMP", order=50,
        )
        response = admin_client.delete(f"{BASE}/grades/{g.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_grade_with_students_rejected(
        self, admin_client, grade, student_user,
    ):
        student_user.grade_fk = grade
        student_user.save(update_fields=["grade_fk"])
        response = admin_client.delete(f"{BASE}/grades/{grade.id}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "students" in response.data["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Section CRUD
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionListCreate:
    """GET/POST /api/v1/academics/sections/"""

    def test_list_sections(self, admin_client, section):
        response = admin_client.get(f"{BASE}/sections/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_filter_by_grade(self, admin_client, section, grade):
        response = admin_client.get(f"{BASE}/sections/", {"grade": str(grade.id)})
        assert response.status_code == status.HTTP_200_OK
        assert any(str(s["id"]) == str(section.id) for s in response.data["data"])

    def test_filter_by_academic_year(self, admin_client, section):
        response = admin_client.get(f"{BASE}/sections/", {"academic_year": "2026-27"})
        assert response.status_code == status.HTTP_200_OK
        assert any(str(s["id"]) == str(section.id) for s in response.data["data"])

    def test_create_section(self, admin_client, grade):
        response = admin_client.post(f"{BASE}/sections/", {
            "grade": str(grade.id),
            "name": "B",
            "academic_year": "2026-27",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "B"

    def test_duplicate_section_rejected(self, admin_client, section, grade):
        response = admin_client.post(f"{BASE}/sections/", {
            "grade": str(grade.id),
            "name": section.name,
            "academic_year": section.academic_year,
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestSectionDetail:
    """GET/PATCH/DELETE /api/v1/academics/sections/{id}/"""

    def test_retrieve(self, admin_client, section):
        response = admin_client.get(f"{BASE}/sections/{section.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == section.name

    def test_patch(self, admin_client, section):
        response = admin_client.patch(
            f"{BASE}/sections/{section.id}/",
            {"name": "Z"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        section.refresh_from_db()
        assert section.name == "Z"

    def test_delete_empty_section(self, admin_client, tenant, grade):
        s = Section.objects.create(
            tenant=tenant, grade=grade, name="DEL", academic_year="2026-27",
        )
        response = admin_client.delete(f"{BASE}/sections/{s.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_section_with_students_rejected(
        self, admin_client, section, student_user,
    ):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = admin_client.delete(f"{BASE}/sections/{section.id}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "students" in response.data["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Section Detail Views (students, teachers, courses)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSectionStudents:
    """GET /api/v1/academics/sections/{id}/students/"""

    def test_returns_students(self, admin_client, section, student_user):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = admin_client.get(f"{BASE}/sections/{section.id}/students/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 1
        assert len(response.data["students"]) == 1

    def test_empty_section(self, admin_client, section):
        response = admin_client.get(f"{BASE}/sections/{section.id}/students/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 0

    def test_search_filter(self, admin_client, section, student_user):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = admin_client.get(
            f"{BASE}/sections/{section.id}/students/",
            {"search": student_user.first_name},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] >= 1

    def test_search_no_match(self, admin_client, section, student_user):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = admin_client.get(
            f"{BASE}/sections/{section.id}/students/",
            {"search": "ZZZ_NOMATCH_ZZZ"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 0

    def test_teacher_can_access(self, teacher_client, section):
        """section_students uses @teacher_or_admin, so teachers are allowed."""
        response = teacher_client.get(f"{BASE}/sections/{section.id}/students/")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestSectionTeachers:
    """GET /api/v1/academics/sections/{id}/teachers/"""

    def test_returns_teachers(self, admin_client, section, teaching_assignment):
        response = admin_client.get(f"{BASE}/sections/{section.id}/teachers/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["teachers"]) >= 1

    def test_empty_when_no_assignments(self, admin_client, tenant, grade):
        empty_section = Section.objects.create(
            tenant=tenant, grade=grade, name="EMPTY", academic_year="2026-27",
        )
        response = admin_client.get(f"{BASE}/sections/{empty_section.id}/teachers/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["teachers"]) == 0


@pytest.mark.django_db
class TestSectionCourses:
    """GET /api/v1/academics/sections/{id}/courses/"""

    def test_returns_courses(self, admin_client, section, tenant, admin_user):
        from apps.courses.models import Course

        course = Course.objects.create(
            tenant=tenant, title="Section Course", course_type="ACADEMIC",
            created_by=admin_user,
        )
        course.target_sections.add(section)
        response = admin_client.get(f"{BASE}/sections/{section.id}/courses/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["courses"]) >= 1

    def test_empty_when_no_courses(self, admin_client, section):
        response = admin_client.get(f"{BASE}/sections/{section.id}/courses/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["courses"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Subject CRUD
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSubjectListCreate:
    """GET/POST /api/v1/academics/subjects/"""

    def test_list_subjects(self, admin_client, subject):
        response = admin_client.get(f"{BASE}/subjects/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_filter_by_department(self, admin_client, subject):
        response = admin_client.get(f"{BASE}/subjects/", {"department": "Sciences"})
        assert response.status_code == status.HTTP_200_OK
        assert any(s["code"] == subject.code for s in response.data["data"])

    def test_search_by_name(self, admin_client, subject):
        response = admin_client.get(f"{BASE}/subjects/", {"search": "Math"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_create_subject(self, admin_client):
        response = admin_client.post(f"{BASE}/subjects/", {
            "name": "Physics",
            "code": "PHY",
            "department": "Sciences",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Physics"

    def test_create_with_applicable_grades(self, admin_client, grade):
        response = admin_client.post(f"{BASE}/subjects/", {
            "name": "Chemistry",
            "code": "CHEM",
            "department": "Sciences",
            "applicable_grade_ids": [str(grade.id)],
        })
        assert response.status_code == status.HTTP_201_CREATED

    def test_duplicate_code_rejected(self, admin_client, subject):
        response = admin_client.post(f"{BASE}/subjects/", {
            "name": "Duplicate",
            "code": subject.code,
            "department": "Test",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_teacher_cannot_create(self, teacher_client):
        response = teacher_client.post(f"{BASE}/subjects/", {
            "name": "X", "code": "X",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestSubjectDetail:
    """GET/PATCH/DELETE /api/v1/academics/subjects/{id}/"""

    def test_retrieve(self, admin_client, subject):
        response = admin_client.get(f"{BASE}/subjects/{subject.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == subject.code

    def test_patch(self, admin_client, subject):
        response = admin_client.patch(
            f"{BASE}/subjects/{subject.id}/",
            {"department": "Updated Dept"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        subject.refresh_from_db()
        assert subject.department == "Updated Dept"

    def test_delete_subject(self, admin_client, tenant):
        s = Subject.objects.create(tenant=tenant, name="Deletable", code="DEL")
        response = admin_client.delete(f"{BASE}/subjects/{s.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT


# ═══════════════════════════════════════════════════════════════════════════
# TeachingAssignment CRUD
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTeachingAssignmentListCreate:
    """GET/POST /api/v1/academics/teaching-assignments/"""

    def test_list_assignments(self, admin_client, teaching_assignment):
        response = admin_client.get(f"{BASE}/teaching-assignments/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_filter_by_teacher(self, admin_client, teaching_assignment, teacher_user):
        response = admin_client.get(
            f"{BASE}/teaching-assignments/",
            {"teacher": str(teacher_user.id)},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_filter_by_subject(self, admin_client, teaching_assignment, subject):
        response = admin_client.get(
            f"{BASE}/teaching-assignments/",
            {"subject": str(subject.id)},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_create_assignment(self, admin_client, tenant, subject, section):
        from apps.users.models import User

        new_teacher = User.objects.create_user(
            email="newteacher@academics-test.com",
            password="Pass!123",
            first_name="New",
            last_name="Teacher",
            tenant=tenant,
            role="TEACHER",
            is_active=True,
        )
        response = admin_client.post(
            f"{BASE}/teaching-assignments/",
            {
                "teacher": str(new_teacher.id),
                "subject": str(subject.id),
                "section_ids": [str(section.id)],
                "academic_year": "2026-27",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["subject_name"] == subject.name

    def test_duplicate_assignment_rejected(
        self, admin_client, teaching_assignment, teacher_user, subject,
    ):
        """Same teacher+subject+year should be rejected."""
        response = admin_client.post(
            f"{BASE}/teaching-assignments/",
            {
                "teacher": str(teacher_user.id),
                "subject": str(subject.id),
                "academic_year": "2026-27",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_teacher_cannot_create(self, teacher_client, teacher_user, subject):
        response = teacher_client.post(
            f"{BASE}/teaching-assignments/",
            {
                "teacher": str(teacher_user.id),
                "subject": str(subject.id),
                "academic_year": "2026-27",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTeachingAssignmentDetail:
    """GET/PATCH/DELETE /api/v1/academics/teaching-assignments/{id}/"""

    def test_retrieve(self, admin_client, teaching_assignment):
        response = admin_client.get(
            f"{BASE}/teaching-assignments/{teaching_assignment.id}/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "teacher_name" in response.data

    def test_delete(self, admin_client, teaching_assignment):
        ta_id = teaching_assignment.id
        response = admin_client.delete(f"{BASE}/teaching-assignments/{ta_id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not TeachingAssignment.all_objects.filter(pk=ta_id).exists()


# ═══════════════════════════════════════════════════════════════════════════
# School Overview
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSchoolOverview:
    """GET /api/v1/academics/school-overview/"""

    def test_returns_overview(self, admin_client, grade_band, grade, section):
        response = admin_client.get(f"{BASE}/school-overview/")
        assert response.status_code == status.HTTP_200_OK
        assert "grade_bands" in response.data
        assert "academic_year" in response.data
        assert "school_name" in response.data
        assert len(response.data["grade_bands"]) >= 1

    def test_overview_contains_nested_grades(self, admin_client, grade_band, grade):
        response = admin_client.get(f"{BASE}/school-overview/")
        band = next(
            b for b in response.data["grade_bands"]
            if str(b["id"]) == str(grade_band.id)
        )
        assert len(band["grades"]) >= 1
        grade_data = band["grades"][0]
        assert "student_count" in grade_data
        assert "section_count" in grade_data
        assert "course_count" in grade_data

    def test_requires_auth(self, api_client):
        response = api_client.get(f"{BASE}/school-overview/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_teacher_cannot_access(self, teacher_client):
        response = teacher_client.get(f"{BASE}/school-overview/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ═══════════════════════════════════════════════════════════════════════════
# Add Student to Section
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAddStudent:
    """POST /api/v1/academics/sections/{id}/add-student/"""

    def test_adds_student(self, admin_client, section):
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/add-student/",
            {
                "email": "newstudent@test.com",
                "first_name": "New",
                "last_name": "Student",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newstudent@test.com"
        assert "student_id" in response.data
        # Password should NOT be returned (security)
        assert "generated_password" not in response.data

    def test_missing_email_rejected(self, admin_client, section):
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/add-student/",
            {"first_name": "No", "last_name": "Email"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data["error"].lower()

    def test_missing_first_name_rejected(self, admin_client, section):
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/add-student/",
            {"email": "noname@test.com", "last_name": "X"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "first name" in response.data["error"].lower()

    def test_duplicate_email_rejected(self, admin_client, section, student_user):
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/add-student/",
            {
                "email": student_user.email,
                "first_name": "Dup",
                "last_name": "User",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.data["error"].lower()

    def test_teacher_cannot_add_student(self, teacher_client, section):
        response = teacher_client.post(
            f"{BASE}/sections/{section.id}/add-student/",
            {
                "email": "teacher-add@test.com",
                "first_name": "T",
                "last_name": "A",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_with_parent_email(self, admin_client, section):
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/add-student/",
            {
                "email": "child@test.com",
                "first_name": "Child",
                "last_name": "Test",
                "parent_email": "parent@test.com",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED


# ═══════════════════════════════════════════════════════════════════════════
# Import Students (CSV)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestImportStudents:
    """POST /api/v1/academics/sections/{id}/import-students/"""

    def test_import_valid_csv(self, admin_client, section):
        csv = _csv_file([
            "first_name,last_name,email",
            "Alice,Smith,alice@import.com",
            "Bob,Jones,bob@import.com",
        ])
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/import-students/",
            {"file": csv},
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] == 2
        assert response.data["total_rows"] == 2

    def test_import_no_file_rejected(self, admin_client, section):
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/import-students/",
            {},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file" in response.data["error"].lower()

    def test_import_missing_columns(self, admin_client, section):
        csv = _csv_file([
            "name,email",
            "Alice,alice@bad.com",
        ])
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/import-students/",
            {"file": csv},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "missing" in response.data["error"].lower()

    def test_import_skips_duplicate_emails(self, admin_client, section, student_user):
        csv = _csv_file([
            "first_name,last_name,email",
            f"Dup,User,{student_user.email}",
            "Fresh,User,fresh@import.com",
        ])
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/import-students/",
            {"file": csv},
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] == 1
        assert response.data["skipped"] == 1

    def test_import_skips_empty_email_rows(self, admin_client, section):
        csv = _csv_file([
            "first_name,last_name,email",
            "NoEmail,User,",
            "Good,User,good@import.com",
        ])
        response = admin_client.post(
            f"{BASE}/sections/{section.id}/import-students/",
            {"file": csv},
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] == 1
        assert len(response.data["errors"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Student Transfer
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTransferStudent:
    """POST /api/v1/academics/students/{id}/transfer/"""

    def test_transfers_student(self, admin_client, tenant, grade, section, student_user):
        section_b = Section.objects.create(
            tenant=tenant, grade=grade, name="B", academic_year="2026-27",
        )
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        response = admin_client.post(
            f"{BASE}/students/{student_user.id}/transfer/",
            {"section_id": str(section_b.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        student_user.refresh_from_db()
        assert student_user.section_fk == section_b

    def test_transfer_updates_grade(self, admin_client, tenant, grade_band, section, student_user):
        """Transferring to a section in a different grade should update grade_fk."""
        new_grade = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="Grade 6",
            short_code="G6X", order=6,
        )
        new_section = Section.objects.create(
            tenant=tenant, grade=new_grade, name="A", academic_year="2026-27",
        )
        student_user.section_fk = section
        student_user.grade_fk = section.grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        response = admin_client.post(
            f"{BASE}/students/{student_user.id}/transfer/",
            {"section_id": str(new_section.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        student_user.refresh_from_db()
        assert student_user.grade_fk == new_grade

    def test_missing_section_id_rejected(self, admin_client, student_user, section):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = admin_client.post(
            f"{BASE}/students/{student_user.id}/transfer/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "section_id" in response.data["error"].lower()

    def test_transfer_nonexistent_student(self, admin_client):
        fake_id = uuid.uuid4()
        response = admin_client.post(
            f"{BASE}/students/{fake_id}/transfer/",
            {"section_id": str(uuid.uuid4())},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_teacher_cannot_transfer(self, teacher_client, student_user, section):
        student_user.section_fk = section
        student_user.save(update_fields=["section_fk"])
        response = teacher_client.post(
            f"{BASE}/students/{student_user.id}/transfer/",
            {"section_id": str(uuid.uuid4())},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ═══════════════════════════════════════════════════════════════════════════
# Course Cloning
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCloneCourse:
    """POST /api/v1/academics/courses/{id}/clone/"""

    def test_clones_course(self, admin_client, tenant, admin_user):
        from apps.courses.models import Course

        course = Course.objects.create(
            tenant=tenant, title="Original", course_type="ACADEMIC",
            created_by=admin_user,
        )
        response = admin_client.post(
            f"{BASE}/courses/{course.id}/clone/",
            {"title": "Cloned Course"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "Cloned Course"

    def test_clone_default_title(self, admin_client, tenant, admin_user):
        from apps.courses.models import Course

        course = Course.objects.create(
            tenant=tenant, title="My Course", course_type="ACADEMIC",
            created_by=admin_user,
        )
        response = admin_client.post(
            f"{BASE}/courses/{course.id}/clone/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "Copy" in response.data["title"]

    def test_clone_nonexistent_course(self, admin_client):
        fake_id = uuid.uuid4()
        response = admin_client.post(
            f"{BASE}/courses/{fake_id}/clone/",
            {"title": "Ghost"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_teacher_can_clone(self, teacher_client, tenant, admin_user):
        """clone_course_view uses @teacher_or_admin."""
        from apps.courses.models import Course

        course = Course.objects.create(
            tenant=tenant, title="Cloneable", course_type="ACADEMIC",
            created_by=admin_user,
        )
        response = teacher_client.post(
            f"{BASE}/courses/{course.id}/clone/",
            {"title": "Teacher Clone"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED


# ═══════════════════════════════════════════════════════════════════════════
# Academic Year Promotion
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPromotionWorkflow:
    """GET /api/v1/academics/promotion/preview/ & POST .../execute/"""

    def test_preview(self, admin_client, grade_band, grade):
        response = admin_client.get(f"{BASE}/promotion/preview/")
        assert response.status_code == status.HTTP_200_OK
        assert "grades" in response.data
        assert "total_students" in response.data
        assert "current_academic_year" in response.data

    def test_preview_includes_grade_info(self, admin_client, grade_band, grade, student_user):
        student_user.grade_fk = grade
        student_user.save(update_fields=["grade_fk"])
        response = admin_client.get(f"{BASE}/promotion/preview/")
        assert response.status_code == status.HTTP_200_OK
        grade_entry = next(
            (g for g in response.data["grades"] if str(g["grade_id"]) == str(grade.id)),
            None,
        )
        assert grade_entry is not None
        assert grade_entry["student_count"] >= 1

    def test_execute_requires_academic_year(self, admin_client, grade_band, grade):
        response = admin_client.post(
            f"{BASE}/promotion/execute/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "new_academic_year" in response.data["error"].lower()

    def test_execute_promotion(self, admin_client, tenant, grade_band, grade, student_user):
        student_user.grade_fk = grade
        student_user.section_fk = None
        student_user.save(update_fields=["grade_fk", "section_fk"])

        response = admin_client.post(
            f"{BASE}/promotion/execute/",
            {"new_academic_year": "2027-28"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "promoted" in response.data
        assert "graduated" in response.data
        assert response.data["new_academic_year"] == "2027-28"

    def test_teacher_cannot_promote(self, teacher_client):
        response = teacher_client.get(f"{BASE}/promotion/preview/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_cannot_execute(self, teacher_client):
        response = teacher_client.post(
            f"{BASE}/promotion/execute/",
            {"new_academic_year": "2027-28"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
