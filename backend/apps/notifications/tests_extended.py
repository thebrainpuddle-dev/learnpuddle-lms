"""
Supplementary notification tests.
Extends (does NOT modify) the existing tests.py.

Added coverage:
  - NotificationAuthTestCase        : unauthenticated requests → 401
  - NotificationCrossTenantTestCase : teacher cannot see another tenant's notifications
  - CreateBulkNotificationsTestCase : service-level bulk creation + duplicate guard
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.notifications.services import create_bulk_notifications
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class NotificationAuthTestCase(TestCase):
    """All notification endpoints must reject unauthenticated requests."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Auth School",
            slug="auth-school-notif",
            subdomain="test",
            email="auth@notif.test",
            is_active=True,
        )

    def _get(self, url):
        return self.client.get(url, HTTP_HOST="test.lms.com")

    def _post(self, url):
        return self.client.post(url, HTTP_HOST="test.lms.com")

    def test_notification_list_unauthenticated_returns_401(self):
        resp = self._get("/api/notifications/")
        self.assertEqual(resp.status_code, 401)

    def test_unread_count_unauthenticated_returns_401(self):
        resp = self._get("/api/notifications/unread-count/")
        self.assertEqual(resp.status_code, 401)

    def test_mark_all_read_unauthenticated_returns_401(self):
        resp = self._post("/api/notifications/mark-all-read/")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["school-a.lms.com", "school-b.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class NotificationCrossTenantTestCase(TestCase):
    """
    A teacher on Tenant A must never see Tenant B's notifications,
    even if they somehow share a user account ID space.
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant_a = Tenant.objects.create(
            name="School A", slug="school-a-notif", subdomain="school-a",
            email="a@notif.test", is_active=True,
        )
        self.tenant_b = Tenant.objects.create(
            name="School B", slug="school-b-notif", subdomain="school-b",
            email="b@notif.test", is_active=True,
        )
        self.teacher_a = User.objects.create_user(
            email="teacher@school-a.test", password="pass123",
            first_name="Teacher", last_name="A",
            tenant=self.tenant_a, role="TEACHER", is_active=True,
        )
        self.teacher_b = User.objects.create_user(
            email="teacher@school-b.test", password="pass123",
            first_name="Teacher", last_name="B",
            tenant=self.tenant_b, role="TEACHER", is_active=True,
        )
        # Notification for tenant_a teacher
        self.notif_a = Notification.objects.create(
            tenant=self.tenant_a,
            teacher=self.teacher_a,
            notification_type="SYSTEM",
            title="Tenant A Notification",
            message="Only for School A",
        )
        # Notification for tenant_b teacher
        self.notif_b = Notification.objects.create(
            tenant=self.tenant_b,
            teacher=self.teacher_b,
            notification_type="SYSTEM",
            title="Tenant B Notification",
            message="Only for School B",
        )

    def test_teacher_a_sees_only_own_tenant_notifications(self):
        self.client.force_authenticate(user=self.teacher_a)
        resp = self.client.get("/api/notifications/", HTTP_HOST="school-a.lms.com")
        self.assertEqual(resp.status_code, 200)
        titles = [n["title"] for n in resp.data]
        self.assertIn("Tenant A Notification", titles)
        self.assertNotIn("Tenant B Notification", titles)

    def test_teacher_b_sees_only_own_tenant_notifications(self):
        self.client.force_authenticate(user=self.teacher_b)
        resp = self.client.get("/api/notifications/", HTTP_HOST="school-b.lms.com")
        self.assertEqual(resp.status_code, 200)
        titles = [n["title"] for n in resp.data]
        self.assertIn("Tenant B Notification", titles)
        self.assertNotIn("Tenant A Notification", titles)

    def test_teacher_a_cannot_mark_tenant_b_notification_as_read(self):
        """mark-read endpoint: 404 for a notification belonging to another tenant."""
        self.client.force_authenticate(user=self.teacher_a)
        resp = self.client.post(
            f"/api/notifications/{self.notif_b.id}/read/",
            HTTP_HOST="school-a.lms.com",
        )
        self.assertEqual(resp.status_code, 404)

    def test_unread_count_scoped_to_tenant(self):
        """Unread count only counts notifications for the authenticated teacher's tenant."""
        self.client.force_authenticate(user=self.teacher_a)
        resp = self.client.get("/api/notifications/unread-count/", HTTP_HOST="school-a.lms.com")
        self.assertEqual(resp.status_code, 200)
        # Only teacher_a's notification should be counted
        self.assertEqual(resp.data["count"], 1)


# ---------------------------------------------------------------------------
# create_bulk_notifications service
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class CreateBulkNotificationsTestCase(TestCase):
    """Service-level tests for create_bulk_notifications (called by video pipeline)."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Bulk Notif School",
            slug="bulk-notif-school",
            subdomain="test",
            email="bulk@notif.test",
            is_active=True,
        )
        self.teacher1 = User.objects.create_user(
            email="t1@bulk.test", password="pass123",
            first_name="Teacher", last_name="One",
            tenant=self.tenant, role="TEACHER", is_active=True,
        )
        self.teacher2 = User.objects.create_user(
            email="t2@bulk.test", password="pass123",
            first_name="Teacher", last_name="Two",
            tenant=self.tenant, role="TEACHER", is_active=True,
        )

    @patch("apps.notifications.services._queue_email")
    def test_creates_notification_for_each_teacher(self, mock_queue):
        created = create_bulk_notifications(
            tenant=self.tenant,
            teachers=[self.teacher1, self.teacher2],
            notification_type="ASSIGNMENT_DUE",
            title="New Assignment",
            message="Please complete by Friday.",
            send_email=False,
        )
        self.assertEqual(len(created), 2)
        teacher_ids = {str(n.teacher_id) for n in created}
        self.assertIn(str(self.teacher1.id), teacher_ids)
        self.assertIn(str(self.teacher2.id), teacher_ids)

    @patch("apps.notifications.services._queue_email")
    def test_notifications_have_correct_tenant(self, mock_queue):
        created = create_bulk_notifications(
            tenant=self.tenant,
            teachers=[self.teacher1],
            notification_type="SYSTEM",
            title="System Message",
            message="Platform maintenance tonight.",
            send_email=False,
        )
        self.assertEqual(created[0].tenant_id, self.tenant.id)

    @patch("apps.notifications.services._queue_email")
    def test_empty_teacher_list_creates_nothing(self, mock_queue):
        created = create_bulk_notifications(
            tenant=self.tenant,
            teachers=[],
            notification_type="SYSTEM",
            title="No recipients",
            message="Should not be created.",
            send_email=False,
        )
        self.assertEqual(len(created), 0)
        mock_queue.assert_not_called()

    @patch("apps.notifications.services._queue_email")
    def test_send_email_true_queues_emails(self, mock_queue):
        """When send_email=True, _queue_email called once per teacher."""
        create_bulk_notifications(
            tenant=self.tenant,
            teachers=[self.teacher1, self.teacher2],
            notification_type="ASSIGNMENT_DUE",
            title="Quiz Due",
            message="Complete your quiz.",
            send_email=True,
        )
        self.assertEqual(mock_queue.call_count, 2)
