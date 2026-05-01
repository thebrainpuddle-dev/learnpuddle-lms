"""
TDD regression suite — Notification.NOTIFICATION_TYPES completeness.

Root cause (2026-04-28):
    discussions/views.py:921 called create_notification(..., notification_type='DISCUSSION_REPLY')
    but 'DISCUSSION_REPLY' was absent from Notification.NOTIFICATION_TYPES.

    Because Django does NOT call full_clean() inside .objects.create(), the invalid
    type value was silently stored in the database on every discussion reply, producing
    rows that are invisible to any code filtering or displaying by valid choices.

    Fix: Add ('DISCUSSION_REPLY', 'Discussion Reply') to Notification.NOTIFICATION_TYPES.

Expected (once fix is applied):
    5 tests PASS — run with:
        docker compose exec web pytest apps/notifications/tests_notification_type_choices.py -v
"""

from django.test import TestCase

from apps.notifications.models import Notification
from apps.notifications.services import ACTIONABLE_TYPES


class TestNotificationTypeChoicesCompleteness(TestCase):
    """
    Verify that every notification_type used by production code is present in
    Notification.NOTIFICATION_TYPES.

    Whenever a new call-site for create_notification() is added, the new type
    must be added BOTH here (to known_production_types) AND to the model choices.
    """

    def _valid_types(self):
        """Return the set of valid choice keys from Notification.NOTIFICATION_TYPES."""
        return {t[0] for t in Notification.NOTIFICATION_TYPES}

    # ------------------------------------------------------------------
    # Test 1 — core regression guard
    # ------------------------------------------------------------------

    def test_discussion_reply_is_in_notification_types(self):
        """
        'DISCUSSION_REPLY' must appear in Notification.NOTIFICATION_TYPES.

        Regression for the bug where discussions/views.py created notifications
        with this type while the model had no matching choice, causing invalid
        data to be stored silently.
        """
        self.assertIn(
            "DISCUSSION_REPLY",
            self._valid_types(),
            "'DISCUSSION_REPLY' is missing from Notification.NOTIFICATION_TYPES. "
            "Add ('DISCUSSION_REPLY', 'Discussion Reply') to the choices list in "
            "apps/notifications/models.py.",
        )

    # ------------------------------------------------------------------
    # Test 2 — display label is meaningful
    # ------------------------------------------------------------------

    def test_discussion_reply_has_human_readable_label(self):
        """
        'DISCUSSION_REPLY' must have a non-empty, non-technical display label.
        The label is shown in Django admin and any future UI choice widgets.
        """
        label_map = dict(Notification.NOTIFICATION_TYPES)
        label = label_map.get("DISCUSSION_REPLY", "")
        self.assertTrue(
            label and label != "DISCUSSION_REPLY",
            f"Expected a human-readable label for 'DISCUSSION_REPLY', got {label!r}.",
        )

    # ------------------------------------------------------------------
    # Test 3 — all known production call-sites covered
    # ------------------------------------------------------------------

    def test_all_known_production_types_are_in_choices(self):
        """
        Document every notification_type used by production code in one place.

        If this test goes red after a new feature is added, it means the new
        type was not added to Notification.NOTIFICATION_TYPES.  Extend
        `known_production_types` below at the same time as adding the model choice.
        """
        # Map each type to its known production call-site for self-documentation.
        known_production_types = {
            "REMINDER": "reminders/tasks.py; admin reminder endpoint",
            "COURSE_ASSIGNED": "courses/views.py assignment; progress/signals.py",
            "ASSIGNMENT_DUE": "reminders/tasks.py due-date alerts",
            "ANNOUNCEMENT": "notifications/views.py admin announcements",
            "SYSTEM": "various system events",
            "DISCUSSION_REPLY": "discussions/views.py:921 — reply notifications",
        }

        valid = self._valid_types()
        missing = {t for t in known_production_types if t not in valid}
        self.assertEqual(
            missing,
            set(),
            "These notification types are used by production code but absent from "
            f"Notification.NOTIFICATION_TYPES: {missing!r}. "
            "Add the missing type(s) to the model choices.",
        )

    # ------------------------------------------------------------------
    # Test 4 — DISCUSSION_REPLY is not marked actionable
    # ------------------------------------------------------------------

    def test_discussion_reply_is_not_in_actionable_types(self):
        """
        Discussion reply notifications are informational, not action-required.
        ACTIONABLE_TYPES drives is_actionable=True on the notification row,
        which highlights the notification as requiring teacher action.
        Replies should NOT be highlighted this way.

        This test pins the current product decision; if product changes it,
        update ACTIONABLE_TYPES in services.py AND flip this test.
        """
        self.assertNotIn(
            "DISCUSSION_REPLY",
            ACTIONABLE_TYPES,
            "'DISCUSSION_REPLY' should not be in ACTIONABLE_TYPES — it is "
            "informational (a reply happened) rather than action-required.",
        )

    # ------------------------------------------------------------------
    # Test 5 — model max_length covers all current type keys
    # ------------------------------------------------------------------

    def test_all_type_keys_fit_within_max_length(self):
        """
        Notification.notification_type is CharField(max_length=20).
        Every key in NOTIFICATION_TYPES must fit within this limit so that
        adding new types doesn't silently truncate keys at the DB level.
        """
        max_len = 20  # matches models.py CharField(max_length=20)
        overlong = [
            t[0]
            for t in Notification.NOTIFICATION_TYPES
            if len(t[0]) > max_len
        ]
        self.assertEqual(
            overlong,
            [],
            f"These notification type keys exceed max_length={max_len}: {overlong}. "
            "Either shorten the key or increase CharField max_length.",
        )
