# apps/notifications/tests_announcements.py
#
# Tests for the announcement endpoints and additional notification edge cases:
#   - Announcement CRUD (admin only)
#   - Bulk mark-read
#   - Unread count with type filter
#   - Notification list edge cases (actionable_only, limit boundary)

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.tenants.models import Tenant
from apps.users.models import User


HOST = "test.lms.com"


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class AnnouncementCreateTestCase(TestCase):
    """Tests for POST /api/notifications/announcements/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Announce School",
            slug="announce-school",
            subdomain="test",
            email="announce@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@announce.test",
            password="admin123",
            first_name="Admin",
            last_name="Ann",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher1 = User.objects.create_user(
            email="teacher1@announce.test",
            password="teacher123",
            first_name="Alice",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.teacher2 = User.objects.create_user(
            email="teacher2@announce.test",
            password="teacher123",
            first_name="Bob",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _auth_admin(self):
        self.client.force_authenticate(user=self.admin)

    def _auth_teacher(self):
        self.client.force_authenticate(user=self.teacher1)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def _get(self, url, **kw):
        return self.client.get(url, HTTP_HOST=HOST, **kw)

    def _delete(self, url, **kw):
        return self.client.delete(url, HTTP_HOST=HOST, **kw)

    # --- Create ---

    def test_admin_can_create_announcement_to_all(self):
        self._auth_admin()
        resp = self._post("/api/notifications/announcements/", {
            "title": "System Update",
            "message": "The platform will be down for maintenance.",
            "target": "all",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["recipient_count"], 2)

    def test_create_announcement_persists_notifications(self):
        self._auth_admin()
        self._post("/api/notifications/announcements/", {
            "title": "Test Announcement",
            "message": "Test message",
            "target": "all",
        })
        count = Notification.objects.filter(
            tenant=self.tenant,
            notification_type="ANNOUNCEMENT",
        ).count()
        self.assertEqual(count, 2)

    def test_create_announcement_missing_title_returns_400(self):
        self._auth_admin()
        resp = self._post("/api/notifications/announcements/", {
            "title": "",
            "message": "Some message",
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_announcement_missing_message_returns_400(self):
        self._auth_admin()
        resp = self._post("/api/notifications/announcements/", {
            "title": "Valid Title",
            "message": "",
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_announcement_title_too_long_returns_400(self):
        self._auth_admin()
        resp = self._post("/api/notifications/announcements/", {
            "title": "x" * 256,
            "message": "Valid message",
        })
        self.assertEqual(resp.status_code, 400)

    def test_teacher_cannot_create_announcement(self):
        self._auth_teacher()
        resp = self._post("/api/notifications/announcements/", {
            "title": "Unauthorized",
            "message": "Not allowed.",
        })
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_cannot_create_announcement(self):
        resp = self._post("/api/notifications/announcements/", {
            "title": "Unauth",
            "message": "Not allowed.",
        })
        self.assertEqual(resp.status_code, 401)

    # --- List ---

    def test_admin_can_list_announcements(self):
        self._auth_admin()
        self._post("/api/notifications/announcements/", {
            "title": "First",
            "message": "First message",
        })
        resp = self._get("/api/notifications/announcements/")
        self.assertEqual(resp.status_code, 200)
        announcements = resp.json()["announcements"]
        self.assertTrue(len(announcements) >= 1)

    def test_announcement_list_contains_expected_fields(self):
        self._auth_admin()
        self._post("/api/notifications/announcements/", {
            "title": "Field Test",
            "message": "Field message",
        })
        resp = self._get("/api/notifications/announcements/")
        a = resp.json()["announcements"][0]
        for field in ("id", "title", "message", "recipient_count", "created_at"):
            self.assertIn(field, a, msg=f"Missing field: {field}")

    def test_teacher_cannot_list_announcements(self):
        self._auth_teacher()
        resp = self._get("/api/notifications/announcements/")
        self.assertEqual(resp.status_code, 403)

    # --- Delete ---

    def test_admin_can_delete_announcement(self):
        self._auth_admin()
        self._post("/api/notifications/announcements/", {
            "title": "Deletable",
            "message": "To be deleted",
        })
        notif = Notification.objects.filter(
            tenant=self.tenant,
            notification_type="ANNOUNCEMENT",
            title="Deletable",
        ).first()
        resp = self._delete(f"/api/notifications/announcements/{notif.id}/")
        self.assertEqual(resp.status_code, 200)
        remaining = Notification.objects.filter(
            tenant=self.tenant,
            notification_type="ANNOUNCEMENT",
            title="Deletable",
        ).count()
        self.assertEqual(remaining, 0)

    def test_delete_nonexistent_announcement_returns_404(self):
        self._auth_admin()
        resp = self._delete(f"/api/notifications/announcements/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)


# ===========================================================================
# Bulk mark-read
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class BulkMarkReadTestCase(TestCase):
    """Tests for POST /api/notifications/mark-read/ (bulk by IDs)."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Bulk School",
            slug="bulk-mark-school",
            subdomain="test",
            email="bulk@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@bulk.test",
            password="bulk123",
            first_name="Bulk",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.notifs = []
        for i in range(5):
            n = Notification.objects.create(
                tenant=self.tenant,
                teacher=self.teacher,
                notification_type="SYSTEM",
                title=f"N{i}",
                message=f"M{i}",
                is_read=False,
            )
            self.notifs.append(n)
        self.client.force_authenticate(user=self.teacher)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_marks_specified_ids_as_read(self):
        ids_to_mark = [str(self.notifs[0].id), str(self.notifs[1].id)]
        resp = self._post("/api/notifications/mark-read/", {"ids": ids_to_mark})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["marked_read"], 2)
        for nid in ids_to_mark:
            self.assertTrue(Notification.objects.get(id=nid).is_read)
        # Others remain unread
        self.assertFalse(Notification.objects.get(id=self.notifs[2].id).is_read)

    def test_empty_ids_returns_400(self):
        resp = self._post("/api/notifications/mark-read/", {"ids": []})
        self.assertEqual(resp.status_code, 400)

    def test_missing_ids_returns_400(self):
        resp = self._post("/api/notifications/mark-read/", {})
        self.assertEqual(resp.status_code, 400)

    def test_ids_not_list_returns_400(self):
        resp = self._post("/api/notifications/mark-read/", {"ids": "not-a-list"})
        self.assertEqual(resp.status_code, 400)

    def test_already_read_ids_return_zero_marked(self):
        """Re-marking already-read notifications should return 0."""
        self.notifs[0].is_read = True
        self.notifs[0].save()
        resp = self._post("/api/notifications/mark-read/", {"ids": [str(self.notifs[0].id)]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["marked_read"], 0)


# ===========================================================================
# Unread count type filter
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class UnreadCountTypeFilterTestCase(TestCase):
    """Tests for GET /api/notifications/unread-count/ with type filter."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Count School",
            slug="count-filter-school",
            subdomain="test",
            email="count@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@count.test",
            password="count123",
            first_name="Count",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        Notification.objects.create(
            tenant=self.tenant, teacher=self.teacher,
            notification_type="SYSTEM", title="S", message="S", is_read=False,
        )
        Notification.objects.create(
            tenant=self.tenant, teacher=self.teacher,
            notification_type="REMINDER", title="R", message="R", is_read=False,
        )
        Notification.objects.create(
            tenant=self.tenant, teacher=self.teacher,
            notification_type="SYSTEM", title="S2", message="S2", is_read=True,
        )
        self.client.force_authenticate(user=self.teacher)

    def _get(self, url, **kw):
        return self.client.get(url, HTTP_HOST=HOST, **kw)

    def test_total_unread_count(self):
        resp = self._get("/api/notifications/unread-count/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_type_filter_system(self):
        resp = self._get("/api/notifications/unread-count/?type=SYSTEM")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)

    def test_type_filter_reminder(self):
        resp = self._get("/api/notifications/unread-count/?type=REMINDER")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)

    def test_invalid_type_returns_total_count(self):
        resp = self._get("/api/notifications/unread-count/?type=INVALID")
        self.assertEqual(resp.status_code, 200)
        # Invalid type should fall through to total count
        self.assertEqual(resp.json()["count"], 2)

    def test_response_includes_actionable_count(self):
        resp = self._get("/api/notifications/unread-count/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("actionable_count", resp.json())


# ===========================================================================
# Notification list edge cases
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class NotificationListEdgeCasesTestCase(TestCase):
    """Edge-case tests for GET /api/notifications/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Edge School",
            slug="edge-notif-school",
            subdomain="test",
            email="edge@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@edge.test",
            password="edge123",
            first_name="Edge",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        for i in range(10):
            Notification.objects.create(
                tenant=self.tenant,
                teacher=self.teacher,
                notification_type="SYSTEM",
                title=f"N{i}",
                message=f"M{i}",
                is_read=False,
            )
        self.client.force_authenticate(user=self.teacher)

    def _get(self, url, **kw):
        return self.client.get(url, HTTP_HOST=HOST, **kw)

    def test_limit_param_caps_results(self):
        resp = self._get("/api/notifications/?limit=3")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 3)

    def test_limit_param_invalid_defaults_to_20(self):
        resp = self._get("/api/notifications/?limit=abc")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 10)  # Only 10 exist

    def test_limit_param_zero_clamps_to_1(self):
        resp = self._get("/api/notifications/?limit=0")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_limit_param_negative_clamps_to_1(self):
        resp = self._get("/api/notifications/?limit=-5")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_unread_only_filter(self):
        # Mark 3 as read
        for n in Notification.objects.filter(teacher=self.teacher)[:3]:
            n.is_read = True
            n.save()
        resp = self._get("/api/notifications/?unread_only=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 7)


# ===========================================================================
# Group-targeted announcements
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class GroupTargetedAnnouncementTestCase(TestCase):
    """Tests for group-targeted announcement creation."""

    def setUp(self):
        from apps.courses.models import TeacherGroup

        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Group Announce School",
            slug="grp-announce-school",
            subdomain="test",
            email="grp@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@grp.test",
            password="admin123",
            first_name="Admin",
            last_name="Grp",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher_in_group = User.objects.create_user(
            email="ingroup@grp.test",
            password="grp123",
            first_name="InGroup",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.teacher_outside_group = User.objects.create_user(
            email="outgroup@grp.test",
            password="grp123",
            first_name="OutGroup",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.group = TeacherGroup.objects.create(
            tenant=self.tenant,
            name="Math Teachers",
            group_type="SUBJECT",
        )
        self.teacher_in_group.teacher_groups.add(self.group)

    def _auth_admin(self):
        self.client.force_authenticate(user=self.admin)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_group_targeted_announcement_only_reaches_group_members(self):
        self._auth_admin()
        resp = self._post("/api/notifications/announcements/", {
            "title": "Math Dept Update",
            "message": "New textbooks arriving.",
            "target": "groups",
            "group_ids": [str(self.group.id)],
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["recipient_count"], 1)
        # Only the in-group teacher should have a notification
        notifs = Notification.objects.filter(
            tenant=self.tenant,
            notification_type="ANNOUNCEMENT",
            title="Math Dept Update",
        )
        self.assertEqual(notifs.count(), 1)
        self.assertEqual(notifs.first().teacher, self.teacher_in_group)

    def test_group_targeted_with_empty_group_returns_400(self):
        """If the group has no members, no announcement should be created."""
        from apps.courses.models import TeacherGroup

        empty_group = TeacherGroup.objects.create(
            tenant=self.tenant,
            name="Empty Group",
            group_type="CUSTOM",
        )
        self._auth_admin()
        resp = self._post("/api/notifications/announcements/", {
            "title": "Nobody",
            "message": "No recipients.",
            "target": "groups",
            "group_ids": [str(empty_group.id)],
        })
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# Single mark-read endpoint
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class SingleMarkReadTestCase(TestCase):
    """Tests for POST /api/notifications/<uuid>/read/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Single Read School",
            slug="single-read-school",
            subdomain="test",
            email="singleread@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@singleread.test",
            password="read123",
            first_name="Single",
            last_name="Read",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.notification = Notification.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Read Me",
            message="Please read this.",
            is_read=False,
        )
        self.client.force_authenticate(user=self.teacher)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_mark_single_notification_read(self):
        resp = self._post(f"/api/notifications/{self.notification.id}/read/")
        self.assertEqual(resp.status_code, 200)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
        self.assertIsNotNone(self.notification.read_at)

    def test_mark_already_read_returns_200(self):
        self.notification.is_read = True
        self.notification.save()
        resp = self._post(f"/api/notifications/{self.notification.id}/read/")
        self.assertEqual(resp.status_code, 200)

    def test_mark_nonexistent_notification_returns_404(self):
        resp = self._post(f"/api/notifications/{uuid.uuid4()}/read/")
        self.assertEqual(resp.status_code, 404)


# ===========================================================================
# Mark-all-read endpoint
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class MarkAllReadTestCase(TestCase):
    """Tests for POST /api/notifications/mark-all-read/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="MarkAll School",
            slug="markall-school",
            subdomain="test",
            email="markall@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@markall.test",
            password="markall123",
            first_name="MarkAll",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        for i in range(5):
            Notification.objects.create(
                tenant=self.tenant,
                teacher=self.teacher,
                notification_type="SYSTEM",
                title=f"N{i}",
                message=f"M{i}",
                is_read=False,
            )
        self.client.force_authenticate(user=self.teacher)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_mark_all_read_marks_all(self):
        resp = self._post("/api/notifications/mark-all-read/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["marked_read"], 5)
        unread_count = Notification.objects.filter(
            teacher=self.teacher, is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_mark_all_read_when_already_read_returns_zero(self):
        Notification.objects.filter(teacher=self.teacher).update(is_read=True)
        resp = self._post("/api/notifications/mark-all-read/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["marked_read"], 0)


# ===========================================================================
# Archive and bulk-archive endpoints
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ArchiveNotificationTestCase(TestCase):
    """Tests for PATCH /api/notifications/<uuid>/archive/ and POST /api/notifications/bulk-archive/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Archive School",
            slug="archive-school",
            subdomain="test",
            email="archive@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@archive.test",
            password="archive123",
            first_name="Archive",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.notifs = []
        for i in range(4):
            n = Notification.objects.create(
                tenant=self.tenant,
                teacher=self.teacher,
                notification_type="SYSTEM",
                title=f"Archive{i}",
                message=f"M{i}",
                is_read=False,
            )
            self.notifs.append(n)
        self.client.force_authenticate(user=self.teacher)

    def _patch(self, url, data=None, **kw):
        return self.client.patch(url, data, format="json", HTTP_HOST=HOST, **kw)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    # --- Single archive ---

    def test_archive_single_notification(self):
        resp = self._patch(f"/api/notifications/{self.notifs[0].id}/archive/")
        self.assertEqual(resp.status_code, 200)
        self.notifs[0].refresh_from_db()
        self.assertTrue(self.notifs[0].is_archived)
        self.assertIsNotNone(self.notifs[0].archived_at)

    def test_archive_already_archived_returns_200(self):
        """Archiving an already-archived notification is idempotent."""
        self.notifs[0].is_archived = True
        self.notifs[0].save()
        resp = self._patch(f"/api/notifications/{self.notifs[0].id}/archive/")
        self.assertEqual(resp.status_code, 200)

    def test_archive_nonexistent_returns_404(self):
        resp = self._patch(f"/api/notifications/{uuid.uuid4()}/archive/")
        self.assertEqual(resp.status_code, 404)

    # --- Bulk archive ---

    def test_bulk_archive_marks_specified(self):
        ids_to_archive = [str(self.notifs[0].id), str(self.notifs[1].id)]
        resp = self._post("/api/notifications/bulk-archive/", {"ids": ids_to_archive})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["archived"], 2)
        for nid in ids_to_archive:
            n = Notification.all_objects.get(id=nid)
            self.assertTrue(n.is_archived)

    def test_bulk_archive_empty_ids_returns_400(self):
        resp = self._post("/api/notifications/bulk-archive/", {"ids": []})
        self.assertEqual(resp.status_code, 400)

    def test_bulk_archive_missing_ids_returns_400(self):
        resp = self._post("/api/notifications/bulk-archive/", {})
        self.assertEqual(resp.status_code, 400)

    def test_bulk_archive_already_archived_returns_zero(self):
        """Re-archiving already-archived notifications should return 0."""
        Notification.all_objects.filter(id=self.notifs[0].id).update(is_archived=True)
        resp = self._post(
            "/api/notifications/bulk-archive/",
            {"ids": [str(self.notifs[0].id)]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["archived"], 0)


# ===========================================================================
# Cross-tenant isolation
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class CrossTenantIsolationTestCase(TestCase):
    """Verify that notification operations are tenant-isolated."""

    def setUp(self):
        self.client = APIClient()
        # Tenant A
        self.tenant_a = Tenant.objects.create(
            name="Tenant A",
            slug="tenant-a",
            subdomain="test",
            email="a@test.com",
            is_active=True,
        )
        self.teacher_a = User.objects.create_user(
            email="teacher@a.test",
            password="a12345",
            first_name="Teacher",
            last_name="A",
            tenant=self.tenant_a,
            role="TEACHER",
            is_active=True,
        )
        self.notif_a = Notification.objects.create(
            tenant=self.tenant_a,
            teacher=self.teacher_a,
            notification_type="SYSTEM",
            title="Tenant A Notif",
            message="For tenant A only",
            is_read=False,
        )
        # Tenant B
        self.tenant_b = Tenant.objects.create(
            name="Tenant B",
            slug="tenant-b",
            subdomain="testb",
            email="b@test.com",
            is_active=True,
        )
        self.teacher_b = User.objects.create_user(
            email="teacher@b.test",
            password="b12345",
            first_name="Teacher",
            last_name="B",
            tenant=self.tenant_b,
            role="TEACHER",
            is_active=True,
        )
        self.notif_b = Notification.objects.create(
            tenant=self.tenant_b,
            teacher=self.teacher_b,
            notification_type="SYSTEM",
            title="Tenant B Notif",
            message="For tenant B only",
            is_read=False,
        )

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_teacher_cannot_mark_read_other_tenant_notification(self):
        """Teacher A should not be able to mark-read a Tenant B notification."""
        self.client.force_authenticate(user=self.teacher_a)
        resp = self._post(f"/api/notifications/{self.notif_b.id}/read/")
        self.assertEqual(resp.status_code, 404)
        # Verify notification remains unread
        self.notif_b.refresh_from_db()
        self.assertFalse(self.notif_b.is_read)

    def test_bulk_mark_read_ignores_other_tenant_ids(self):
        """Bulk mark-read should only affect notifications belonging to the current teacher/tenant."""
        self.client.force_authenticate(user=self.teacher_a)
        resp = self._post("/api/notifications/mark-read/", {
            "ids": [str(self.notif_b.id)],
        })
        self.assertEqual(resp.status_code, 200)
        # Should mark 0 since this notification belongs to tenant B
        self.assertEqual(resp.json()["marked_read"], 0)
        self.notif_b.refresh_from_db()
        self.assertFalse(self.notif_b.is_read)
