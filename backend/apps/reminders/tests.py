# apps/reminders/tests.py

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.models import TeacherProgress
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.reminders.models import ReminderCampaign
from apps.reminders.services import run_automated_course_deadline_reminders


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"], PLATFORM_DOMAIN="lms.com")
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
        self.completed_teacher = User.objects.create_user(
            email="completed@test.com", password="teacher123",
            first_name="C", last_name="Done", tenant=self.tenant, role="TEACHER",
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Automation Course",
            description="Course with deadline",
            is_published=True,
            assigned_to_all=True,
            deadline=timezone.localdate() + timedelta(days=3),
            created_by=self.admin,
        )
        self.module = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="Test",
            order=1,
            is_active=True,
        )
        self.lesson = Content.objects.create(
            module=self.module,
            title="Lesson 1",
            content_type="TEXT",
            order=1,
            text_content="<p>Welcome</p>",
            is_active=True,
        )
        TeacherProgress.objects.create(
            teacher=self.completed_teacher,
            course=self.course,
            content=self.lesson,
            status="COMPLETED",
            progress_percentage=100,
            started_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now() - timedelta(days=1),
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

    def test_course_deadline_preview_is_locked_for_manual_send(self):
        resp = self.client.post("/api/reminders/preview/", {
            "reminder_type": "COURSE_DEADLINE",
            "course_id": str(self.course.id),
        }, format="json", HTTP_HOST="test.lms.com")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.data.get("locked"))

    def test_course_deadline_send_is_locked_for_manual_send(self):
        resp = self.client.post("/api/reminders/send/", {
            "reminder_type": "COURSE_DEADLINE",
            "course_id": str(self.course.id),
        }, format="json", HTTP_HOST="test.lms.com")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.data.get("locked"))

    def test_reminder_history(self):
        resp = self.client.get("/api/reminders/history/", HTTP_HOST="test.lms.com")
        self.assertEqual(resp.status_code, 200)

    def test_automation_status_endpoint(self):
        resp = self.client.get("/api/reminders/automation-status/", HTTP_HOST="test.lms.com")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data.get("enabled"))
        self.assertIn("COURSE_DEADLINE", resp.data.get("locked_manual_types", []))

    def test_custom_send_targets_selected_teacher(self):
        resp = self.client.post("/api/reminders/send/", {
            "reminder_type": "CUSTOM",
            "subject": "Custom ping",
            "message": "Please check your dashboard.",
            "teacher_ids": [str(self.teacher.id)],
        }, format="json", HTTP_HOST="test.lms.com")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["sent"], 1)
        campaign = ReminderCampaign.objects.get(id=resp.data["campaign"]["id"])
        self.assertEqual(campaign.source, "MANUAL")
        self.assertEqual(campaign.deliveries.count(), 1)
        self.assertEqual(str(campaign.deliveries.first().teacher_id), str(self.teacher.id))

    def test_automated_course_deadline_sends_once_and_skips_completed_teachers(self):
        summary = run_automated_course_deadline_reminders(run_date=timezone.localdate())
        self.assertEqual(summary["created_campaigns"], 1)

        campaign = ReminderCampaign.objects.filter(source="AUTOMATED", reminder_type="COURSE_DEADLINE").first()
        self.assertIsNotNone(campaign)
        delivery_teacher_ids = {str(tid) for tid in campaign.deliveries.values_list("teacher_id", flat=True)}
        self.assertIn(str(self.teacher.id), delivery_teacher_ids)
        self.assertNotIn(str(self.completed_teacher.id), delivery_teacher_ids)

        # Running again on the same day must not duplicate due to automation_key locking.
        second_summary = run_automated_course_deadline_reminders(run_date=timezone.localdate())
        self.assertEqual(second_summary["created_campaigns"], 0)
        self.assertEqual(ReminderCampaign.objects.filter(source="AUTOMATED", reminder_type="COURSE_DEADLINE").count(), 1)

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
