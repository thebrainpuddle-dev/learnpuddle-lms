from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Course
from apps.tenants.models import Tenant


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=[".lms.com", "lms.com", "localhost", "127.0.0.1"],
)
class CourseCreationFlowTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Demo School",
            subdomain="demo",
            slug="demo-school",
            is_active=True,
        )
        self.user = get_user_model().objects.create_user(
            email="admin@demo.test",
            password="pass123",
            first_name="Demo",
            last_name="Admin",
            role="SCHOOL_ADMIN",
            tenant=self.tenant,
            is_active=True,
        )

    def _login(self):
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": "admin@demo.test", "password": "pass123"},
            format="json",
            HTTP_HOST="demo.lms.com",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_admin_course_create_flow(self):
        self._login()

        payload = {
            "title": "Course Creation Flow Test",
            "description": "Validates tenant-scoped course creation endpoint.",
            "is_mandatory": True,
            "is_published": False,
            "assigned_to_all": False,
            "assigned_groups": [],
            "assigned_teachers": [],
        }
        create_resp = self.client.post(
            "/api/courses/",
            payload,
            format="json",
            HTTP_HOST="demo.lms.com",
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.content)
        self.assertIn("id", create_resp.data)
        self.assertEqual(create_resp.data["title"], payload["title"])

        created = Course.objects.get(id=create_resp.data["id"])
        self.assertEqual(created.tenant_id, self.tenant.id)
        self.assertEqual(created.created_by_id, self.user.id)
        self.assertEqual(created.description, payload["description"])
        self.assertTrue(created.is_mandatory)
        self.assertFalse(created.is_published)

        list_resp = self.client.get("/api/courses/", HTTP_HOST="demo.lms.com")
        self.assertEqual(list_resp.status_code, 200, list_resp.content)
        self.assertGreaterEqual(list_resp.data["count"], 1)
