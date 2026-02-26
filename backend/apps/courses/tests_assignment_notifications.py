from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.courses.assignment_views import _notify_assignment_created
from apps.courses.models import Course
from apps.courses.serializers import CourseDetailSerializer
from apps.progress.models import Assignment
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"], PLATFORM_DOMAIN="lms.com")
class AssignmentNotificationRulesTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Course School",
            slug="course-school",
            subdomain="course",
            email="admin@course.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@course.com",
            password="admin123",
            first_name="Admin",
            last_name="User",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
        )
        self.teacher_existing = User.objects.create_user(
            email="existing@course.com",
            password="teacher123",
            first_name="Existing",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
        )
        self.teacher_new = User.objects.create_user(
            email="new@course.com",
            password="teacher123",
            first_name="New",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Physics 101",
            description="Course",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=False,
        )
        self.course.assigned_teachers.add(self.teacher_existing)

    @patch("apps.notifications.services.create_bulk_notifications")
    def test_assignment_create_uses_assignment_due_notification(self, mocked_bulk_create):
        assignment = Assignment.objects.create(
            course=self.course,
            title="Quiz 1",
            description="Quiz",
            instructions="Complete quiz",
            is_active=True,
        )

        _notify_assignment_created(self.course, assignment)

        self.assertTrue(mocked_bulk_create.called)
        kwargs = mocked_bulk_create.call_args.kwargs
        self.assertEqual(kwargs["notification_type"], "ASSIGNMENT_DUE")
        self.assertEqual(kwargs["assignment"], assignment)
        self.assertTrue(kwargs["send_email"])

    @patch("apps.notifications.services.notify_course_assigned")
    def test_false_to_true_assigned_to_all_notifies_only_newly_included(self, mocked_notify):
        request = type("Req", (), {"tenant": self.tenant, "user": self.admin})()
        serializer = CourseDetailSerializer(
            instance=self.course,
            data={"assigned_to_all": True},
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        self.assertTrue(mocked_notify.called)
        notified_teachers = mocked_notify.call_args.args[1]
        notified_ids = {str(t.id) for t in notified_teachers}
        self.assertIn(str(self.teacher_new.id), notified_ids)
        self.assertNotIn(str(self.teacher_existing.id), notified_ids)

    @patch("apps.notifications.services.notify_course_assigned")
    def test_true_to_false_assigned_to_all_does_not_blast(self, mocked_notify):
        self.course.assigned_to_all = True
        self.course.save(update_fields=["assigned_to_all"])

        request = type("Req", (), {"tenant": self.tenant, "user": self.admin})()
        serializer = CourseDetailSerializer(
            instance=self.course,
            data={"assigned_to_all": False},
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        mocked_notify.assert_not_called()
