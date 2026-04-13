# apps/reminders/tests_extended.py
#
# Supplementary tests for the reminders app.
# These extend (do NOT modify) the existing tests.py.

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.models import Assignment
from apps.reminders.models import ReminderCampaign
from apps.reminders.services import run_automated_course_deadline_reminders
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Shared base class
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class RemindersExtendedTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Reminder School",
            slug="reminder-school-ext",
            subdomain="test",
            email="t@t.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@reminders.test",
            password="admin123",
            first_name="Admin",
            last_name="Reminders",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@reminders.test",
            password="teacher123",
            first_name="Teacher",
            last_name="One",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.teacher2 = User.objects.create_user(
            email="teacher2@reminders.test",
            password="teacher123",
            first_name="Teacher",
            last_name="Two",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Test Course",
            slug="rem-course-ext",
            description="Test",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="",
            order=1,
            is_active=True,
        )
        self.content = Content.objects.create(
            module=self.module,
            title="Lesson 1",
            content_type="TEXT",
            order=1,
            text_content="<p>Text</p>",
            is_active=True,
        )
        self.assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            module=self.module,
            content=self.content,
            title="Test Assignment",
            description="",
            generation_source="MANUAL",
            is_mandatory=True,
            is_active=True,
        )
        self.client.force_authenticate(user=self.admin)

    def _post(self, url, data, **kwargs):
        return self.client.post(url, data, format="json", HTTP_HOST="test.lms.com", **kwargs)

    def _get(self, url, **kwargs):
        return self.client.get(url, HTTP_HOST="test.lms.com", **kwargs)


# ---------------------------------------------------------------------------
# 1. Unauthenticated access
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class RemindersAuthTestCase(TestCase):
    """Unauthenticated requests must be rejected with 401."""

    def setUp(self):
        self.client = APIClient()
        # Deliberately do NOT authenticate.

    def test_preview_unauthenticated_returns_401(self):
        resp = self.client.post(
            "/api/reminders/preview/",
            {"reminder_type": "CUSTOM", "subject": "x", "message": "y"},
            format="json",
            HTTP_HOST="test.lms.com",
        )
        self.assertEqual(resp.status_code, 401)

    def test_send_unauthenticated_returns_401(self):
        resp = self.client.post(
            "/api/reminders/send/",
            {"reminder_type": "CUSTOM", "subject": "x", "message": "y"},
            format="json",
            HTTP_HOST="test.lms.com",
        )
        self.assertEqual(resp.status_code, 401)

    def test_history_unauthenticated_returns_401(self):
        resp = self.client.get(
            "/api/reminders/history/",
            HTTP_HOST="test.lms.com",
        )
        self.assertEqual(resp.status_code, 401)

    def test_automation_status_unauthenticated_returns_401(self):
        resp = self.client.get(
            "/api/reminders/automation-status/",
            HTTP_HOST="test.lms.com",
        )
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# 2. ASSIGNMENT_DUE reminders
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class AssignmentDueReminderTestCase(RemindersExtendedTestBase):
    """Tests for ASSIGNMENT_DUE reminder preview behaviour."""

    def test_assignment_due_preview_with_valid_assignment_id_returns_200(self):
        resp = self._post(
            "/api/reminders/preview/",
            {
                "reminder_type": "ASSIGNMENT_DUE",
                "assignment_id": str(self.assignment.id),
                "subject": "Please submit",
                "message": "Deadline approaching",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["recipient_count"], 1)

    def test_assignment_due_preview_without_assignment_id_returns_400_or_404(self):
        resp = self._post(
            "/api/reminders/preview/",
            {
                "reminder_type": "ASSIGNMENT_DUE",
                # assignment_id intentionally omitted
                "subject": "Missing id",
                "message": "Should fail",
            },
        )
        # The view calls get_object_or_404 when assignment_id is None/missing,
        # which results in a 404.  Some validation paths may return 400.
        self.assertIn(resp.status_code, [400, 404])

    def test_assignment_due_is_not_locked(self):
        """ASSIGNMENT_DUE is NOT in LOCKED_MANUAL_REMINDER_TYPES; preview should return 200."""
        resp = self._post(
            "/api/reminders/preview/",
            {
                "reminder_type": "ASSIGNMENT_DUE",
                "assignment_id": str(self.assignment.id),
            },
        )
        # Must NOT be 403 (locked)
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 200)

    def test_assignment_due_preview_returns_resolved_subject(self):
        resp = self._post(
            "/api/reminders/preview/",
            {
                "reminder_type": "ASSIGNMENT_DUE",
                "assignment_id": str(self.assignment.id),
            },
        )
        self.assertEqual(resp.status_code, 200)
        # When no subject is provided the service auto-builds one containing the title.
        self.assertIn("resolved_subject", resp.data)
        self.assertIn(self.assignment.title, resp.data["resolved_subject"])


