# apps/notifications/tests_management_commands.py
"""
Tests for notifications management commands (TASK-009 follow-up m2).

Covers the ``unarchive_notification`` management command which allows support
ops to restore an archived notification for a specific user without needing
direct database access.
"""

import uuid
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import Notification
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant():
    uid = uuid.uuid4().hex[:8]
    return Tenant.objects.create(
        name=f"Test Tenant {uid}",
        slug=f"test-{uid}",
        subdomain=f"test-{uid}",
        email=f"admin-{uid}@example.com",
        is_active=True,
    )


def _make_user(tenant):
    uid = uuid.uuid4().hex[:8]
    return User.objects.create_user(
        email=f"teacher-{uid}@example.com",
        password="pass123",
        first_name="Test",
        last_name="Teacher",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _make_notification(tenant, teacher, *, is_archived=False):
    n = Notification.all_objects.create(
        tenant=tenant,
        teacher=teacher,
        notification_type="SYSTEM",
        title="Test notification",
        message="This is a test notification.",
        is_archived=is_archived,
        archived_at=timezone.now() if is_archived else None,
    )
    return n


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUnarchiveNotificationCommand(TestCase):
    """
    Unit tests for the ``unarchive_notification`` management command.

    The command is invoked via ``python manage.py unarchive_notification --id <uuid>``.
    It must:
    - Restore is_archived=False and clear archived_at on the target row
    - Work on already-archived rows (all_objects bypass, not objects)
    - Refuse to process an already-active notification (idempotency guard)
    - Raise CommandError on missing --id or invalid UUID
    - Raise CommandError when the notification does not exist
    """

    def setUp(self):
        self.tenant = _make_tenant()
        self.teacher = _make_user(self.tenant)

    # -- Happy path -----------------------------------------------------------

    def test_unarchive_restores_is_archived_false(self):
        """Command sets is_archived=False on the target archived notification."""
        n = _make_notification(self.tenant, self.teacher, is_archived=True)
        assert n.is_archived is True  # pre-condition

        call_command("unarchive_notification", id=str(n.id), stdout=StringIO())

        n.refresh_from_db()
        self.assertFalse(
            n.is_archived,
            "unarchive_notification must set is_archived=False",
        )

    def test_unarchive_clears_archived_at(self):
        """Command sets archived_at=None on the target archived notification."""
        n = _make_notification(self.tenant, self.teacher, is_archived=True)
        assert n.archived_at is not None  # pre-condition

        call_command("unarchive_notification", id=str(n.id), stdout=StringIO())

        n.refresh_from_db()
        self.assertIsNone(
            n.archived_at,
            "unarchive_notification must set archived_at=None",
        )

    def test_unarchive_prints_success_message(self):
        """Command writes a success message to stdout on success."""
        n = _make_notification(self.tenant, self.teacher, is_archived=True)
        out = StringIO()

        call_command("unarchive_notification", id=str(n.id), stdout=out)

        output = out.getvalue()
        self.assertIn(str(n.id), output)

    def test_unarchive_uses_all_objects_manager(self):
        """
        The default ``objects`` manager excludes archived rows.
        The command must use ``all_objects`` to reach them.
        This test verifies the notification is NOT visible via objects
        before the command runs, yet the command still succeeds.
        """
        n = _make_notification(self.tenant, self.teacher, is_archived=True)
        # The archived notification must NOT be reachable via objects
        self.assertFalse(
            Notification.objects.filter(pk=n.pk).exists(),
            "Archived notifications must be hidden from the default manager",
        )

        # But the command must still be able to unarchive it
        call_command("unarchive_notification", id=str(n.id), stdout=StringIO())

        n.refresh_from_db()
        self.assertFalse(n.is_archived)

    # -- Idempotency / guards -------------------------------------------------

    def test_already_active_notification_raises_command_error(self):
        """
        Running the command on a notification that is already active (not
        archived) should raise CommandError to prevent confusing ops.
        The caller likely meant a different UUID.
        """
        n = _make_notification(self.tenant, self.teacher, is_archived=False)

        with self.assertRaises(CommandError) as ctx:
            call_command("unarchive_notification", id=str(n.id), stdout=StringIO())

        self.assertIn("not archived", str(ctx.exception).lower())

    # -- Error handling -------------------------------------------------------

    def test_missing_id_raises_command_error(self):
        """--id is required; omitting it must raise CommandError."""
        with self.assertRaises((CommandError, SystemExit)):
            call_command("unarchive_notification", stdout=StringIO())

    def test_nonexistent_id_raises_command_error(self):
        """Unknown UUID must raise CommandError, not crash with DoesNotExist."""
        random_uuid = str(uuid.uuid4())

        with self.assertRaises(CommandError) as ctx:
            call_command("unarchive_notification", id=random_uuid, stdout=StringIO())

        self.assertIn("not found", str(ctx.exception).lower())

    def test_invalid_uuid_raises_command_error(self):
        """Malformed UUID string must raise CommandError, not unhandled ValueError."""
        with self.assertRaises(CommandError) as ctx:
            call_command("unarchive_notification", id="not-a-uuid", stdout=StringIO())

        self.assertIn("invalid", str(ctx.exception).lower())
