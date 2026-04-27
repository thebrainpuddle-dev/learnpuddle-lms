# apps/reports/tests_engagement.py
#
# Tests for the admin engagement heatmap endpoint.

from datetime import datetime, timezone as dt_timezone

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Content, Course, Module
from apps.progress.models import TeacherProgress


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "other.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class EngagementHeatmapTests(TestCase):
    """
    Covers:
      - admin gets a 7x24 grid with expected bucket counts
      - cross-tenant activity does NOT bleed into another tenant's heatmap
      - non-admins are rejected (teachers, unauthenticated)
    """

    URL = "/api/reports/engagement/heatmap/"

    def setUp(self):
        self.client = APIClient()

        # Tenant A
        self.tenant_a = Tenant.objects.create(
            name="School A", slug="school-a-heat", subdomain="test",
            email="a@a.com", is_active=True,
        )
        self.admin_a = User.objects.create_user(
            email="admin_a@a.com", password="admin123",
            first_name="A", last_name="Admin",
            tenant=self.tenant_a, role="SCHOOL_ADMIN",
        )
        self.teacher_a = User.objects.create_user(
            email="teach_a@a.com", password="teacher123",
            first_name="T", last_name="A",
            tenant=self.tenant_a, role="TEACHER",
        )
        self.course_a = Course.objects.create(
            tenant=self.tenant_a, title="Course A", slug="course-a-heat",
            description="x", created_by=self.admin_a,
            is_published=True, is_active=True, assigned_to_all=True,
        )
        mod_a = Module.objects.create(
            course=self.course_a, title="M1", description="", order=1, is_active=True,
        )
        self.content_a = Content.objects.create(
            module=mod_a, title="C1", content_type="TEXT", order=1,
            text_content="x", is_active=True,
        )

        # Tenant B — isolated
        self.tenant_b = Tenant.objects.create(
            name="School B", slug="school-b-heat", subdomain="other",
            email="b@b.com", is_active=True,
        )
        self.admin_b = User.objects.create_user(
            email="admin_b@b.com", password="admin123",
            first_name="B", last_name="Admin",
            tenant=self.tenant_b, role="SCHOOL_ADMIN",
        )
        self.teacher_b = User.objects.create_user(
            email="teach_b@b.com", password="teacher123",
            first_name="T", last_name="B",
            tenant=self.tenant_b, role="TEACHER",
        )
        self.course_b = Course.objects.create(
            tenant=self.tenant_b, title="Course B", slug="course-b-heat",
            description="x", created_by=self.admin_b,
            is_published=True, is_active=True, assigned_to_all=True,
        )
        mod_b = Module.objects.create(
            course=self.course_b, title="M1B", description="", order=1, is_active=True,
        )
        self.content_b = Content.objects.create(
            module=mod_b, title="C1B", content_type="TEXT", order=1,
            text_content="x", is_active=True,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _login(self, email: str, password: str, host: str):
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": email, "password": password},
            HTTP_HOST=host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _make_progress(self, *, tenant, teacher, course, content, when):
        """
        Create a TeacherProgress and override the auto_now `last_accessed`
        to the desired timestamp via an UPDATE (auto_now fires on save).
        """
        tp = TeacherProgress.objects.create(
            tenant=tenant, teacher=teacher, course=course, content=content,
            status="IN_PROGRESS", progress_percentage=10,
            started_at=when,
        )
        TeacherProgress.all_objects.filter(pk=tp.pk).update(last_accessed=when)
        return tp

    # ── tests ────────────────────────────────────────────────────────────

    def test_admin_sees_buckets_aggregated_for_own_tenant(self):
        # Two events on Monday 09:00 UTC, one on Wednesday 14:00 UTC.
        mon_9 = datetime(2026, 4, 13, 9, 0, tzinfo=dt_timezone.utc)   # Monday
        wed_14 = datetime(2026, 4, 15, 14, 0, tzinfo=dt_timezone.utc)  # Wednesday

        # Build a second teacher + a second content node so we can land
        # three progress rows without tripping the
        # (teacher, course, content) unique_together.
        teacher_a2 = User.objects.create_user(
            email="teach_a2@a.com", password="teacher123",
            first_name="T2", last_name="A",
            tenant=self.tenant_a, role="TEACHER",
        )
        mod2 = Module.objects.create(
            course=self.course_a, title="M2", description="", order=2, is_active=True,
        )
        content_a2 = Content.objects.create(
            module=mod2, title="C2", content_type="TEXT", order=1,
            text_content="x", is_active=True,
        )

        # Monday 09:00 UTC — teacher_a on content_a
        self._make_progress(
            tenant=self.tenant_a, teacher=self.teacher_a,
            course=self.course_a, content=self.content_a, when=mon_9,
        )
        # Monday 09:00 UTC — teacher_a2 on content_a (different row)
        self._make_progress(
            tenant=self.tenant_a, teacher=teacher_a2,
            course=self.course_a, content=self.content_a, when=mon_9,
        )
        # Wednesday 14:00 UTC — teacher_a on content_a2 (different row)
        self._make_progress(
            tenant=self.tenant_a, teacher=self.teacher_a,
            course=self.course_a, content=content_a2, when=wed_14,
        )

        self._login("admin_a@a.com", "admin123", "test.lms.com")
        resp = self.client.get(
            self.URL + "?start=2026-04-01&end=2026-04-30&tz=UTC",
            HTTP_HOST="test.lms.com",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.data

        self.assertEqual(body["timezone"], "UTC")
        self.assertFalse(body["tz_fallback"])
        self.assertEqual(len(body["cells"]), 7 * 24)
        self.assertEqual(body["total_events"], 3)

        cell_index = {(c["day"], c["hour"]): c["count"] for c in body["cells"]}
        self.assertEqual(cell_index[(0, 9)], 2)   # Monday 09:00 UTC
        self.assertEqual(cell_index[(2, 14)], 1)  # Wednesday 14:00 UTC
        self.assertEqual(body["max_cell"], 2)

    def test_cross_tenant_isolation(self):
        """Tenant B's activity must not appear in Tenant A's heatmap."""
        when = datetime(2026, 4, 13, 9, 0, tzinfo=dt_timezone.utc)
        # Tenant B has 5 events, tenant A has none.
        for i in range(5):
            mod = Module.objects.create(
                course=self.course_b, title=f"M{i}", description="",
                order=i + 1, is_active=True,
            )
            content = Content.objects.create(
                module=mod, title=f"C{i}", content_type="TEXT", order=1,
                text_content="x", is_active=True,
            )
            self._make_progress(
                tenant=self.tenant_b, teacher=self.teacher_b,
                course=self.course_b, content=content, when=when,
            )

        self._login("admin_a@a.com", "admin123", "test.lms.com")
        resp = self.client.get(
            self.URL + "?start=2026-04-01&end=2026-04-30",
            HTTP_HOST="test.lms.com",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["total_events"], 0)
        self.assertTrue(all(c["count"] == 0 for c in resp.data["cells"]))

    def test_rejects_non_admin(self):
        """Teachers must not be able to hit this endpoint."""
        self._login("teach_a@a.com", "teacher123", "test.lms.com")
        resp = self.client.get(self.URL, HTTP_HOST="test.lms.com")
        self.assertIn(resp.status_code, (401, 403))

    def test_invalid_tz_falls_back_to_utc(self):
        self._login("admin_a@a.com", "admin123", "test.lms.com")
        resp = self.client.get(
            self.URL + "?tz=Not/AZone",
            HTTP_HOST="test.lms.com",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["timezone"], "UTC")
        self.assertTrue(resp.data["tz_fallback"])