# ---------------------------------------------------------------------------
# 3. Send to all teachers (CUSTOM with no teacher_ids)
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class SendToAllTeachersTestCase(RemindersExtendedTestBase):
    """When no teacher_ids are specified the campaign targets all tenant teachers."""

    def test_custom_send_no_teacher_ids_targets_all_teachers(self):
        resp = self._post(
            "/api/reminders/send/",
            {
                "reminder_type": "CUSTOM",
                "subject": "Broadcast message",
                "message": "Hello everyone",
                # teacher_ids intentionally omitted → all teachers
            },
        )
        self.assertEqual(resp.status_code, 200)
        # Both self.teacher and self.teacher2 are active TEACHER role users on the tenant.
        self.assertEqual(resp.data["sent"], 2)

    def test_custom_send_empty_teacher_ids_targets_all_teachers(self):
        """Passing an empty list for teacher_ids should not filter recipients."""
        resp = self._post(
            "/api/reminders/send/",
            {
                "reminder_type": "CUSTOM",
                "subject": "Broadcast",
                "message": "Hello",
                "teacher_ids": [],
            },
        )
        self.assertEqual(resp.status_code, 200)
        # An empty list means the teacher_ids branch is skipped; all teachers are targeted.
        self.assertEqual(resp.data["sent"], 2)

    def test_campaign_source_is_manual(self):
        resp = self._post(
            "/api/reminders/send/",
            {
                "reminder_type": "CUSTOM",
                "subject": "Manual broadcast",
                "message": "Check the LMS",
            },
        )
        self.assertEqual(resp.status_code, 200)
        campaign = ReminderCampaign.all_objects.get(id=resp.data["campaign"]["id"])
        self.assertEqual(campaign.source, "MANUAL")

    def test_delivery_count_equals_recipient_count(self):
        resp = self._post(
            "/api/reminders/send/",
            {
                "reminder_type": "CUSTOM",
                "subject": "Delivery check",
                "message": "Count matches",
            },
        )
        self.assertEqual(resp.status_code, 200)
        campaign = ReminderCampaign.all_objects.get(id=resp.data["campaign"]["id"])
        self.assertEqual(campaign.deliveries.count(), resp.data["sent"])


