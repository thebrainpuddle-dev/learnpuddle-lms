# apps/notifications/management/commands/unarchive_notification.py
"""
Support-ops command: restore an archived notification by UUID.

Usage::

    python manage.py unarchive_notification --id <uuid>

This bypasses the ``ActiveNotificationManager`` (which hides archived rows)
by using the ``Notification.all_objects`` manager so that archived rows are
reachable.

Raises CommandError for:
- Missing or malformed --id
- Notification not found
- Notification is not archived (idempotency guard — wrong UUID is likely)
"""

import uuid

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restore an archived notification to active status."

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            dest="notification_id",
            help="UUID of the notification to unarchive.",
        )
        parser.add_argument(
            "notification_id_positional",
            nargs="?",
            help="UUID of the notification to unarchive.",
        )

    def handle(self, *args, **options):
        raw_id = options.get("notification_id") or options.get("notification_id_positional")
        if not raw_id:
            raise CommandError("Notification ID is required. Pass --id <uuid> or <uuid>.")

        # Validate UUID format before hitting the DB.
        try:
            notification_uuid = uuid.UUID(raw_id)
        except ValueError:
            raise CommandError(
                f"Invalid notification ID '{raw_id}' — must be a valid UUID."
            )

        from apps.notifications.models import Notification

        try:
            notification = Notification.all_objects.get(pk=notification_uuid)
        except Notification.DoesNotExist:
            raise CommandError(
                f"Notification {notification_uuid} not found."
            )

        if not notification.is_archived and notification.archived_at is None:
            raise CommandError(
                f"Notification {notification_uuid} is not archived — nothing to restore."
            )

        notification.is_archived = False
        notification.archived_at = None
        notification.save(update_fields=["is_archived", "archived_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Notification {notification_uuid} has been unarchived successfully."
            )
        )
