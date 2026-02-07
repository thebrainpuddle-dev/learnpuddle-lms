from django.test import TestCase
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course, Module


class VideoUploadTenantIsolationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.t1 = Tenant.objects.create(
            name="Tenant 1",
            slug="t1",
            subdomain="t1",
            email="t1@test.com",
            is_active=True,
        )
        self.t2 = Tenant.objects.create(
            name="Tenant 2",
            slug="t2",
            subdomain="t2",
            email="t2@test.com",
            is_active=True,
        )

        self.admin1 = User.objects.create_user(
            email="admin@t1.test",
            password="pass123",
            first_name="Admin",
            last_name="One",
            tenant=self.t1,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.admin2 = User.objects.create_user(
            email="admin@t2.test",
            password="pass123",
            first_name="Admin",
            last_name="Two",
            tenant=self.t2,
            role="SCHOOL_ADMIN",
            is_active=True,
        )

        self.course1 = Course.objects.create(
            tenant=self.t1,
            title="Course 1",
            slug="course-1",
            description="c1",
            created_by=self.admin1,
            is_published=True,
            is_active=True,
        )
        self.course2 = Course.objects.create(
            tenant=self.t2,
            title="Course 2",
            slug="course-2",
            description="c2",
            created_by=self.admin2,
            is_published=True,
            is_active=True,
        )

        self.module1 = Module.objects.create(course=self.course1, title="M1", description="", order=1, is_active=True)
        self.module2 = Module.objects.create(course=self.course2, title="M2", description="", order=1, is_active=True)

    def _login_and_set_bearer(self, host: str, email: str, password: str):
        self.client.defaults["HTTP_HOST"] = host
        resp = self.client.post("/api/users/auth/login/", {"email": email, "password": password}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_cross_tenant_video_upload_404(self):
        # Login as tenant1 admin but attempt upload to tenant2 course/module
        self._login_and_set_bearer("t1.lms.com", "admin@t1.test", "pass123")

        resp = self.client.post(
            f"/api/courses/{self.course2.id}/modules/{self.module2.id}/contents/video-upload/",
            data={"title": "X"},
            format="multipart",
        )
        # Tenant filter in get_object_or_404 should hide the other tenant's course.
        self.assertEqual(resp.status_code, 404)

