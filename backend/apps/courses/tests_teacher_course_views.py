# apps/courses/tests_teacher_course_views.py
"""
Tests for teacher-facing course views:
  - teacher_course_list: GET /api/v1/teacher/courses/
  - teacher_course_detail: GET /api/v1/teacher/courses/<id>/
  - teacher_video_transcript: GET /api/v1/teacher/videos/<id>/transcript/

Covers:
- Auth guards (401 for unauthenticated)
- Correct tenant isolation (403 for wrong tenant)
- Assignment rules (assigned_to_all, assigned_teachers)
- Content not found (404)
"""

import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course, Module, Content


HOST = "test.lms.com"
HOST_B = "other.lms.com"


def _tenant(name, slug, sub, email):
    return Tenant.objects.create(name=name, slug=slug, subdomain=sub, email=email, is_active=True)


def _user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email,
        password="Pass!1234",
        first_name="T",
        last_name="U",
        tenant=tenant,
        role=role,
        is_active=True,
    )


def _course(tenant, admin, title="Course", assigned_to_all=True, published=True):
    return Course.objects.create(
        tenant=tenant,
        title=title,
        slug=f"course-{uuid.uuid4().hex[:6]}",
        description="Test",
        created_by=admin,
        is_published=published,
        is_active=True,
        assigned_to_all=assigned_to_all,
    )


def _module(course):
    return Module.objects.create(course=course, title="Module 1", order=1, is_active=True)


def _content(module, ctype="TEXT"):
    return Content.objects.create(
        module=module,
        title="Content 1",
        content_type=ctype,
        order=1,
        text_content="<p>Hello</p>",
        is_active=True,
    )


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TeacherCourseListTestCase(TestCase):
    """Tests for GET /api/v1/teacher/courses/"""

    def setUp(self):
        self.tenant = _tenant("List School", "tcl", "test", "admin@tcl.com")
        self.admin = _user("admin@tcl.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@tcl.com", self.tenant)
        self.course = _course(self.tenant, self.admin, assigned_to_all=True)

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/teacher/courses/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_teacher_can_list_assigned_all_courses(self):
        client = self._client(self.teacher)
        response = client.get("/api/v1/teacher/courses/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data]
        self.assertIn(str(self.course.id), ids)

    def test_teacher_sees_only_published_courses(self):
        draft = _course(self.tenant, self.admin, title="Draft", published=False)
        client = self._client(self.teacher)
        response = client.get("/api/v1/teacher/courses/", HTTP_HOST=HOST)
        ids = [item["id"] for item in response.data]
        self.assertNotIn(str(draft.id), ids)

    def test_teacher_sees_only_assigned_to_all_not_other_teachers_course(self):
        other_teacher = _user("other@tcl.com", self.tenant)
        unassigned_course = _course(self.tenant, self.admin, title="Unassigned", assigned_to_all=False)
        client = self._client(self.teacher)
        response = client.get("/api/v1/teacher/courses/", HTTP_HOST=HOST)
        ids = [item["id"] for item in response.data]
        self.assertNotIn(str(unassigned_course.id), ids)

    def test_teacher_sees_course_directly_assigned(self):
        unassigned = _course(self.tenant, self.admin, title="Direct", assigned_to_all=False)
        unassigned.assigned_teachers.add(self.teacher)
        client = self._client(self.teacher)
        response = client.get("/api/v1/teacher/courses/", HTTP_HOST=HOST)
        ids = [item["id"] for item in response.data]
        self.assertIn(str(unassigned.id), ids)

    def test_admin_can_list_courses(self):
        client = self._client(self.admin)
        response = client.get("/api/v1/teacher/courses/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TeacherCourseDetailTestCase(TestCase):
    """Tests for GET /api/v1/teacher/courses/<id>/"""

    def setUp(self):
        self.tenant = _tenant("Detail School", "tcd", "test", "admin@tcd.com")
        self.admin = _user("admin@tcd.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@tcd.com", self.tenant)
        self.course = _course(self.tenant, self.admin, assigned_to_all=True)
        self.module = _module(self.course)
        self.content = _content(self.module)

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(f"/api/v1/teacher/courses/{self.course.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_teacher_can_get_assigned_course(self):
        client = self._client(self.teacher)
        response = client.get(f"/api/v1/teacher/courses/{self.course.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.course.id))

    def test_teacher_cannot_get_unassigned_course(self):
        other_admin = _user("admin2@tcd.com", self.tenant, role="SCHOOL_ADMIN")
        unassigned = _course(self.tenant, self.admin, title="Not Mine", assigned_to_all=False)
        client = self._client(self.teacher)
        response = client.get(f"/api/v1/teacher/courses/{unassigned.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_nonexistent_course_returns_404(self):
        client = self._client(self.teacher)
        response = client.get(f"/api/v1/teacher/courses/{uuid.uuid4()}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_get_any_course_detail(self):
        client = self._client(self.admin)
        response = client.get(f"/api/v1/teacher/courses/{self.course.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_course_detail_includes_modules(self):
        client = self._client(self.teacher)
        response = client.get(f"/api/v1/teacher/courses/{self.course.id}/", HTTP_HOST=HOST)
        self.assertIn("modules", response.data)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TeacherVideoTranscriptTestCase(TestCase):
    """Tests for GET /api/v1/teacher/videos/<id>/transcript/"""

    def setUp(self):
        self.tenant = _tenant("Transcript School", "tvt", "test", "admin@tvt.com")
        self.admin = _user("admin@tvt.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@tvt.com", self.tenant)
        self.course = _course(self.tenant, self.admin, assigned_to_all=True)
        self.module = _module(self.course)
        self.video_content = _content(self.module, ctype="VIDEO")

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(
            f"/api/v1/teacher/videos/{self.video_content.id}/transcript/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_video_asset_returns_404(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get(
            f"/api/v1/teacher/videos/{self.video_content.id}/transcript/", HTTP_HOST=HOST
        )
        # No video asset attached — should return 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_content_returns_404(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get(
            f"/api/v1/teacher/videos/{uuid.uuid4()}/transcript/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_not_assigned_to_course_returns_403(self):
        other_teacher = _user("other@tvt.com", self.tenant)
        unassigned_course = _course(self.tenant, self.admin, title="Not Mine", assigned_to_all=False)
        unassigned_module = _module(unassigned_course)
        unassigned_video = _content(unassigned_module, ctype="VIDEO")
        client = APIClient()
        client.force_authenticate(user=other_teacher)
        response = client.get(
            f"/api/v1/teacher/videos/{unassigned_video.id}/transcript/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
