# apps/notifications/tests_services.py
"""
Unit tests for notifications/services.py.

Tests:
- create_notification: creates DB record, blocks cross-tenant
- create_bulk_notifications: bulk create, cross-tenant filtering
- serialize_notification: correct shape
- notify_course_assigned: calls bulk create
- notify_reminder: correct notification type selection

WebSocket/Celery side effects are mocked out since channels
are not available in test environment.
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.notifications.models import Notification
from apps.notifications import services


def _tenant(name, slug, sub, email):
    return Tenant.objects.create(name=name, slug=slug, subdomain=sub, email=email, is_active=True)


def _user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email, password="Pass!1234",
        first_name="T", last_name="U",
        tenant=tenant, role=role, is_active=True,
    )


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class SerializeNotificationTestCase(TestCase):
    """Tests for serialize_notification()"""

    def setUp(self):
        self.tenant = _tenant("Serialize School", "notif-ser", "test", "ser@test.com")
        self.teacher = _user("teacher@ser.com", self.tenant)

    def test_serialize_notification_has_required_keys(self):
        notif = Notification.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="REMINDER",
            title="Test",
            message="Hello",
        )
        data = services.serialize_notification(notif)
        self.assertIn("id", data)
        self.assertIn("type", data)
        self.assertIn("title", data)
        self.assertIn("message", data)
        self.assertIn("is_read", data)
        self.assertIn("is_actionable", data)
        self.assertIn("created_at", data)

    def test_serialize_notification_course_id_is_none_when_unset(self):
        notif = Notification.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="REMINDER",
            title="No Course",
            message="No course here",
        )
        data = services.serialize_notification(notif)
        self.assertIsNone(data["course_id"])

    def test_serialize_notification_actionable_for_course_assigned(self):
        notif = Notification.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="COURSE_ASSIGNED",
            title="Course!",
            message="Assigned",
            is_actionable=True,
        )
        data = services.serialize_notification(notif)
        self.assertTrue(data["is_actionable"])


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class CreateNotificationTestCase(TestCase):
    """Tests for create_notification()"""

    def setUp(self):
        self.tenant = _tenant("Notif School", "notif-create", "test", "notif@test.com")
        self.teacher = _user("teacher@notif.com", self.tenant)

    @patch("apps.notifications.services.send_realtime_notification")
    def test_create_notification_persists_to_db(self, mock_ws):
        notif = services.create_notification(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="REMINDER",
            title="Test Reminder",
            message="Do something",
        )
        self.assertIsNotNone(notif)
        self.assertIsNotNone(notif.id)
        self.assertTrue(Notification.objects.filter(id=notif.id).exists())

    @patch("apps.notifications.services.send_realtime_notification")
    def test_create_notification_correct_type(self, mock_ws):
        notif = services.create_notification(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="COURSE_ASSIGNED",
            title="New Course",
            message="You have a new course",
        )
        self.assertEqual(notif.notification_type, "COURSE_ASSIGNED")

    @patch("apps.notifications.services.send_realtime_notification")
    def test_create_notification_is_actionable_for_course_assigned(self, mock_ws):
        notif = services.create_notification(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="COURSE_ASSIGNED",
            title="New Course",
            message="You have a new course",
        )
        self.assertTrue(notif.is_actionable)

    @patch("apps.notifications.services.send_realtime_notification")
    def test_create_notification_not_actionable_for_generic(self, mock_ws):
        notif = services.create_notification(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Info",
            message="General info",
        )
        self.assertFalse(notif.is_actionable)

    def test_create_notification_blocks_cross_tenant(self):
        other_tenant = _tenant("Other School", "notif-other", "other", "other@test.com")
        result = services.create_notification(
            tenant=other_tenant,  # different tenant
            teacher=self.teacher,  # teacher belongs to self.tenant
            notification_type="REMINDER",
            title="Cross-tenant",
            message="Should be blocked",
        )
        self.assertIsNone(result)

    @patch("apps.notifications.services.send_realtime_notification")
    def test_create_notification_calls_realtime(self, mock_ws):
        services.create_notification(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="REMINDER",
            title="RT Test",
            message="RT message",
        )
        mock_ws.assert_called_once()


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class CreateBulkNotificationsTestCase(TestCase):
    """Tests for create_bulk_notifications()"""

    def setUp(self):
        self.tenant = _tenant("Bulk Notif School", "notif-bulk", "test", "bulk@test.com")
        self.teacher1 = _user("t1@bulk.com", self.tenant)
        self.teacher2 = _user("t2@bulk.com", self.tenant)

    @patch("apps.notifications.services.send_realtime_notification")
    def test_bulk_creates_notification_for_each_teacher(self, mock_ws):
        results = services.create_bulk_notifications(
            tenant=self.tenant,
            teachers=[self.teacher1, self.teacher2],
            notification_type="REMINDER",
            title="Bulk Reminder",
            message="Everyone gets this",
        )
        self.assertEqual(len(results), 2)

    @patch("apps.notifications.services.send_realtime_notification")
    def test_bulk_filters_cross_tenant_teachers(self, mock_ws):
        other_tenant = _tenant("Other", "notif-ot", "other", "ot@test.com")
        cross_teacher = _user("cross@other.com", other_tenant)
        results = services.create_bulk_notifications(
            tenant=self.tenant,
            teachers=[self.teacher1, cross_teacher],
            notification_type="REMINDER",
            title="Filtered",
            message="Only same tenant",
        )
        # Only teacher1 should get the notification
        self.assertEqual(len(results), 1)

    @patch("apps.notifications.services.send_realtime_notification")
    def test_bulk_returns_empty_for_no_valid_teachers(self, mock_ws):
        other_tenant = _tenant("No Tenant", "notif-none", "noone", "none@test.com")
        cross_teacher = _user("cross2@other.com", other_tenant)
        results = services.create_bulk_notifications(
            tenant=self.tenant,
            teachers=[cross_teacher],
            notification_type="REMINDER",
            title="None",
            message="Empty",
        )
        self.assertEqual(results, [])

    @patch("apps.notifications.services.send_realtime_notification")
    def test_bulk_empty_teacher_list_returns_empty(self, mock_ws):
        results = services.create_bulk_notifications(
            tenant=self.tenant,
            teachers=[],
            notification_type="REMINDER",
            title="Empty",
            message="No teachers",
        )
        self.assertEqual(results, [])


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class NotifyCourseAssignedTestCase(TestCase):
    """Tests for notify_course_assigned()"""

    def setUp(self):
        self.tenant = _tenant("Assigned School", "notif-assigned", "test", "assigned@test.com")
        self.admin = _user("admin@assigned.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@assigned.com", self.tenant)

    @patch("apps.notifications.services.send_realtime_notification")
    def test_notify_course_assigned_creates_notification(self, mock_ws):
        from apps.courses.models import Course
        course = Course.objects.create(
            tenant=self.tenant, title="Assigned Course",
            slug="assigned-course-notif", description="",
            created_by=self.admin, is_published=True, is_active=True,
        )
        results = services.notify_course_assigned(
            tenant=self.tenant,
            teachers=[self.teacher],
            course=course,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].notification_type, "COURSE_ASSIGNED")

    @patch("apps.notifications.services.send_realtime_notification")
    def test_notify_reminder_uses_assignment_due_type(self, mock_ws):
        from apps.progress.models import Assignment
        from apps.courses.models import Course
        course = Course.objects.create(
            tenant=self.tenant, title="Course for Reminder",
            slug="course-reminder-notif", description="",
            created_by=self.admin, is_published=True, is_active=True,
        )
        assignment = Assignment.objects.create(
            tenant=self.tenant, course=course, title="Due Assignment",
            description="Due soon", is_active=True,
        )
        results = services.notify_reminder(
            tenant=self.tenant,
            teachers=[self.teacher],
            subject="Assignment Due",
            message="Your assignment is due soon",
            assignment=assignment,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].notification_type, "ASSIGNMENT_DUE")

    @patch("apps.notifications.services.send_realtime_notification")
    def test_notify_reminder_without_assignment_uses_reminder_type(self, mock_ws):
        results = services.notify_reminder(
            tenant=self.tenant,
            teachers=[self.teacher],
            subject="General Reminder",
            message="Just a reminder",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].notification_type, "REMINDER")
