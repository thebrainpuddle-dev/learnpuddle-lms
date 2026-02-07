# apps/reminders/tests.py

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.reminders.models import ReminderCampaign


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"])
class ReminderViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Test School", slug="test-school-rem", subdomain="test",
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
        self._login()

    def _login(self):
        resp = self.client.post("/api/users/auth/login/", {
            "email": "admin@test.com", "password": "admin123"
        }, HTTP_HOST="test.lms.com")
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_reminder_preview(self):
        resp = self.client.post("/api/reminders/preview/", {
            "reminder_type": "CUSTOM",
            "subject": "Test Reminder",
            "message": "Hello teachers",
            "teacher_ids": [str(self.teacher.id)],
        }, format="json", HTTP_HOST="test.lms.com")
        self.assertIn(resp.status_code, [200, 201])

    def test_reminder_history(self):
        resp = self.client.get("/api/reminders/history/", HTTP_HOST="test.lms.com")
        self.assertEqual(resp.status_code, 200)

    def test_reminder_requires_admin(self):
        """Teachers should not be able to send reminders."""
        resp = self.client.post("/api/users/auth/login/", {
            "email": "teach@test.com", "password": "teacher123"
        }, HTTP_HOST="test.lms.com")
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.post("/api/reminders/preview/", {
            "reminder_type": "CUSTOM", "subject": "Test", "message": "Nope"
        }, format="json", HTTP_HOST="test.lms.com")
        self.assertEqual(resp.status_code, 403)
