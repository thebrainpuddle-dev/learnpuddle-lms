# apps/notifications/tests.py

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.notifications.models import Notification


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"])
class NotificationViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Test School", slug="test-school", subdomain="test", email="t@t.com", is_active=True
        )
        self.teacher = User.objects.create_user(
            email="teach@test.com", password="testpass123",
            first_name="T", last_name="T", tenant=self.tenant, role="TEACHER",
        )
        # Create test notifications
        for i in range(5):
            Notification.objects.create(
                teacher=self.teacher, tenant=self.tenant,
                notification_type="SYSTEM",
                title=f"Notification {i}",
                message=f"Message {i}",
                is_read=(i < 2),  # First 2 are read
            )
        self._login()

    def _login(self):
        resp = self.client.post("/api/users/auth/login/", {
            "email": "teach@test.com", "password": "testpass123"
        }, HTTP_HOST="test.lms.com")
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _get(self, url, **kwargs):
        return self.client.get(url, HTTP_HOST="test.lms.com", **kwargs)

    def _post_req(self, url, data=None, **kwargs):
        return self.client.post(url, data, HTTP_HOST="test.lms.com", **kwargs)

    def test_notification_list(self):
        resp = self._get("/api/notifications/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 5)

    def test_notification_list_unread_only(self):
        resp = self._get("/api/notifications/?unread_only=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 3)

    def test_notification_list_with_type_filter(self):
        Notification.objects.create(
            teacher=self.teacher, tenant=self.tenant,
            notification_type="REMINDER", title="R", message="R",
        )
        resp = self._get("/api/notifications/?type=REMINDER")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_notification_list_limit(self):
        resp = self._get("/api/notifications/?limit=2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_unread_count(self):
        resp = self._get("/api/notifications/unread-count/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 3)

    def test_mark_read(self):
        unread = Notification.objects.filter(teacher=self.teacher, is_read=False).first()
        resp = self._post_req(f"/api/notifications/{unread.id}/read/")
        self.assertEqual(resp.status_code, 200)
        unread.refresh_from_db()
        self.assertTrue(unread.is_read)

    def test_mark_all_read(self):
        resp = self._post_req("/api/notifications/mark-all-read/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["marked_read"], 3)
        self.assertEqual(
            Notification.objects.filter(teacher=self.teacher, is_read=False).count(), 0
        )

    def test_mark_read_wrong_notification_404(self):
        import uuid
        resp = self._post_req(f"/api/notifications/{uuid.uuid4()}/read/")
        self.assertEqual(resp.status_code, 404)