# ---------------------------------------------------------------------------
# 4. No valid recipients — cross-tenant teacher_ids
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class NoRecipientsTestCase(RemindersExtendedTestBase):
    """Providing teacher_ids from a different tenant must yield 400 (no valid recipients)."""

    def setUp(self):
        super().setUp()
        # Create a second tenant with its own teacher.
        self.other_tenant = Tenant.objects.create(
            name="Other School",
            slug="other-school-ext",
            subdomain="other",
            email="other@t.com",
            is_active=True,
        )
        self.other_teacher = User.objects.create_user(
            email="other_teacher@other.test",
            password="other123",
            first_name="Other",
            last_name="Teacher",
            tenant=self.other_tenant,
            role="TEACHER",
            is_active=True,
        )

    def test_send_with_cross_tenant_teacher_ids_returns_400(self):
        """
        When all provided teacher_ids belong to a different tenant the
        defense-in-depth tenant filter leaves the recipient list empty → 400.
        """
        resp = self._post(
            "/api/reminders/send/",
            {
                "reminder_type": "CUSTOM",
                "subject": "Cross-tenant attempt",
                "message": "Should be rejected",
                "teacher_ids": [str(self.other_teacher.id)],
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)

    def test_send_with_cross_tenant_ids_creates_no_campaign(self):
        """No ReminderCampaign must be created when recipient validation fails."""
        initial_count = ReminderCampaign.all_objects.filter(tenant=self.tenant).count()
        self._post(
            "/api/reminders/send/",
            {
                "reminder_type": "CUSTOM",
                "subject": "No campaign",
                "message": "Empty recipients",
                "teacher_ids": [str(self.other_teacher.id)],
            },
        )
        self.assertEqual(
            ReminderCampaign.all_objects.filter(tenant=self.tenant).count(),
            initial_count,
        )


# ---------------------------------------------------------------------------
# 5. Reminder history
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ReminderHistoryTestCase(RemindersExtendedTestBase):
    """Tests for the GET /api/reminders/history/ endpoint."""

    def test_history_empty_initially_returns_200(self):
        resp = self._get("/api/reminders/history/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["results"], [])

    def test_history_shows_campaign_after_send(self):
        # Send a reminder first.
        send_resp = self._post(
            "/api/reminders/send/",
            {
                "reminder_type": "CUSTOM",
                "subject": "History test",
                "message": "Verify history",
                "teacher_ids": [str(self.teacher.id)],
            },
        )
        self.assertEqual(send_resp.status_code, 200)
        campaign_id = send_resp.data["campaign"]["id"]

        # Now fetch the history.
        history_resp = self._get("/api/reminders/history/")
        self.assertEqual(history_resp.status_code, 200)
        result_ids = [str(r["id"]) for r in history_resp.data["results"]]
        self.assertIn(str(campaign_id), result_ids)

    def test_history_tenant_isolation(self):
        """Campaigns belonging to another tenant must not appear in the current tenant's history."""
        # Create a second tenant and directly create a campaign for it.
        other_tenant = Tenant.objects.create(
            name="Isolated School",
            slug="isolated-school-ext",
            subdomain="isolated",
            email="iso@t.com",
            is_active=True,
        )
        # Create a campaign directly without going through the view so we can
        # set the tenant explicitly regardless of middleware.
        ReminderCampaign.all_objects.create(
            tenant=other_tenant,
            reminder_type="CUSTOM",
            subject="Other tenant campaign",
            message="Should not appear",
            source="MANUAL",
            automation_key="",
        )

        # Fetch history as the admin of the first tenant.
        resp = self._get("/api/reminders/history/")
        self.assertEqual(resp.status_code, 200)
        for result in resp.data["results"]:
            # None of the returned campaigns should belong to the other tenant.
            campaign_obj = ReminderCampaign.all_objects.get(id=result["id"])
            self.assertEqual(campaign_obj.tenant_id, self.tenant.id)


# ---------------------------------------------------------------------------
# 6. Automation status with courses having deadlines
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class AutomationStatusWithCoursesTestCase(RemindersExtendedTestBase):
    """Tests for GET /api/reminders/automation-status/ with realistic course deadlines."""

    def test_course_with_near_deadline_counted_in_upcoming(self):
        """A course whose deadline falls within the lead-day horizon is counted."""
        self.course.deadline = timezone.localdate() + timedelta(days=3)
        self.course.save()

        resp = self._get("/api/reminders/automation-status/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["upcoming_courses_count"], 1)

    def test_course_with_far_future_deadline_not_counted(self):
        """A course with a deadline 5 years away is outside the horizon and not counted."""
        self.course.deadline = timezone.localdate() + timedelta(days=5 * 365)
        self.course.save()

        resp = self._get("/api/reminders/automation-status/")
        self.assertEqual(resp.status_code, 200)
        # The far-future course must NOT be included in upcoming_courses_count.
        # (Other tests may not run in isolation so we verify this course is absent
        #  by ensuring upcoming_courses_count hasn't been inflated by this course.
        #  We set deadline to a value outside any reasonable lead-day window.)
        # We can directly verify by checking it equals 0 given clean setUp.
        self.assertEqual(resp.data["upcoming_courses_count"], 0)

    def test_automation_status_last_run_at_populated_after_automated_reminder(self):
        """After running the automated reminder service last_run_at is non-null."""
        # Ensure the course has a deadline that falls within the lead window so
        # that the automation service creates a campaign.
        self.course.deadline = timezone.localdate() + timedelta(days=3)
        self.course.save()

        # Before automation: last_run_at should be None (no campaigns yet).
        resp_before = self._get("/api/reminders/automation-status/")
        self.assertEqual(resp_before.status_code, 200)
        self.assertIsNone(resp_before.data["last_run_at"])

        # Run automated reminders (the tenant needs feature_reminders=True which is the default).
        self.tenant.feature_reminders = True
        self.tenant.save()
        run_automated_course_deadline_reminders(run_date=timezone.localdate())

        # After automation: last_run_at should be populated.
        resp_after = self._get("/api/reminders/automation-status/")
        self.assertEqual(resp_after.status_code, 200)
        self.assertIsNotNone(resp_after.data["last_run_at"])

    def test_automation_status_enabled_field_present(self):
        resp = self._get("/api/reminders/automation-status/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("enabled", resp.data)

    def test_automation_status_locked_manual_types_contains_course_deadline(self):
        resp = self._get("/api/reminders/automation-status/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("COURSE_DEADLINE", resp.data.get("locked_manual_types", []))

    def test_automation_status_no_deadline_course_not_counted(self):
        """A course without a deadline must not appear in upcoming_courses_count."""
        # The course created in setUp has no deadline by default.
        resp = self._get("/api/reminders/automation-status/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["upcoming_courses_count"], 0)
