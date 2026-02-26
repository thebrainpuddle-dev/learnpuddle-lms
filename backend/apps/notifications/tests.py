# apps/notifications/tests.py

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.notifications.models import Notification
from apps.notifications.services import notify_reminder
from apps.notifications.tasks import send_notification_email


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"], PLATFORM_DOMAIN="lms.com")
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


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"], PLATFORM_DOMAIN="lms.com")
class NotificationDeliveryRulesTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Notify School", slug="notify-school", subdomain="notify", email="n@t.com", is_active=True
        )
        self.teacher = User.objects.create_user(
            email="teacher@notify.com",
            password="testpass123",
            first_name="Notify",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
        )

    @override_settings(REMINDER_EMAIL_ENABLED=True, COURSE_ASSIGNMENT_EMAIL_ENABLED=True)
    @patch("apps.notifications.tasks.send_templated_email")
    def test_course_assignment_respects_email_courses_preference(self, mocked_send):
        self.teacher.notification_preferences = {"email_courses": False}
        self.teacher.save(update_fields=["notification_preferences"])
        notification = Notification.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="COURSE_ASSIGNED",
            title="New Course",
            message="Assigned",
        )
        result = send_notification_email(str(notification.id))

        self.assertEqual(result.get("reason"), "user_preference")
        mocked_send.assert_not_called()

    @patch("apps.notifications.services._queue_email")
    def test_notify_reminder_does_not_queue_notification_email(self, mocked_queue):
        created = notify_reminder(
            tenant=self.tenant,
            teachers=[self.teacher],
            subject="Reminder",
            message="Reminder message",
        )

        self.assertEqual(len(created), 1)
        mocked_queue.assert_not_called()

    @override_settings(REMINDER_EMAIL_ENABLED=False)
    @patch("apps.notifications.tasks.send_templated_email")
    def test_assignment_due_not_blocked_by_reminder_toggle(self, mocked_send):
        notification = Notification.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="ASSIGNMENT_DUE",
            title="Assignment Due",
            message="Please submit",
        )
        result = send_notification_email(str(notification.id))

        self.assertTrue(result.get("sent"))
        mocked_send.assert_called_once()
