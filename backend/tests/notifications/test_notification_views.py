# tests/notifications/test_notification_views.py
"""
Tests for in-app notification endpoints.

Covers:
- GET  /api/v1/notifications/               — list notifications
- GET  /api/v1/notifications/unread-count/  — unread count
- POST /api/v1/notifications/<id>/read/     — mark single as read
- POST /api/v1/notifications/mark-read/     — bulk mark read
- POST /api/v1/notifications/mark-all-read/ — mark all read
- POST /api/v1/notifications/<id>/archive/  — archive notification

Security:
- Requires authentication
- Tenant isolation: teachers only see their own tenant's notifications
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.notifications.models import Notification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"{subdomain}@example.com", is_active=True,
    )


def _make_user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="Test", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _make_notification(tenant, teacher, title="Test Notif", notif_type="SYSTEM",
                       is_read=False, is_archived=False):
    n = Notification(
        tenant=tenant,
        teacher=teacher,
        notification_type=notif_type,
        title=title,
        message="Test notification message",
        is_read=is_read,
        is_archived=is_archived,
    )
    n.save()
    return n


def _client_for(user, tenant_subdomain):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


def _anon_client(tenant_subdomain):
    c = APIClient()
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


# ===========================================================================
# 1. Notification List
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class NotificationListTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Notif School", "notif")
        self.teacher = _make_user("teacher@notif.com", self.tenant)
        self.admin = _make_user("admin@notif.com", self.tenant, role="SCHOOL_ADMIN")

    def test_list_requires_authentication(self):
        c = _anon_client("notif")
        r = c.get("/api/v1/notifications/")
        self.assertEqual(r.status_code, 401)

    def test_list_returns_200_for_teacher(self):
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/")
        self.assertEqual(r.status_code, 200)

    def test_list_returns_200_for_admin(self):
        c = _client_for(self.admin, "notif")
        r = c.get("/api/v1/notifications/")
        self.assertEqual(r.status_code, 200)

    def test_list_returns_empty_when_no_notifications(self):
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/")
        self.assertEqual(r.data, [])

    def test_list_returns_notifications_for_current_user(self):
        _make_notification(self.tenant, self.teacher, title="My Notification")
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/")
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["title"], "My Notification")

    def test_list_does_not_return_other_users_notifications(self):
        other = _make_user("other@notif.com", self.tenant)
        _make_notification(self.tenant, other, title="Other User's Notif")
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/")
        self.assertEqual(r.data, [])

    def test_list_filters_by_unread_only(self):
        _make_notification(self.tenant, self.teacher, title="Unread", is_read=False)
        _make_notification(self.tenant, self.teacher, title="Read", is_read=True)
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/?unread_only=true")
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["title"], "Unread")

    def test_list_filters_by_type(self):
        _make_notification(self.tenant, self.teacher, title="Reminder", notif_type="REMINDER")
        _make_notification(self.tenant, self.teacher, title="System", notif_type="SYSTEM")
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/?type=REMINDER")
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["title"], "Reminder")

    def test_list_excludes_archived_notifications(self):
        """Archived notifications must not appear in the default list."""
        _make_notification(self.tenant, self.teacher, title="Active Notif", is_archived=False)
        _make_notification(self.tenant, self.teacher, title="Archived Notif", is_archived=True)
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/")
        titles = [n["title"] for n in r.data]
        self.assertIn("Active Notif", titles)
        self.assertNotIn("Archived Notif", titles)

    def test_list_respects_limit_parameter(self):
        for i in range(5):
            _make_notification(self.tenant, self.teacher, title=f"Notif {i}")
        c = _client_for(self.teacher, "notif")
        r = c.get("/api/v1/notifications/?limit=2")
        self.assertEqual(len(r.data), 2)


# ===========================================================================
# 2. Unread Count
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class NotificationUnreadCountTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Count School", "countnotif")
        self.teacher = _make_user("teacher@countnotif.com", self.tenant)

    def test_unread_count_requires_authentication(self):
        c = _anon_client("countnotif")
        r = c.get("/api/v1/notifications/unread-count/")
        self.assertEqual(r.status_code, 401)

    def test_unread_count_returns_200(self):
        c = _client_for(self.teacher, "countnotif")
        r = c.get("/api/v1/notifications/unread-count/")
        self.assertEqual(r.status_code, 200)

    def test_unread_count_is_zero_with_no_notifications(self):
        c = _client_for(self.teacher, "countnotif")
        r = c.get("/api/v1/notifications/unread-count/")
        self.assertEqual(r.data["count"], 0)

    def test_unread_count_reflects_unread_notifications(self):
        _make_notification(self.tenant, self.teacher, is_read=False)
        _make_notification(self.tenant, self.teacher, is_read=False)
        _make_notification(self.tenant, self.teacher, is_read=True)  # Should not count
        c = _client_for(self.teacher, "countnotif")
        r = c.get("/api/v1/notifications/unread-count/")
        self.assertEqual(r.data["count"], 2)

    def test_unread_count_only_counts_own_notifications(self):
        other = _make_user("other@countnotif.com", self.tenant)
        _make_notification(self.tenant, other, is_read=False)  # Other user's
        c = _client_for(self.teacher, "countnotif")
        r = c.get("/api/v1/notifications/unread-count/")
        self.assertEqual(r.data["count"], 0)


# ===========================================================================
# 3. Mark Read
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class NotificationMarkReadTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Read School", "readnotif")
        self.teacher = _make_user("teacher@readnotif.com", self.tenant)
        self.notif = _make_notification(self.tenant, self.teacher, is_read=False)

    def test_mark_read_returns_200(self):
        c = _client_for(self.teacher, "readnotif")
        r = c.post(f"/api/v1/notifications/{self.notif.id}/read/")
        self.assertEqual(r.status_code, 200)

    def test_mark_read_sets_is_read_true(self):
        c = _client_for(self.teacher, "readnotif")
        c.post(f"/api/v1/notifications/{self.notif.id}/read/")
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

    def test_mark_read_requires_authentication(self):
        c = _anon_client("readnotif")
        r = c.post(f"/api/v1/notifications/{self.notif.id}/read/")
        self.assertEqual(r.status_code, 401)

    def test_mark_nonexistent_notification_returns_404(self):
        import uuid
        c = _client_for(self.teacher, "readnotif")
        r = c.post(f"/api/v1/notifications/{uuid.uuid4()}/read/")
        self.assertEqual(r.status_code, 404)

    def test_mark_all_read_returns_200(self):
        _make_notification(self.tenant, self.teacher, is_read=False)
        _make_notification(self.tenant, self.teacher, is_read=False)
        c = _client_for(self.teacher, "readnotif")
        r = c.post("/api/v1/notifications/mark-all-read/")
        self.assertEqual(r.status_code, 200)

    def test_mark_all_read_clears_unread_count(self):
        _make_notification(self.tenant, self.teacher, is_read=False)
        _make_notification(self.tenant, self.teacher, is_read=False)
        c = _client_for(self.teacher, "readnotif")
        c.post("/api/v1/notifications/mark-all-read/")
        # Unread count should now be 0
        r = c.get("/api/v1/notifications/unread-count/")
        self.assertEqual(r.data["count"], 0)


# ===========================================================================
# 4. Archive
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class NotificationArchiveTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Archive School", "archivenotif")
        self.teacher = _make_user("teacher@archivenotif.com", self.tenant)
        self.notif = _make_notification(self.tenant, self.teacher)

    def test_archive_returns_200(self):
        c = _client_for(self.teacher, "archivenotif")
        r = c.patch(f"/api/v1/notifications/{self.notif.id}/archive/")
        self.assertEqual(r.status_code, 200)

    def test_archive_sets_is_archived_flag(self):
        c = _client_for(self.teacher, "archivenotif")
        c.patch(f"/api/v1/notifications/{self.notif.id}/archive/")
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_archived)

    def test_archive_sets_archived_at_timestamp(self):
        c = _client_for(self.teacher, "archivenotif")
        c.patch(f"/api/v1/notifications/{self.notif.id}/archive/")
        self.notif.refresh_from_db()
        self.assertIsNotNone(self.notif.archived_at)

    def test_archived_notification_disappears_from_list(self):
        c = _client_for(self.teacher, "archivenotif")
        c.patch(f"/api/v1/notifications/{self.notif.id}/archive/")
        r = c.get("/api/v1/notifications/")
        ids = [n["id"] for n in r.data]
        self.assertNotIn(str(self.notif.id), ids)

    def test_archive_requires_authentication(self):
        c = _anon_client("archivenotif")
        r = c.patch(f"/api/v1/notifications/{self.notif.id}/archive/")
        self.assertEqual(r.status_code, 401)


# ===========================================================================
# 5. Cross-Tenant Isolation
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class NotificationCrossTenantTestCase(TestCase):
    """
    A teacher from Tenant A must not see or act on Tenant B's notifications.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Alpha School", "alphanotif")
        self.teacher_a = _make_user("teacher@alphanotif.com", self.tenant_a)
        self.notif_a = _make_notification(self.tenant_a, self.teacher_a, title="Alpha Notif")

        self.tenant_b = _make_tenant("Beta School", "betanotif")
        self.teacher_b = _make_user("teacher@betanotif.com", self.tenant_b)
        self.notif_b = _make_notification(self.tenant_b, self.teacher_b, title="Beta Notif")

    def test_teacher_a_cannot_list_tenant_b_notifications_via_cross_host(self):
        """Teacher A using tenant B's host must be denied."""
        c = APIClient()
        c.force_authenticate(user=self.teacher_a)
        c.defaults["HTTP_HOST"] = "betanotif.lms.com"
        r = c.get("/api/v1/notifications/")
        self.assertEqual(r.status_code, 403)

    def test_teacher_a_list_does_not_contain_tenant_b_notifications(self):
        c = _client_for(self.teacher_a, "alphanotif")
        r = c.get("/api/v1/notifications/")
        titles = [n["title"] for n in r.data]
        self.assertNotIn("Beta Notif", titles)

    def test_teacher_a_cannot_mark_read_tenant_b_notification(self):
        """Teacher A must not be able to mark Tenant B's notification as read."""
        c = _client_for(self.teacher_a, "alphanotif")
        r = c.post(f"/api/v1/notifications/{self.notif_b.id}/read/")
        # Should be 404 (not found in their tenant) or 403
        self.assertIn(r.status_code, [403, 404])
        # Notification B must remain unread
        self.notif_b.refresh_from_db()
        self.assertFalse(self.notif_b.is_read)


