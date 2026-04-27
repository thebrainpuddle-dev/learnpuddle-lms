# tests/reminders/test_reminders_services.py
"""
Coverage gap tests for the reminders app.

Existing suites (``apps/reminders/tests.py``, ``apps/reminders/tests_extended.py``,
``tests/reminders/test_reminders_views.py``) exercise the HTTP layer well but
leave several service-layer and model-level behaviours uncovered:

- ``ReminderCampaign`` TenantManager auto-filtering + ``all_objects`` escape.
- Unique ``automation_key`` constraint for AUTOMATED campaigns.
- ``ReminderDelivery`` unique_together (campaign, teacher) -> idempotency.
- Delivery status lifecycle (PENDING -> SENT / FAILED).
- ``build_subject_and_message`` auto-generated subject/body for each type
  including the ``deadline_override`` branch.
- ``get_course_reminder_lead_days`` parsing rules (invalid tokens, out-of-range,
  empty -> defaults, dedupe+sort).
- ``is_automation_enabled`` flag flipping.
- ``dispatch_campaign``:
    * real email send path (with send_templated_email mocked)
    * email failure marked FAILED
    * teacher with notification_preferences.email_reminders=False skips email
      but still records delivery as SENT
    * empty recipient list short-circuit
- ``run_automated_course_deadline_reminders``:
    * disabled via setting
    * tenant with feature_reminders=False skipped
    * course without deadline skipped
    * course whose ``days_left`` is not in ``lead_days`` skipped
    * idempotency via automation_key (re-run does not duplicate)
    * completed teachers excluded from recipients

These tests only touch test code -- no production files are modified.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone

from apps.courses.models import Content, Course, Module
from apps.progress.models import TeacherProgress
from apps.reminders.models import ReminderCampaign, ReminderDelivery
from apps.reminders.services import (
    build_subject_and_message,
    dispatch_campaign,
    get_course_reminder_lead_days,
    is_automation_enabled,
    is_manual_reminder_locked,
    locked_reminder_message,
    recipients_for_course_deadline,
    run_automated_course_deadline_reminders,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Fixtures local to this module
# ---------------------------------------------------------------------------


@pytest.fixture
def rem_tenant(db):
    return Tenant.objects.create(
        name="Rem Svc School",
        slug="rem-svc-school",
        subdomain="remsvc",
        email="rem-svc@example.com",
        is_active=True,
        feature_reminders=True,
    )


@pytest.fixture
def rem_tenant_other(db):
    return Tenant.objects.create(
        name="Rem Svc Other",
        slug="rem-svc-other",
        subdomain="remsvcother",
        email="rem-svc-other@example.com",
        is_active=True,
        feature_reminders=True,
    )


@pytest.fixture
def rem_admin(db, rem_tenant):
    return User.objects.create_user(
        email="admin-remsvc@example.com",
        password="pw",
        first_name="Svc",
        last_name="Admin",
        tenant=rem_tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


@pytest.fixture
def rem_teacher_a(db, rem_tenant):
    return User.objects.create_user(
        email="t-a-remsvc@example.com",
        password="pw",
        first_name="Alpha",
        last_name="Teacher",
        tenant=rem_tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def rem_teacher_b(db, rem_tenant):
    return User.objects.create_user(
        email="t-b-remsvc@example.com",
        password="pw",
        first_name="Bravo",
        last_name="Teacher",
        tenant=rem_tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def rem_course_with_deadline(db, rem_tenant, rem_admin):
    return Course.objects.create(
        tenant=rem_tenant,
        title="Deadline Course",
        slug="deadline-course-svc",
        description="",
        created_by=rem_admin,
        is_published=True,
        is_active=True,
        assigned_to_all=True,
        deadline=timezone.localdate() + timedelta(days=3),
    )


@pytest.fixture
def rem_content(db, rem_course_with_deadline):
    module = Module.objects.create(
        course=rem_course_with_deadline,
        title="M1",
        description="",
        order=1,
        is_active=True,
    )
    return Content.objects.create(
        module=module,
        title="L1",
        content_type="TEXT",
        order=1,
        text_content="<p>x</p>",
        is_active=True,
        is_mandatory=True,
    )


# ---------------------------------------------------------------------------
# Model-level tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReminderCampaignModel:
    def test_tenant_manager_auto_filters_by_current_tenant(
        self, rem_tenant, rem_tenant_other
    ):
        """``ReminderCampaign.objects`` must auto-filter via TenantManager."""
        from utils.tenant_middleware import set_current_tenant, clear_current_tenant

        ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="CUSTOM",
            subject="mine",
            message="m",
            source="MANUAL",
        )
        ReminderCampaign.all_objects.create(
            tenant=rem_tenant_other,
            reminder_type="CUSTOM",
            subject="other",
            message="m",
            source="MANUAL",
        )

        try:
            set_current_tenant(rem_tenant)
            visible = list(ReminderCampaign.objects.all())
        finally:
            clear_current_tenant()

        subjects = {c.subject for c in visible}
        assert subjects == {"mine"}
        # all_objects escape hatch must see both
        assert ReminderCampaign.all_objects.count() == 2

    def test_automated_campaign_unique_automation_key_per_tenant(self, rem_tenant):
        ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="COURSE_DEADLINE",
            subject="s",
            message="m",
            source="AUTOMATED",
            automation_key="course-deadline:abc:3:2026-04-20",
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ReminderCampaign.all_objects.create(
                    tenant=rem_tenant,
                    reminder_type="COURSE_DEADLINE",
                    subject="s2",
                    message="m2",
                    source="AUTOMATED",
                    automation_key="course-deadline:abc:3:2026-04-20",
                )

    def test_manual_campaigns_may_share_empty_automation_key(self, rem_tenant):
        """The unique constraint only applies when source=AUTOMATED and key is non-empty."""
        ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="CUSTOM",
            subject="a",
            message="m",
            source="MANUAL",
            automation_key="",
        )
        # Creating a second MANUAL with empty key must succeed.
        second = ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="CUSTOM",
            subject="b",
            message="m",
            source="MANUAL",
            automation_key="",
        )
        assert second.pk is not None


@pytest.mark.django_db
class TestReminderDeliveryModel:
    def test_delivery_defaults_to_pending_status(self, rem_tenant, rem_teacher_a):
        campaign = ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="CUSTOM",
            subject="s",
            message="m",
            source="MANUAL",
        )
        delivery = ReminderDelivery.objects.create(
            campaign=campaign, teacher=rem_teacher_a
        )
        assert delivery.status == "PENDING"
        assert delivery.sent_at is None
        assert delivery.error == ""

    def test_delivery_unique_together_prevents_duplicates(
        self, rem_tenant, rem_teacher_a
    ):
        """(campaign, teacher) is unique_together -> idempotency guarantee."""
        campaign = ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="CUSTOM",
            subject="s",
            message="m",
            source="MANUAL",
        )
        ReminderDelivery.objects.create(campaign=campaign, teacher=rem_teacher_a)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ReminderDelivery.objects.create(
                    campaign=campaign, teacher=rem_teacher_a
                )

    def test_delivery_status_lifecycle_transitions(
        self, rem_tenant, rem_teacher_a
    ):
        campaign = ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="CUSTOM",
            subject="s",
            message="m",
            source="MANUAL",
        )
        d = ReminderDelivery.objects.create(campaign=campaign, teacher=rem_teacher_a)
        assert d.status == "PENDING"

        d.status = "SENT"
        d.sent_at = timezone.now()
        d.save(update_fields=["status", "sent_at"])
        d.refresh_from_db()
        assert d.status == "SENT"
        assert d.sent_at is not None

        d.status = "FAILED"
        d.error = "smtp error"
        d.save(update_fields=["status", "error"])
        d.refresh_from_db()
        assert d.status == "FAILED"
        assert d.error == "smtp error"


# ---------------------------------------------------------------------------
# build_subject_and_message
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBuildSubjectAndMessage:
    def test_custom_type_fills_defaults_when_blank(self):
        subj, msg = build_subject_and_message(
            "CUSTOM", None, None, "", "", None
        )
        assert subj == "Reminder"
        assert "reminder" in msg.lower()

    def test_course_deadline_uses_course_title_when_subject_blank(
        self, rem_course_with_deadline
    ):
        subj, msg = build_subject_and_message(
            "COURSE_DEADLINE",
            rem_course_with_deadline,
            None,
            "",
            "",
            None,
        )
        assert rem_course_with_deadline.title in subj
        assert rem_course_with_deadline.title in msg

    def test_course_deadline_uses_deadline_override_when_provided(
        self, rem_course_with_deadline
    ):
        override = timezone.now() + timedelta(days=10)
        _, msg = build_subject_and_message(
            "COURSE_DEADLINE",
            rem_course_with_deadline,
            None,
            "",
            "",
            override,
        )
        assert str(override.date()) in msg

    def test_assignment_due_uses_assignment_title(
        self, rem_tenant, rem_course_with_deadline, rem_content
    ):
        from apps.progress.models import Assignment

        assignment = Assignment.objects.create(
            tenant=rem_tenant,
            course=rem_course_with_deadline,
            module=rem_content.module,
            content=rem_content,
            title="Deep Work Essay",
            description="",
            generation_source="MANUAL",
            is_mandatory=True,
            is_active=True,
        )
        subj, msg = build_subject_and_message(
            "ASSIGNMENT_DUE", None, assignment, "", "", None
        )
        assert "Deep Work Essay" in subj
        assert "Deep Work Essay" in msg


# ---------------------------------------------------------------------------
# Lead-day parsing + automation flags
# ---------------------------------------------------------------------------


class TestLeadDayParsing:
    def test_empty_setting_returns_defaults(self, settings):
        settings.AUTO_COURSE_REMINDER_LEAD_DAYS = ""
        assert get_course_reminder_lead_days() == [7, 3, 1, 0]

    def test_parses_valid_tokens_sorted_descending_and_deduped(self, settings):
        settings.AUTO_COURSE_REMINDER_LEAD_DAYS = "1, 3, 3, 7, 0"
        assert get_course_reminder_lead_days() == [7, 3, 1, 0]

    def test_out_of_range_and_invalid_tokens_are_ignored(self, settings):
        # -1 and 31 are out of 0..30; "abc" is non-integer -> all ignored.
        # When everything is dropped the default list is returned.
        settings.AUTO_COURSE_REMINDER_LEAD_DAYS = "-1, 31, abc"
        assert get_course_reminder_lead_days() == [7, 3, 1, 0]

    def test_is_automation_enabled_respects_setting(self, settings):
        settings.AUTO_COURSE_REMINDERS_ENABLED = False
        assert is_automation_enabled() is False
        settings.AUTO_COURSE_REMINDERS_ENABLED = True
        assert is_automation_enabled() is True

    def test_manual_lock_helpers(self):
        assert is_manual_reminder_locked("COURSE_DEADLINE") is True
        assert is_manual_reminder_locked("CUSTOM") is False
        assert "locked" in locked_reminder_message("COURSE_DEADLINE").lower()
        assert "locked" in locked_reminder_message("OTHER").lower()


# ---------------------------------------------------------------------------
# dispatch_campaign
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(REMINDER_EMAIL_ENABLED=True)
class TestDispatchCampaign:
    def _make_campaign(self, tenant, source="MANUAL"):
        return ReminderCampaign.all_objects.create(
            tenant=tenant,
            reminder_type="CUSTOM",
            subject="Hi",
            message="Hello",
            source=source,
        )

    def test_dispatch_sends_email_and_marks_delivery_sent(
        self, rem_tenant, rem_teacher_a
    ):
        campaign = self._make_campaign(rem_tenant)
        with patch("apps.reminders.services.send_templated_email") as mock_send, patch(
            "apps.notifications.services.notify_reminder"
        ):
            result = dispatch_campaign(campaign, [rem_teacher_a])

        assert result.sent == 1
        assert result.failed == 0
        mock_send.assert_called_once()
        delivery = ReminderDelivery.objects.get(
            campaign=campaign, teacher=rem_teacher_a
        )
        assert delivery.status == "SENT"
        assert delivery.sent_at is not None

    def test_dispatch_marks_delivery_failed_on_email_exception(
        self, rem_tenant, rem_teacher_a
    ):
        campaign = self._make_campaign(rem_tenant)
        with patch(
            "apps.reminders.services.send_templated_email",
            side_effect=RuntimeError("smtp down"),
        ), patch("apps.notifications.services.notify_reminder"):
            result = dispatch_campaign(campaign, [rem_teacher_a])

        assert result.sent == 0
        assert result.failed == 1
        delivery = ReminderDelivery.objects.get(
            campaign=campaign, teacher=rem_teacher_a
        )
        assert delivery.status == "FAILED"
        assert "smtp down" in delivery.error
        assert delivery.sent_at is None

    def test_dispatch_respects_teacher_email_preference_opt_out(
        self, rem_tenant, rem_teacher_a
    ):
        """A teacher who has disabled email_reminders should NOT receive an email,
        but the delivery is still recorded as SENT (in-app reminder still delivered)."""
        rem_teacher_a.notification_preferences = {"email_reminders": False}
        rem_teacher_a.save(update_fields=["notification_preferences"])

        campaign = self._make_campaign(rem_tenant)
        with patch("apps.reminders.services.send_templated_email") as mock_send, patch(
            "apps.notifications.services.notify_reminder"
        ):
            result = dispatch_campaign(campaign, [rem_teacher_a])

        mock_send.assert_not_called()
        assert result.sent == 1
        assert result.failed == 0
        assert (
            ReminderDelivery.objects.get(campaign=campaign, teacher=rem_teacher_a).status
            == "SENT"
        )

    def test_dispatch_empty_recipient_list_is_noop(self, rem_tenant):
        campaign = self._make_campaign(rem_tenant)
        with patch("apps.reminders.services.send_templated_email") as mock_send, patch(
            "apps.notifications.services.notify_reminder"
        ) as mock_notify:
            result = dispatch_campaign(campaign, [])
        assert result.sent == 0
        assert result.failed == 0
        mock_send.assert_not_called()
        # notify_reminder should not be called when there are no recipients
        mock_notify.assert_not_called()
        assert ReminderDelivery.objects.filter(campaign=campaign).count() == 0

    def test_dispatch_sets_in_app_sent_when_notify_reminder_succeeds(
        self, rem_tenant, rem_teacher_a, rem_teacher_b
    ):
        """
        When ``notify_reminder`` completes without raising,
        ``result.in_app_sent`` must equal the number of recipients and
        ``result.in_app_failed`` must be 0.

        Covers the BE-FOLLOWUPS-2026-04-20 requirement:
        "reminders/dispatch_campaign with mock notify_reminder raising:
         assert result.in_app_failed == len(recipients) and result.in_app_sent == 0"
        (happy-path counterpart)
        """
        recipients = [rem_teacher_a, rem_teacher_b]
        campaign = self._make_campaign(rem_tenant)
        with patch("apps.reminders.services.send_templated_email"), patch(
            "apps.notifications.services.notify_reminder"
        ):
            result = dispatch_campaign(campaign, recipients)

        assert result.in_app_sent == len(recipients)
        assert result.in_app_failed == 0

    def test_dispatch_sets_in_app_failed_when_notify_reminder_raises(
        self, rem_tenant, rem_teacher_a, rem_teacher_b
    ):
        """
        When ``notify_reminder`` raises any exception,
        ``result.in_app_failed`` must equal the number of recipients,
        ``result.in_app_sent`` must be 0, and the email dispatch result
        (``sent`` / ``failed``) must be unaffected.

        Directly verifies the BE-FOLLOWUPS-2026-04-20 requirement:
        "assert result.in_app_failed == len(recipients) and result.in_app_sent == 0"
        """
        recipients = [rem_teacher_a, rem_teacher_b]
        campaign = self._make_campaign(rem_tenant)
        with patch("apps.reminders.services.send_templated_email"), patch(
            "apps.notifications.services.notify_reminder",
            side_effect=RuntimeError("notification service unavailable"),
        ):
            result = dispatch_campaign(campaign, recipients)

        # In-app failure must be fully counted.
        assert result.in_app_failed == len(recipients)
        assert result.in_app_sent == 0
        # Email channel result must not be contaminated by the in-app failure.
        assert result.sent == len(recipients)
        assert result.failed == 0


@pytest.mark.django_db
@override_settings(REMINDER_EMAIL_ENABLED=False)
class TestDispatchCampaignEmailDisabled:
    def test_email_disabled_skips_send_but_marks_delivery_sent(
        self, rem_tenant, rem_teacher_a
    ):
        """When REMINDER_EMAIL_ENABLED=False, no email is sent but the delivery
        is still recorded as SENT (in-app channel is considered the source of truth)."""
        campaign = ReminderCampaign.all_objects.create(
            tenant=rem_tenant,
            reminder_type="CUSTOM",
            subject="Hi",
            message="Hello",
            source="MANUAL",
        )
        with patch("apps.reminders.services.send_templated_email") as mock_send, patch(
            "apps.notifications.services.notify_reminder"
        ):
            result = dispatch_campaign(campaign, [rem_teacher_a])

        mock_send.assert_not_called()
        assert result.sent == 1
        assert result.failed == 0
        assert (
            ReminderDelivery.objects.get(campaign=campaign, teacher=rem_teacher_a).status
            == "SENT"
        )


# ---------------------------------------------------------------------------
# recipients_for_course_deadline -- completed teachers excluded
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRecipientsForCourseDeadline:
    def test_completed_teachers_are_excluded(
        self,
        rem_tenant,
        rem_course_with_deadline,
        rem_content,
        rem_teacher_a,
        rem_teacher_b,
    ):
        # Teacher A has completed the course; Teacher B has not.
        TeacherProgress.objects.create(
            teacher=rem_teacher_a,
            course=rem_course_with_deadline,
            content=rem_content,
            status="COMPLETED",
            progress_percentage=100,
            started_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now(),
        )
        ids = set(
            recipients_for_course_deadline(rem_course_with_deadline).values_list(
                "id", flat=True
            )
        )
        assert rem_teacher_b.id in ids
        assert rem_teacher_a.id not in ids


# ---------------------------------------------------------------------------
# run_automated_course_deadline_reminders
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRunAutomatedCourseDeadlineReminders:
    def test_disabled_via_setting_short_circuits(self, settings, rem_tenant):
        settings.AUTO_COURSE_REMINDERS_ENABLED = False
        summary = run_automated_course_deadline_reminders(
            run_date=timezone.localdate()
        )
        assert summary == {
            "enabled": False,
            "processed_courses": 0,
            "sent": 0,
            "failed": 0,
            "created_campaigns": 0,
        }

    def test_skips_tenants_without_feature_reminders(
        self,
        rem_tenant,
        rem_course_with_deadline,
        rem_teacher_a,
    ):
        """A tenant with feature_reminders=False must be skipped entirely."""
        rem_tenant.feature_reminders = False
        rem_tenant.save(update_fields=["feature_reminders"])

        with patch("apps.reminders.services.send_templated_email"), patch(
            "apps.notifications.services.notify_reminder"
        ):
            summary = run_automated_course_deadline_reminders(
                run_date=timezone.localdate()
            )
        assert summary["created_campaigns"] == 0
        assert summary["processed_courses"] == 0
        assert (
            ReminderCampaign.all_objects.filter(
                tenant=rem_tenant, source="AUTOMATED"
            ).count()
            == 0
        )

    def test_course_days_left_outside_lead_window_is_skipped(
        self,
        settings,
        rem_tenant,
        rem_course_with_deadline,
        rem_teacher_a,
    ):
        # Course deadline is 3 days out; lead_days are {10} -> should skip.
        settings.AUTO_COURSE_REMINDER_LEAD_DAYS = "10"
        with patch("apps.reminders.services.send_templated_email"), patch(
            "apps.notifications.services.notify_reminder"
        ):
            summary = run_automated_course_deadline_reminders(
                run_date=timezone.localdate()
            )
        assert summary["created_campaigns"] == 0
        assert summary["processed_courses"] == 0

    def test_idempotent_within_same_day_via_automation_key(
        self,
        rem_tenant,
        rem_course_with_deadline,
        rem_teacher_a,
    ):
        """Running twice on the same day must not create a duplicate campaign."""
        run_date = timezone.localdate()
        # course.deadline is run_date + 3 -> days_left = 3 (in default lead_days)
        with patch("apps.reminders.services.send_templated_email"), patch(
            "apps.notifications.services.notify_reminder"
        ):
            first = run_automated_course_deadline_reminders(run_date=run_date)
            second = run_automated_course_deadline_reminders(run_date=run_date)

        assert first["created_campaigns"] == 1
        assert second["created_campaigns"] == 0
        assert (
            ReminderCampaign.all_objects.filter(
                tenant=rem_tenant,
                source="AUTOMATED",
                reminder_type="COURSE_DEADLINE",
            ).count()
            == 1
        )

    def test_skips_course_with_no_recipients(
        self,
        rem_tenant,
        rem_course_with_deadline,
        rem_content,
        rem_teacher_a,
    ):
        """If every assigned teacher has completed the course, no campaign is created."""
        TeacherProgress.objects.create(
            teacher=rem_teacher_a,
            course=rem_course_with_deadline,
            content=rem_content,
            status="COMPLETED",
            progress_percentage=100,
            started_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now(),
        )
        with patch("apps.reminders.services.send_templated_email"), patch(
            "apps.notifications.services.notify_reminder"
        ):
            summary = run_automated_course_deadline_reminders(
                run_date=timezone.localdate()
            )
        # processed_courses counts any course matching lead_days; with only one
        # assigned teacher who is completed, recipients is empty and no campaign
        # is created.
        assert summary["created_campaigns"] == 0

    def test_course_without_deadline_is_skipped(
        self, rem_tenant, rem_admin, rem_teacher_a
    ):
        """Courses with deadline=NULL must never be processed by automation."""
        Course.objects.create(
            tenant=rem_tenant,
            title="No-Deadline Course",
            slug="no-deadline-course",
            description="",
            created_by=rem_admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
            deadline=None,
        )
        with patch("apps.reminders.services.send_templated_email"), patch(
            "apps.notifications.services.notify_reminder"
        ):
            summary = run_automated_course_deadline_reminders(
                run_date=timezone.localdate()
            )
        assert summary["created_campaigns"] == 0
        assert (
            ReminderCampaign.all_objects.filter(
                tenant=rem_tenant, source="AUTOMATED"
            ).count()
            == 0
        )
