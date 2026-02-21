from django.test import TestCase
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course


class CourseTenantIsolationTestCase(TestCase):
    DEMO_ADMIN_PASSWORD = "TenantPass@123"

    def setUp(self):
        self.client = APIClient()
        self.demo = Tenant.objects.create(
            name="Demo School",
            slug="demo-school-test",
            subdomain="demo",
            email="demo@test.com",
            is_active=True,
        )
        self.abc = Tenant.objects.create(
            name="ABC School",
            slug="abc-school-test",
            subdomain="abc",
            email="abc@test.com",
            is_active=True,
        )

        self.demo_admin = User.objects.create_user(
            email="admin@demo.test",
            password=self.DEMO_ADMIN_PASSWORD,
            first_name="Demo",
            last_name="Admin",
            tenant=self.demo,
            role="SCHOOL_ADMIN",
            is_active=True,
        )

        self.abc_admin = User.objects.create_user(
            email="admin@abc.test",
            password="abc123",
            first_name="ABC",
            last_name="Admin",
            tenant=self.abc,
            role="SCHOOL_ADMIN",
            is_active=True,
        )

        self.demo_course = Course.objects.create(
            tenant=self.demo,
            title="Demo Course",
            slug="demo-course",
            description="demo",
            created_by=self.demo_admin,
            is_published=True,
            is_active=True,
        )

        self.abc_course = Course.objects.create(
            tenant=self.abc,
            title="ABC Course",
            slug="abc-course",
            description="abc",
            created_by=self.abc_admin,
            is_published=True,
            is_active=True,
        )

    def _login_and_set_bearer(self, host: str, email: str, password: str):
        self.client.defaults["HTTP_HOST"] = host
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_admin_course_list_is_tenant_scoped(self):
        self._login_and_set_bearer("demo.lms.com", "admin@demo.test", self.DEMO_ADMIN_PASSWORD)

        resp = self.client.get("/api/courses/")
        self.assertEqual(resp.status_code, 200)

        ids = [c["id"] for c in resp.json().get("results", [])]
        self.assertIn(str(self.demo_course.id), ids)
        self.assertNotIn(str(self.abc_course.id), ids)

    def test_cross_tenant_course_detail_not_found(self):
        self._login_and_set_bearer("demo.lms.com", "admin@demo.test", self.DEMO_ADMIN_PASSWORD)

        resp = self.client.get(f"/api/courses/{self.abc_course.id}/")
        # get_object_or_404 with tenant filter -> 404
        self.assertEqual(resp.status_code, 404)
