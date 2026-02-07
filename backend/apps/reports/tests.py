# apps/reports/tests.py

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"])
class ReportsViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Test School", slug="test-school-rep", subdomain="test",
            email="t@t.com", is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@test.com", password="admin123",
            first_name="A", last_name="A", tenant=self.tenant, role="SCHOOL_ADMIN",
        )
        self.teacher = User.objects.create_user(
            email="teach@test.com", password="teacher123",
            first_name="T", last_name="T", tenant=self.tenant, role="TEACHER",
        )
        self.course = Course.objects.create(
            tenant=self.tenant, title="Test Course", slug="test-course",
            description="Test", created_by=self.admin,
            is_published=True, is_active=True, assigned_to_all=True,
        )
        self._login()

    def _login(self):
        resp = self.client.post("/api/users/auth/login/", {
            "email": "admin@test.com", "password": "admin123"
        }, HTTP_HOST="test.lms.com")
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _get(self, url, **kwargs):
        return self.client.get(url, HTTP_HOST="test.lms.com", **kwargs)

    def test_course_progress_report(self):
        resp = self._get(f"/api/reports/course-progress/?course_id={self.course.id}")
        self.assertEqual(resp.status_code, 200)

    def test_assignment_status_report_no_assignment(self):
        """Should handle no matching assignment gracefully."""
        import uuid
        resp = self._get(f"/api/reports/assignment-status/?assignment_id={uuid.uuid4()}")
        self.assertEqual(resp.status_code, 404)

    def test_list_courses_for_reports(self):
        resp = self._get("/api/reports/courses/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(len(resp.data) >= 1)

    def test_list_assignments_for_reports(self):
        resp = self._get("/api/reports/assignments/")
        self.assertEqual(resp.status_code, 200)

    def test_reports_require_admin(self):
        """Teachers should not access admin reports."""
        resp = self.client.post("/api/users/auth/login/", {
            "email": "teach@test.com", "password": "teacher123"
        }, HTTP_HOST="test.lms.com")
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self._get("/api/reports/courses/")
        self.assertEqual(resp.status_code, 403)
