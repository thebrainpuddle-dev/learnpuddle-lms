# apps/notifications/tests_archival.py
"""
Notification archival and lifecycle tests (TASK-009 / TASK-010).

Covers:
- ActiveNotificationManager excludes archived notifications
- all_objects bypass manager reaches archived rows
- archive_old_notifications Celery task (90-day cutoff)
- delete_archived_notifications Celery task (30-day grace window)
- Full notification lifecycle: create -> read -> archive -> delete
- Edge cases: empty DB, already-archived rows not re-stamped, boundary dates
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.notifications.models import Notification, ActiveNotificationManager
from apps.notifications.tasks import (
    archive_old_notifications,
    delete_archived_notifications,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, slug, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=slug, subdomain=subdomain, email=email, is_active=True,
    )


def _make_user(email, tenant, role="TEACHER", first="Test", last="User"):
    return User.objects.create_user(
        email=email, password="pass123",
        first_name=first, last_name=last,
        tenant=tenant, role=role, is_active=True,
    )


def _make_notification(tenant, teacher, title="Test Notification", **kwargs):
    defaults = {
        "notification_type": "SYSTEM",
        "message": "Test message body",
    }
    defaults.update(kwargs)
    return Notification.objects.create(
        tenant=tenant, teacher=teacher, title=title, **defaults,
    )


# ===========================================================================
# 1. ActiveNotificationManager Tests
# ===========================================================================

class ActiveNotificationManagerTestCase(TestCase):
    """
    Verify that the default manager (`Notification.objects`) automatically
    excludes archived notifications, and that `Notification.all_objects`
    bypasses that filter.
    """

    def setUp(self):
        self.tenant = _make_tenant("Mgr School", "mgr-notif", "mgr", "mgr@notif.test")
        self.teacher = _make_user("teacher@mgr.test", self.tenant)

    def test_default_manager_excludes_archived(self):
        """Notification.objects.all() must not include archived rows."""
        active = _make_notification(self.tenant, self.teacher, title="Active")
        archived = _make_notification(
            self.tenant, self.teacher, title="Archived",
            archived_at=timezone.now(),
        )
        # Using all_objects to create, then filter via default manager
        qs = Notification.objects.all()
        ids = set(str(n.id) for n in qs)
        self.assertIn(str(active.id), ids)
        self.assertNotIn(str(archived.id), ids)

    def test_all_objects_includes_archived(self):
        """Notification.all_objects must include both active and archived rows."""
        active = _make_notification(self.tenant, self.teacher, title="Active")
        archived = _make_notification(
            self.tenant, self.teacher, title="Archived",
            archived_at=timezone.now(),
        )
        qs = Notification.all_objects.all()
        ids = set(str(n.id) for n in qs)
        self.assertIn(str(active.id), ids)
        self.assertIn(str(archived.id), ids)

    def test_default_manager_includes_non_archived_only(self):
        """Notifications with archived_at=None should appear in default manager."""
        n = _make_notification(self.tenant, self.teacher, title="Fresh")
        self.assertIsNone(n.archived_at)
        self.assertTrue(
            Notification.objects.filter(id=n.id).exists()
        )

    def test_default_manager_is_instance_of_active_notification_manager(self):
        """Sanity check: Notification.objects is an ActiveNotificationManager."""
        self.assertIsInstance(Notification.objects, ActiveNotificationManager)

    def test_archived_notification_count_zero_in_default_manager(self):
        """When all notifications are archived, default manager returns zero."""
        _make_notification(
            self.tenant, self.teacher, title="A1",
            archived_at=timezone.now() - timedelta(days=5),
        )
        _make_notification(
            self.tenant, self.teacher, title="A2",
            archived_at=timezone.now() - timedelta(days=10),
        )
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(Notification.all_objects.count(), 2)


# ===========================================================================
# 2. archive_old_notifications Task Tests
# ===========================================================================

class ArchiveOldNotificationsTaskTestCase(TestCase):
    """
    Verify the Celery task that archives notifications older than 90 days.
    """

    def setUp(self):
        self.tenant = _make_tenant("Archive School", "arch-notif", "arch", "arch@notif.test")
        self.teacher = _make_user("teacher@arch.test", self.tenant)

    def test_archives_notifications_older_than_90_days(self):
        """Notifications created more than 90 days ago should be archived."""
        old_notif = Notification.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Old Notification",
            message="Created 100 days ago",
        )
        # Manually set created_at to 100 days ago
        Notification.all_objects.filter(id=old_notif.id).update(
            created_at=timezone.now() - timedelta(days=100)
        )

        result = archive_old_notifications()

        self.assertEqual(result["archived"], 1)
        old_notif.refresh_from_db()
        self.assertIsNotNone(old_notif.archived_at)

    def test_does_not_archive_recent_notifications(self):
        """Notifications created less than 90 days ago should NOT be archived."""
        recent = _make_notification(self.tenant, self.teacher, title="Recent")
        # created_at is auto-set to now, so it's < 90 days old

        result = archive_old_notifications()

        self.assertEqual(result["archived"], 0)
        recent.refresh_from_db()
        self.assertIsNone(recent.archived_at)

    def test_does_not_re_stamp_already_archived_notifications(self):
        """Already-archived notifications should NOT have archived_at updated."""
        original_archive_time = timezone.now() - timedelta(days=20)
        old_notif = Notification.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Already Archived",
            message="Archived 20 days ago",
            archived_at=original_archive_time,
        )
        # Set created_at to 100 days ago (older than cutoff)
        Notification.all_objects.filter(id=old_notif.id).update(
            created_at=timezone.now() - timedelta(days=100)
        )

        result = archive_old_notifications()

        # Should not re-archive (archived_at is already set)
        self.assertEqual(result["archived"], 0)
        old_notif.refresh_from_db()
        # archived_at should remain unchanged
        self.assertAlmostEqual(
            old_notif.archived_at.timestamp(),
            original_archive_time.timestamp(),
            delta=1,
        )

    def test_empty_database_archives_zero(self):
        """Task handles empty notification table gracefully."""
        result = archive_old_notifications()
        self.assertEqual(result["archived"], 0)

    def test_boundary_exactly_90_days_old_not_archived(self):
        """Notification created exactly 90 days ago is NOT archived (lt, not lte)."""
        boundary_notif = Notification.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Boundary 90 days",
            message="Exactly 90 days old",
        )
        Notification.all_objects.filter(id=boundary_notif.id).update(
            created_at=timezone.now() - timedelta(days=90)
        )

        result = archive_old_notifications()

        # created_at__lt=cutoff means exactly 90 days does NOT match
        self.assertEqual(result["archived"], 0)
        boundary_notif.refresh_from_db()
        self.assertIsNone(boundary_notif.archived_at)

    def test_91_days_old_is_archived(self):
        """Notification created 91 days ago IS archived."""
        old_notif = Notification.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="91 days old",
            message="Just past the cutoff",
        )
        Notification.all_objects.filter(id=old_notif.id).update(
            created_at=timezone.now() - timedelta(days=91)
        )

        result = archive_old_notifications()

        self.assertEqual(result["archived"], 1)
        old_notif.refresh_from_db()
        self.assertIsNotNone(old_notif.archived_at)

    def test_archives_multiple_notifications_across_tenants(self):
        """Task archives old notifications from all tenants at once."""
        tenant_b = _make_tenant("School B", "arch-b", "archb", "b@archnotif.test")
        teacher_b = _make_user("teacher@archb.test", tenant_b)

        notif_a = Notification.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            notification_type="SYSTEM", title="Old A", message="Msg",
        )
        notif_b = Notification.all_objects.create(
            tenant=tenant_b, teacher=teacher_b,
            notification_type="SYSTEM", title="Old B", message="Msg",
        )
        # Both are 120 days old
        Notification.all_objects.filter(
            id__in=[notif_a.id, notif_b.id]
        ).update(created_at=timezone.now() - timedelta(days=120))

        result = archive_old_notifications()

        self.assertEqual(result["archived"], 2)


# ===========================================================================
# 3. delete_archived_notifications Task Tests
# ===========================================================================

class DeleteArchivedNotificationsTaskTestCase(TestCase):
    """
    Verify the Celery task that hard-deletes notifications archived more
    than 30 days ago.
    """

    def setUp(self):
        self.tenant = _make_tenant("Delete School", "del-notif", "del", "del@notif.test")
        self.teacher = _make_user("teacher@del.test", self.tenant)

    def test_deletes_notifications_archived_more_than_30_days_ago(self):
        """Archived 35 days ago -> should be hard-deleted."""
        old_archived = Notification.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Old Archived",
            message="Msg",
            archived_at=timezone.now() - timedelta(days=35),
        )

        result = delete_archived_notifications()

        self.assertEqual(result["deleted"], 1)
        self.assertFalse(
            Notification.all_objects.filter(id=old_archived.id).exists()
        )

    def test_does_not_delete_recently_archived_notifications(self):
        """Archived 10 days ago -> should NOT be deleted (grace window)."""
        recent_archived = Notification.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Recent Archived",
            message="Msg",
            archived_at=timezone.now() - timedelta(days=10),
        )

        result = delete_archived_notifications()

        self.assertEqual(result["deleted"], 0)
        self.assertTrue(
            Notification.all_objects.filter(id=recent_archived.id).exists()
        )

    def test_does_not_delete_non_archived_notifications(self):
        """Active (non-archived) notifications should never be deleted."""
        active = _make_notification(self.tenant, self.teacher, title="Active")

        result = delete_archived_notifications()

        self.assertEqual(result["deleted"], 0)
        self.assertTrue(
            Notification.all_objects.filter(id=active.id).exists()
        )

    def test_empty_database_deletes_zero(self):
        """Task handles empty table gracefully."""
        result = delete_archived_notifications()
        self.assertEqual(result["deleted"], 0)

    def test_boundary_exactly_30_days_archived_not_deleted(self):
        """Archived exactly 30 days ago is NOT deleted (lt, not lte)."""
        boundary = Notification.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            notification_type="SYSTEM",
            title="Boundary",
            message="Msg",
            archived_at=timezone.now() - timedelta(days=30),
        )

        result = delete_archived_notifications()

        self.assertEqual(result["deleted"], 0)
        self.assertTrue(
            Notification.all_objects.filter(id=boundary.id).exists()
        )

    def test_deletes_multiple_across_tenants(self):
        """Deletes old archived notifications from all tenants."""
        tenant_b = _make_tenant("School B", "del-b", "delb", "b@delnotif.test")
        teacher_b = _make_user("teacher@delb.test", tenant_b)

        for t, u in [(self.tenant, self.teacher), (tenant_b, teacher_b)]:
            Notification.all_objects.create(
                tenant=t, teacher=u,
                notification_type="SYSTEM", title="Old", message="Msg",
                archived_at=timezone.now() - timedelta(days=45),
            )

        result = delete_archived_notifications()
        self.assertEqual(result["deleted"], 2)


# ===========================================================================
# 4. Full Notification Lifecycle Tests
# ===========================================================================

class NotificationLifecycleTestCase(TestCase):
    """
    End-to-end test: create -> read -> archive -> delete.
    Verifies the complete notification lifecycle.
    """

    def setUp(self):
        self.tenant = _make_tenant("Lifecycle School", "lc-notif", "lifecycle", "lc@notif.test")
        self.teacher = _make_user("teacher@lc.test", self.tenant)

    def test_full_lifecycle(self):
        """Notification: create -> mark read -> archive -> hard delete."""

        # Step 1: Create notification
        notif = _make_notification(self.tenant, self.teacher, title="Lifecycle Test")
        self.assertIsNotNone(notif.id)
        self.assertFalse(notif.is_read)
        self.assertIsNone(notif.archived_at)
        self.assertTrue(Notification.objects.filter(id=notif.id).exists())

        # Step 2: Mark as read
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save()
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

        # Step 3: Archive (simulate task behavior)
        notif.archived_at = timezone.now()
        notif.save()
        notif.refresh_from_db()
        self.assertIsNotNone(notif.archived_at)

        # After archival: default manager excludes it, all_objects still has it
        self.assertFalse(Notification.objects.filter(id=notif.id).exists())
        self.assertTrue(Notification.all_objects.filter(id=notif.id).exists())

        # Step 4: Hard delete (simulate task behavior)
        Notification.all_objects.filter(id=notif.id).delete()
        self.assertFalse(Notification.all_objects.filter(id=notif.id).exists())

    def test_unread_notification_can_be_archived(self):
        """Archive works on unread notifications too."""
        notif = _make_notification(self.tenant, self.teacher, title="Unread Archived")
        notif.archived_at = timezone.now()
        notif.save()
        self.assertFalse(notif.is_read)
        self.assertIsNotNone(notif.archived_at)
        self.assertFalse(Notification.objects.filter(id=notif.id).exists())

    def test_notification_str_representation(self):
        """__str__ returns expected format."""
        notif = _make_notification(
            self.tenant, self.teacher,
            title="String Test",
            notification_type="REMINDER",
        )
        s = str(notif)
        self.assertIn("REMINDER", s)
        self.assertIn("String Test", s)
        self.assertIn(self.teacher.email, s)


# ===========================================================================
# 5. Notification Model Edge Cases
# ===========================================================================

class NotificationEdgeCaseTestCase(TestCase):
    """Edge-case and boundary tests for Notification model."""

    def setUp(self):
        self.tenant = _make_tenant("Edge School", "edge-notif", "edge", "edge@notif.test")
        self.teacher = _make_user("teacher@edge.test", self.tenant)

    def test_create_notification_all_types(self):
        """All notification types can be created without error."""
        for type_code, _ in Notification.NOTIFICATION_TYPES:
            notif = Notification.objects.create(
                tenant=self.tenant,
                teacher=self.teacher,
                notification_type=type_code,
                title=f"{type_code} Test",
                message=f"Message for {type_code}",
            )
            self.assertEqual(notif.notification_type, type_code)

    def test_notification_ordering_by_created_at_desc(self):
        """Default ordering is by -created_at (newest first)."""
        n1 = _make_notification(self.tenant, self.teacher, title="First")
        n2 = _make_notification(self.tenant, self.teacher, title="Second")
        n3 = _make_notification(self.tenant, self.teacher, title="Third")

        qs = list(Notification.objects.all())
        # Newest first: Third -> Second -> First
        self.assertEqual(qs[0].id, n3.id)
        self.assertEqual(qs[-1].id, n1.id)

    def test_is_read_default_false(self):
        """New notifications default to unread."""
        notif = _make_notification(self.tenant, self.teacher, title="Fresh")
        self.assertFalse(notif.is_read)
        self.assertIsNone(notif.read_at)

    def test_is_actionable_default_false(self):
        """SYSTEM notifications are not actionable by default."""
        notif = _make_notification(
            self.tenant, self.teacher, title="System",
            notification_type="SYSTEM",
        )
        self.assertFalse(notif.is_actionable)

    def test_uuid_primary_key(self):
        """Primary key is a valid UUID."""
        import uuid
        notif = _make_notification(self.tenant, self.teacher, title="UUID Check")
        # Should not raise
        uuid.UUID(str(notif.id))

    def test_optional_course_and_assignment_fields(self):
        """Notification can be created without course or assignment."""
        notif = _make_notification(self.tenant, self.teacher, title="No Relations")
        self.assertIsNone(notif.course)
        self.assertIsNone(notif.assignment)
