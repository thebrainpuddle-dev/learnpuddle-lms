# apps/progress/tests_gamification_signals.py
"""
Coverage for `apps.progress.gamification_signals`.

The three signal receivers wire learning activity to the XP engine:

  - `on_teacher_progress_save` — content + course completion XP + streak bump
  - `on_assignment_submission` — assignment XP + streak bump
  - `on_quiz_submission`       — quiz XP, with dedup, in-progress skip,
                                 and abandoned-attempt skip

These tests exercise each branch of the signal handlers end-to-end via the
Django ORM (not the HTTP API) — the handlers are registered via
`ProgressConfig.ready()` so `post_save` triggers them automatically.

Scope:

  - Happy paths for each signal (XP awarded, streak bumped)
  - Dedup: saving the same row twice does not double-award
  - Inactive config / opt-out short-circuits
  - Missing tenant short-circuits (no crash, no XP row)
  - Cross-tenant isolation
  - In-progress / abandoned / time-expired quiz edge cases
  - Assignment status PENDING does not award; SUBMITTED + GRADED do
  - Full-course completion triggers the `course_completion` XP row
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.courses.models import Content, Course, Module
from apps.progress.gamification_models import (
    GamificationConfig,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)
from apps.progress.models import (
    Assignment,
    AssignmentSubmission,
    Quiz,
    QuizSubmission,
    TeacherProgress,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT_COUNTER = {"n": 0}


def _uniq():
    _TENANT_COUNTER["n"] += 1
    return _TENANT_COUNTER["n"]


def _make_tenant(name="School", subdomain=None):
    sub = subdomain or f"sig{_uniq()}"
    return Tenant.objects.create(
        name=name,
        slug=sub,
        subdomain=sub,
        email=f"{sub}@test.com",
        is_active=True,
    )


def _make_admin(tenant, idx=1):
    return User.objects.create_user(
        email=f"admin-{tenant.subdomain}-{idx}@test.com",
        password="pass123",
        first_name="Admin",
        last_name=str(idx),
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _make_teacher(tenant, idx=1):
    return User.objects.create_user(
        email=f"teacher-{tenant.subdomain}-{idx}@test.com",
        password="pass123",
        first_name="Teacher",
        last_name=str(idx),
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _make_course(tenant, admin, idx=1):
    return Course.objects.create(
        tenant=tenant,
        title=f"Course {idx}",
        slug=f"course-{tenant.subdomain}-{idx}",
        description="desc",
        created_by=admin,
        is_published=True,
        is_active=True,
        assigned_to_all=True,
    )


def _make_module(course, idx=1):
    return Module.objects.create(
        course=course,
        title=f"Module {idx}",
        description="",
        order=idx,
        is_active=True,
    )


def _make_content(module, idx=1):
    return Content.objects.create(
        module=module,
        title=f"Content {idx}",
        content_type="TEXT",
        order=idx,
        file_url="",
        file_size=0,
        duration=10,
        text_content="hello",
        is_mandatory=True,
        is_active=True,
    )


def _make_assignment(tenant, course, idx=1):
    return Assignment.all_objects.create(
        tenant=tenant,
        course=course,
        title=f"Assignment {idx}",
        description="desc",
        is_active=True,
    )


def _make_quiz(tenant, assignment, max_attempts=3):
    return Quiz.all_objects.create(
        tenant=tenant,
        assignment=assignment,
        max_attempts=max_attempts,
    )


# ---------------------------------------------------------------------------
# 1. on_teacher_progress_save — content completion
# ---------------------------------------------------------------------------


class TeacherProgressContentCompletionSignalTest(TestCase):
    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_admin(self.tenant)
        self.teacher = _make_teacher(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.content = _make_content(self.module)

    def _complete_content(self, content=None):
        c = content or self.content
        return TeacherProgress.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            course=self.course,
            content=c,
            status="COMPLETED",
            completed_at=timezone.now(),
        )

    def test_content_completion_awards_xp(self):
        self._complete_content()
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher,
            reason="content_completion",
            reference_id=self.content.id,
        ).count() == 1

    def test_content_completion_updates_xp_summary(self):
        self._complete_content()
        summary = TeacherXPSummary.all_objects.get(teacher=self.teacher)
        # Default config => 10 XP per content completion.
        assert summary.total_xp >= 10

    def test_content_completion_bumps_streak(self):
        self._complete_content()
        streak = TeacherStreak.all_objects.get(teacher=self.teacher)
        assert streak.current_streak >= 1
        assert streak.last_activity_date == timezone.localdate()

    def test_non_completed_status_does_not_award(self):
        TeacherProgress.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            course=self.course,
            content=self.content,
            status="IN_PROGRESS",
        )
        assert XPTransaction.all_objects.filter(teacher=self.teacher).count() == 0

    def test_double_save_same_content_does_not_double_award(self):
        row = self._complete_content()
        # Force another save — the signal fires again but dedup must hold.
        row.progress_percentage = Decimal("100.00")
        row.save()
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher,
            reason="content_completion",
            reference_id=self.content.id,
        ).count() == 1

    def test_missing_tenant_on_progress_skips_award(self):
        # Construct a teacher whose .tenant is None and a progress row with
        # tenant=None so the signal's short-circuit branch fires.
        orphan = User.objects.create_user(
            email="orphan@test.com",
            password="pass123",
            first_name="O",
            last_name="O",
            tenant=None,
            role="TEACHER",
            is_active=True,
        )
        TeacherProgress.all_objects.create(
            tenant=None,
            teacher=orphan,
            course=self.course,
            content=self.content,
            status="COMPLETED",
        )
        assert XPTransaction.all_objects.filter(teacher=orphan).count() == 0

    def test_inactive_config_skips_xp(self):
        GamificationConfig.objects.create(tenant=self.tenant, is_active=False)
        self._complete_content()
        assert XPTransaction.all_objects.filter(teacher=self.teacher).count() == 0

    def test_opted_out_teacher_gets_no_xp(self):
        # Create summary first with opted_out=True.
        TeacherXPSummary.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, opted_out=True,
        )
        self._complete_content()
        assert XPTransaction.all_objects.filter(teacher=self.teacher).count() == 0


# ---------------------------------------------------------------------------
# 2. on_teacher_progress_save — course-completion branch
# ---------------------------------------------------------------------------


class TeacherProgressCourseCompletionSignalTest(TestCase):
    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_admin(self.tenant)
        self.teacher = _make_teacher(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.c1 = _make_content(self.module, idx=1)
        self.c2 = _make_content(self.module, idx=2)

    def test_course_completion_fires_when_all_content_done(self):
        TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.c1, status="COMPLETED",
        )
        TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.c2, status="COMPLETED",
        )
        course_rows = XPTransaction.all_objects.filter(
            teacher=self.teacher,
            reason="course_completion",
            reference_id=self.course.id,
        )
        assert course_rows.count() == 1

    def test_partial_completion_does_not_fire_course_xp(self):
        TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.c1, status="COMPLETED",
        )
        # Only 1 of 2 contents done — course XP should not fire yet.
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="course_completion",
        ).count() == 0

    def test_course_completion_dedups_on_further_content_saves(self):
        TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.c1, status="COMPLETED",
        )
        second = TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.c2, status="COMPLETED",
        )
        # Save again - course XP should still be exactly 1.
        second.save()
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="course_completion",
        ).count() == 1


# ---------------------------------------------------------------------------
# 3. on_assignment_submission
# ---------------------------------------------------------------------------


class AssignmentSubmissionSignalTest(TestCase):
    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_admin(self.tenant)
        self.teacher = _make_teacher(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.assignment = _make_assignment(self.tenant, self.course)

    def _submit(self, status="SUBMITTED"):
        return AssignmentSubmission.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            assignment=self.assignment,
            submission_text="answer",
            status=status,
        )

    def test_submitted_status_awards_xp(self):
        self._submit(status="SUBMITTED")
        rows = XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="assignment_submission",
        )
        assert rows.count() == 1

    def test_graded_status_awards_xp(self):
        # Create in SUBMITTED state to mirror the real flow; the signal only
        # awards on the CREATE of the row.  GRADED-on-create is a rare admin
        # path but the signal allows it.
        AssignmentSubmission.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            assignment=self.assignment,
            submission_text="answer",
            status="GRADED",
            score=Decimal("85"),
        )
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="assignment_submission",
        ).count() == 1

    def test_pending_status_does_not_award(self):
        self._submit(status="PENDING")
        assert XPTransaction.all_objects.filter(teacher=self.teacher).count() == 0

    def test_resave_submitted_does_not_double_award(self):
        sub = self._submit(status="SUBMITTED")
        # Grading the submission triggers a save but `created=False` — no XP.
        sub.status = "GRADED"
        sub.score = Decimal("90")
        sub.save()
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="assignment_submission",
        ).count() == 1

    def test_submission_bumps_streak(self):
        self._submit()
        streak = TeacherStreak.all_objects.get(teacher=self.teacher)
        assert streak.current_streak >= 1


# ---------------------------------------------------------------------------
# 4. on_quiz_submission
# ---------------------------------------------------------------------------


class QuizSubmissionSignalTest(TestCase):
    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_admin(self.tenant)
        self.teacher = _make_teacher(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.assignment = _make_assignment(self.tenant, self.course)
        self.quiz = _make_quiz(self.tenant, self.assignment)

    def _submission(self, score=Decimal("80"), attempt=1, time_expired=False):
        return QuizSubmission.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            quiz=self.quiz,
            attempt_number=attempt,
            score=score,
            time_expired=time_expired,
            graded_at=timezone.now() if score is not None else None,
        )

    def test_completed_submission_awards_xp(self):
        self._submission(score=Decimal("75"))
        rows = XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="quiz_submission",
        )
        assert rows.count() == 1

    def test_in_progress_submission_is_skipped(self):
        QuizSubmission.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            quiz=self.quiz,
            attempt_number=1,
            score=None,  # in-progress
        )
        assert XPTransaction.all_objects.filter(teacher=self.teacher).count() == 0

    def test_abandoned_timed_attempt_is_skipped(self):
        # Simulated abandonment: timed quiz closed with score=0 + time_expired.
        self._submission(score=Decimal("0"), time_expired=True)
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="quiz_submission",
        ).count() == 0

    def test_time_expired_with_nonzero_score_still_awards(self):
        # Teacher answered some questions before the timer fired.
        self._submission(score=Decimal("40"), time_expired=True)
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="quiz_submission",
        ).count() == 1

    def test_earned_zero_score_not_timed_out_still_awards(self):
        # Honest zero — teacher submitted answers, all wrong.  Policy targets
        # force-closes (time_expired=True, score=0), not earned zeros, so XP
        # for completion is still awarded.
        self._submission(score=Decimal("0"), time_expired=False)
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="quiz_submission",
        ).count() == 1

    def test_abandoned_timed_attempt_emits_structured_log(self):
        # The skip path emits a `metric=quiz_xp_skipped_on_timeout` log line
        # so observability can detect force-close volume.
        import logging as _logging

        with self.assertLogs(
            "apps.progress.gamification_signals", level=_logging.INFO,
        ) as cap:
            sub = self._submission(score=Decimal("0"), time_expired=True)
        assert any(
            "Skipping XP for abandoned timed quiz attempt" in m
            for m in cap.output
        )
        # The structured `extra={"metric": ...}` is attached to the LogRecord
        # via assertLogs.records — confirm the metric key is set.
        records_with_metric = [
            r for r in cap.records
            if getattr(r, "metric", None) == "quiz_xp_skipped_on_timeout"
        ]
        assert len(records_with_metric) == 1
        rec = records_with_metric[0]
        assert rec.attempt_id == str(sub.pk)

    def test_each_attempt_awards_its_own_xp(self):
        self._submission(score=Decimal("50"), attempt=1)
        self._submission(score=Decimal("70"), attempt=2)
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="quiz_submission",
        ).count() == 2

    def test_resaving_same_submission_does_not_double_award(self):
        sub = self._submission(score=Decimal("60"))
        # Admin re-grade scenario: save the same row again with a new score.
        sub.score = Decimal("75")
        sub.save()
        assert XPTransaction.all_objects.filter(
            teacher=self.teacher,
            reason="quiz_submission",
            reference_id=sub.id,
        ).count() == 1

    def test_quiz_submission_bumps_streak(self):
        self._submission(score=Decimal("80"))
        streak = TeacherStreak.all_objects.get(teacher=self.teacher)
        assert streak.current_streak >= 1


# ---------------------------------------------------------------------------
# 5. Cross-tenant isolation: activity in tenant A must not touch tenant B
# ---------------------------------------------------------------------------


class SignalCrossTenantIsolationTest(TestCase):
    def setUp(self):
        self.tenant_a = _make_tenant()
        self.tenant_b = _make_tenant()
        self.admin_a = _make_admin(self.tenant_a, idx=1)
        self.admin_b = _make_admin(self.tenant_b, idx=2)
        self.teacher_a = _make_teacher(self.tenant_a, idx=1)
        self.teacher_b = _make_teacher(self.tenant_b, idx=2)
        self.course_a = _make_course(self.tenant_a, self.admin_a, idx=1)
        self.course_b = _make_course(self.tenant_b, self.admin_b, idx=2)
        self.module_a = _make_module(self.course_a)
        self.module_b = _make_module(self.course_b)
        self.content_a = _make_content(self.module_a)
        self.content_b = _make_content(self.module_b)

    def test_content_completion_xp_is_scoped_to_activity_tenant(self):
        TeacherProgress.all_objects.create(
            tenant=self.tenant_a,
            teacher=self.teacher_a,
            course=self.course_a,
            content=self.content_a,
            status="COMPLETED",
        )
        # XP rows for teacher_a are on tenant_a; tenant_b rows unaffected.
        a_rows = XPTransaction.all_objects.filter(tenant=self.tenant_a)
        b_rows = XPTransaction.all_objects.filter(tenant=self.tenant_b)
        assert a_rows.count() == 1
        assert b_rows.count() == 0
        assert a_rows.first().teacher_id == self.teacher_a.id

    def test_simultaneous_activity_in_both_tenants_stays_isolated(self):
        TeacherProgress.all_objects.create(
            tenant=self.tenant_a, teacher=self.teacher_a,
            course=self.course_a, content=self.content_a, status="COMPLETED",
        )
        TeacherProgress.all_objects.create(
            tenant=self.tenant_b, teacher=self.teacher_b,
            course=self.course_b, content=self.content_b, status="COMPLETED",
        )
        a = XPTransaction.all_objects.filter(tenant=self.tenant_a)
        b = XPTransaction.all_objects.filter(tenant=self.tenant_b)
        assert a.count() == 1 and b.count() == 1
        # No cross-contamination of teacher attribution.
        assert a.first().teacher_id == self.teacher_a.id
        assert b.first().teacher_id == self.teacher_b.id