# ===========================================================================
# 6. Serializer FK fields (course_title / assignment_title) + select_related
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class NotificationSerializerFieldsTestCase(TestCase):
    """
    Verify that course_title and assignment_title serialize correctly and that
    select_related prevents N+1 queries on the notification list endpoint.

    Covers the select_related fix in notification_list (2026-04-22 backend-engineer
    entry, Fix 5 — N+1 in notification_list).
    """

    def setUp(self):
        self.tenant = _make_tenant("Fields School", "fieldsnotif")
        self.admin = _make_user(
            f"admin@{self.tenant.subdomain}.com", self.tenant, role="SCHOOL_ADMIN"
        )
        self.teacher = _make_user(
            f"teacher@{self.tenant.subdomain}.com", self.tenant, role="TEACHER"
        )

    def _client(self):
        return _client_for(self.teacher, self.tenant.subdomain)

    def _make_course(self, title="FK Test Course"):
        from apps.courses.models import Course
        import uuid as _uuid
        slug = f"fk-test-{_uuid.uuid4().hex[:6]}"
        return Course.objects.create(
            tenant=self.tenant,
            title=title,
            slug=slug,
            description="Test",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )

    def _make_assignment(self, course, title="FK Test Assignment"):
        from apps.progress.models import Assignment
        return Assignment.all_objects.create(
            tenant=self.tenant,
            course=course,
            title=title,
            description="Test assignment for notification FK test",
            is_active=True,
        )

    def _notif_with_course(self, course, title="Course Notif"):
        n = Notification(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="COURSE_ASSIGNED",
            title=title,
            message="You've been assigned a course",
            course=course,
        )
        n.save()
        return n

    def _notif_with_assignment(self, assignment, title="Assignment Notif"):
        n = Notification(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="ASSIGNMENT_DUE",
            title=title,
            message="An assignment is due",
            assignment=assignment,
        )
        n.save()
        return n

    # -----------------------------------------------------------------------
    # Test 1: course_title returns the linked course's title
    # -----------------------------------------------------------------------

    def test_notification_with_course_returns_correct_course_title(self):
        """
        When a Notification has a course FK, the list response must include
        course_title matching the course's title.
        """
        course = self._make_course("Introduction to Pedagogy")
        self._notif_with_course(course)

        r = self._client().get("/api/v1/notifications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(
            r.data[0]["course_title"],
            "Introduction to Pedagogy",
            f"course_title mismatch: {r.data[0].get('course_title')}",
        )

    # -----------------------------------------------------------------------
    # Test 2: assignment_title returns the linked assignment's title
    # -----------------------------------------------------------------------

    def test_notification_with_assignment_returns_correct_assignment_title(self):
        """
        When a Notification has an assignment FK, the list response must
        include assignment_title matching the assignment's title.
        """
        course = self._make_course("Assessment Course")
        assignment = self._make_assignment(course, "Mid-Year Assessment")
        self._notif_with_assignment(assignment)

        r = self._client().get("/api/v1/notifications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(
            r.data[0]["assignment_title"],
            "Mid-Year Assessment",
            f"assignment_title mismatch: {r.data[0].get('assignment_title')}",
        )

    # -----------------------------------------------------------------------
    # Test 3: null titles when no FK is set
    # -----------------------------------------------------------------------

    def test_notification_without_course_or_assignment_returns_null_titles(self):
        """
        A Notification with no course or assignment FK must return
        course_title=null and assignment_title=null.
        """
        _make_notification(self.tenant, self.teacher, notif_type="SYSTEM")

        r = self._client().get("/api/v1/notifications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertIsNone(
            r.data[0].get("course_title"),
            "Expected course_title=null for a notification without a course FK",
        )
        self.assertIsNone(
            r.data[0].get("assignment_title"),
            "Expected assignment_title=null for a notification without an assignment FK",
        )

    # -----------------------------------------------------------------------
    # Test 4: select_related prevents N+1 queries
    # -----------------------------------------------------------------------

    def test_notification_list_no_n_plus_one_queries(self):
        """
        With 5 notifications each linked to a different course, the query
        count must remain bounded (≤10 total).

        Pre-fix N+1 would produce 5 extra queries for course.title + 5 for
        assignment.title = 10 extra queries for 5 rows.
        Post-fix (select_related): all course/assignment rows fetched in the
        single main query — no extra per-row lookups.
        """
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        for i in range(5):
            course = self._make_course(f"N+1 Test Course {i}")
            self._notif_with_course(course, title=f"N+1 Notif {i}")

        with CaptureQueriesContext(connection) as ctx:
            r = self._client().get("/api/v1/notifications/")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 5)

        # Annotated/select_related: main query + middleware overhead ≤10 total.
        # Old N+1 with 5 rows = 1 + 5 course + 5 assignment = 11+ queries.
        self.assertLessEqual(
            len(ctx.captured_queries),
            10,
            f"Expected ≤10 queries for 5 notifications, got {len(ctx.captured_queries)}. "
            "Possible N+1 regression in notification_list.",
        )
