# apps/progress/tests_mastery_points.py
#
# TASK-018 — Mastery Points (TDD)
#
# Covers:
#   - Models: tenant FK + TenantManager, decimal precision, unique dedup
#   - Engine: happy path, threshold gate, opt-out, tenant-scoped summary,
#             quiz-score calc, assignment grade calc, idempotency on re-save
#   - Signal wiring: quiz submission ≥ threshold awards MP;
#                    assignment GRADED + score ≥ threshold awards MP;
#                    course completion triggers bonus when avg ≥ threshold
#   - API: teacher summary endpoint, teacher history endpoint,
#          admin leaderboard endpoint, cross-tenant isolation

import uuid
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.gamification_engine import get_or_create_config
from apps.progress.gamification_models import (
    GamificationConfig,
    MasteryPointTransaction,
    TeacherMasterySummary,
    TeacherXPSummary,
)
from apps.progress.mastery_engine import (
    award_assignment_mastery,
    award_course_mastery_bonus,
    award_mastery_points,
    award_quiz_mastery,
    get_mastery_summary,
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

_CTR = {"n": 0}


def _u():
    _CTR["n"] += 1
    return _CTR["n"]


def _tenant(name="Mastery School", subdomain=None):
    sub = subdomain or f"mp{_u()}"
    return Tenant.objects.create(
        name=name, slug=sub, subdomain=sub,
        email=f"{sub}@test.com", is_active=True,
    )


def _teacher(tenant, idx=None):
    idx = idx if idx is not None else _u()
    return User.objects.create_user(
        email=f"t{idx}-{tenant.subdomain}@test.com",
        password="pass123",
        first_name="T", last_name=str(idx),
        tenant=tenant, role="TEACHER", is_active=True,
    )


def _admin(tenant, idx=None):
    idx = idx if idx is not None else _u()
    return User.objects.create_user(
        email=f"a{idx}-{tenant.subdomain}@test.com",
        password="pass123",
        first_name="A", last_name=str(idx),
        tenant=tenant, role="SCHOOL_ADMIN", is_active=True,
    )


def _course(tenant, admin, idx=None):
    idx = idx if idx is not None else _u()
    return Course.objects.create(
        tenant=tenant, title=f"Course {idx}",
        slug=f"c-{tenant.subdomain}-{idx}", description="d",
        created_by=admin, is_published=True, is_active=True,
        assigned_to_all=True,
    )


def _module(course, idx=1):
    return Module.objects.create(
        course=course, title=f"M{idx}", description="", order=idx, is_active=True,
    )


def _content(module, idx=1):
    return Content.objects.create(
        module=module, title=f"C{idx}", content_type="TEXT",
        order=idx, file_url="", file_size=0, duration=10,
        text_content="x", is_mandatory=True, is_active=True,
    )


def _assignment(tenant, course, module, content=None, max_score=100):
    return Assignment.objects.create(
        tenant=tenant, course=course, module=module, content=content,
        title="A", description="d", instructions="",
        generation_source="MANUAL", generation_metadata={},
        max_score=max_score, passing_score=70,
    )


def _quiz(tenant, assignment):
    return Quiz.objects.create(
        tenant=tenant, assignment=assignment, is_auto_generated=False,
    )


# ===========================================================================
# 1. Model tests
# ===========================================================================

class MasteryPointModelTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)

    def test_transaction_requires_tenant(self):
        txn = MasteryPointTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=Decimal("42.50"), reason="quiz_mastery",
        )
        self.assertEqual(txn.tenant, self.tenant)
        self.assertEqual(txn.amount, Decimal("42.50"))

    def test_decimal_precision_preserved(self):
        txn = MasteryPointTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=Decimal("12.34"), reason="assignment_mastery",
        )
        refreshed = MasteryPointTransaction.all_objects.get(pk=txn.pk)
        self.assertEqual(refreshed.amount, Decimal("12.34"))

    def test_tenant_manager_isolates_transactions(self):
        other = _tenant(subdomain="mpother")
        other_teacher = _teacher(other)
        MasteryPointTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=10, reason="quiz_mastery",
        )
        MasteryPointTransaction.all_objects.create(
            tenant=other, teacher=other_teacher,
            amount=20, reason="quiz_mastery",
        )
        self.assertEqual(
            MasteryPointTransaction.all_objects.filter(tenant=self.tenant).count(),
            1,
        )

    def test_unique_reference_prevents_duplicates(self):
        from django.db import IntegrityError, transaction as dj_transaction

        ref = uuid.uuid4()
        MasteryPointTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=10, reason="quiz_mastery",
            reference_id=ref, reference_type="quiz_submission",
        )
        with self.assertRaises(IntegrityError):
            with dj_transaction.atomic():
                MasteryPointTransaction.all_objects.create(
                    tenant=self.tenant, teacher=self.teacher,
                    amount=10, reason="quiz_mastery",
                    reference_id=ref, reference_type="quiz_submission",
                )

    def test_summary_refresh_aggregates_total(self):
        MasteryPointTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=Decimal("10.5"), reason="quiz_mastery",
        )
        MasteryPointTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=Decimal("20.25"), reason="assignment_mastery",
        )
        summary, _ = TeacherMasterySummary.all_objects.get_or_create(
            teacher=self.teacher, defaults={'tenant': self.tenant},
        )
        summary.refresh_from_transactions()
        self.assertEqual(summary.total_mastery_points, Decimal("30.75"))


# ===========================================================================
# 2. Engine tests
# ===========================================================================

class MasteryEngineTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)
        self.config = get_or_create_config(self.tenant)

    def test_award_mastery_points_happy_path(self):
        txn = award_mastery_points(
            teacher=self.teacher, reason="quiz_mastery",
            amount=Decimal("50"),
            reference_id=uuid.uuid4(), reference_type="quiz_submission",
        )
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, Decimal("50.00"))

        summary = TeacherMasterySummary.all_objects.get(teacher=self.teacher)
        self.assertEqual(summary.total_mastery_points, Decimal("50.00"))

    def test_award_is_idempotent_on_same_reference(self):
        ref = uuid.uuid4()
        first = award_mastery_points(
            teacher=self.teacher, reason="quiz_mastery",
            amount=Decimal("30"), reference_id=ref,
            reference_type="quiz_submission",
        )
        dupe = award_mastery_points(
            teacher=self.teacher, reason="quiz_mastery",
            amount=Decimal("30"), reference_id=ref,
            reference_type="quiz_submission",
        )
        self.assertIsNotNone(first)
        self.assertIsNone(dupe)
        self.assertEqual(
            MasteryPointTransaction.all_objects.filter(
                teacher=self.teacher,
            ).count(),
            1,
        )

    def test_opt_out_blocks_award(self):
        TeacherXPSummary.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, opted_out=True,
        )
        result = award_mastery_points(
            teacher=self.teacher, reason="quiz_mastery",
            amount=Decimal("25"),
        )
        self.assertIsNone(result)
        self.assertEqual(
            MasteryPointTransaction.all_objects.filter(
                teacher=self.teacher,
            ).count(),
            0,
        )

    def test_gamification_inactive_blocks_award(self):
        self.config.is_active = False
        self.config.save(update_fields=["is_active"])
        result = award_mastery_points(
            teacher=self.teacher, reason="quiz_mastery", amount=25,
        )
        self.assertIsNone(result)

    def test_quiz_mastery_awards_above_threshold(self):
        # 80% threshold, weight 1.0 → MP = 85
        admin = _admin(self.tenant)
        course = _course(self.tenant, admin)
        module = _module(course)
        content = _content(module)
        assignment = _assignment(
            self.tenant, course, module, content, max_score=100,
        )
        quiz = _quiz(self.tenant, assignment)
        sub = QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=quiz, teacher=self.teacher,
            score=Decimal("85"),
        )

        txn = award_quiz_mastery(sub)
        self.assertIsNotNone(txn)
        self.assertEqual(txn.reason, "quiz_mastery")
        self.assertEqual(txn.reference_id, sub.id)

    def test_quiz_mastery_skipped_below_threshold(self):
        admin = _admin(self.tenant)
        course = _course(self.tenant, admin)
        module = _module(course)
        assignment = _assignment(
            self.tenant, course, module, max_score=100,
        )
        quiz = _quiz(self.tenant, assignment)
        sub = QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=quiz, teacher=self.teacher,
            score=Decimal("60"),
        )
        self.assertIsNone(award_quiz_mastery(sub))

    def test_quiz_mastery_respects_weight(self):
        self.config.mp_quiz_weight = Decimal("2")
        self.config.save(update_fields=["mp_quiz_weight"])

        admin = _admin(self.tenant)
        course = _course(self.tenant, admin)
        module = _module(course)
        assignment = _assignment(
            self.tenant, course, module, max_score=100,
        )
        quiz = _quiz(self.tenant, assignment)
        sub = QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=quiz, teacher=self.teacher,
            score=Decimal("90"),
        )
        txn = award_quiz_mastery(sub)
        self.assertIsNotNone(txn)
        # 90% * weight 2 = 180
        self.assertEqual(txn.amount, Decimal("180.00"))

    def test_assignment_mastery_awards_when_graded(self):
        admin = _admin(self.tenant)
        course = _course(self.tenant, admin)
        module = _module(course)
        assignment = _assignment(
            self.tenant, course, module, max_score=100,
        )
        sub = AssignmentSubmission.all_objects.create(
            tenant=self.tenant, assignment=assignment, teacher=self.teacher,
            submission_text="answer", status="GRADED",
            score=Decimal("90"), graded_at=timezone.now(),
        )
        txn = award_assignment_mastery(sub)
        self.assertIsNotNone(txn)
        self.assertEqual(txn.reason, "assignment_mastery")
        # 90 * weight 1 = 90
        self.assertEqual(txn.amount, Decimal("90.00"))

    def test_assignment_mastery_skipped_when_not_graded(self):
        admin = _admin(self.tenant)
        course = _course(self.tenant, admin)
        module = _module(course)
        assignment = _assignment(
            self.tenant, course, module, max_score=100,
        )
        sub = AssignmentSubmission.all_objects.create(
            tenant=self.tenant, assignment=assignment, teacher=self.teacher,
            submission_text="answer", status="SUBMITTED",
            score=Decimal("90"),
        )
        self.assertIsNone(award_assignment_mastery(sub))

    def test_course_mastery_bonus_awarded_when_avg_meets_threshold(self):
        admin = _admin(self.tenant)
        course = _course(self.tenant, admin)
        module = _module(course)
        assignment = _assignment(
            self.tenant, course, module, max_score=100,
        )
        quiz = _quiz(self.tenant, assignment)

        QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=quiz, teacher=self.teacher,
            score=Decimal("85"), attempt_number=1,
        )
        QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=quiz, teacher=self.teacher,
            score=Decimal("90"), attempt_number=2,
        )

        txn = award_course_mastery_bonus(self.teacher, course)
        self.assertIsNotNone(txn)
        self.assertEqual(txn.reason, "course_mastery_bonus")
        # Default bonus is 50.
        self.assertEqual(txn.amount, Decimal("50.00"))

    def test_course_mastery_bonus_skipped_when_avg_below_threshold(self):
        admin = _admin(self.tenant)
        course = _course(self.tenant, admin)
        module = _module(course)
        assignment = _assignment(
            self.tenant, course, module, max_score=100,
        )
        quiz = _quiz(self.tenant, assignment)

        QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=quiz, teacher=self.teacher,
            score=Decimal("60"), attempt_number=1,
        )
        QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=quiz, teacher=self.teacher,
            score=Decimal("65"), attempt_number=2,
        )
        self.assertIsNone(
            award_course_mastery_bonus(self.teacher, course),
        )

    def test_get_mastery_summary_is_tenant_scoped(self):
        other = _tenant(subdomain="mpscoped")
        other_teacher = _teacher(other)

        award_mastery_points(
            teacher=self.teacher, reason="quiz_mastery", amount=Decimal("40"),
        )
        award_mastery_points(
            teacher=other_teacher, reason="quiz_mastery",
            amount=Decimal("60"),
        )

        s1 = get_mastery_summary(self.teacher)
        s2 = get_mastery_summary(other_teacher)
        self.assertEqual(s1.total_mastery_points, Decimal("40.00"))
        self.assertEqual(s2.total_mastery_points, Decimal("60.00"))


# ===========================================================================
# 3. Signal wiring tests
# ===========================================================================

class MasterySignalTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)
        self.admin = _admin(self.tenant)
        self.config = get_or_create_config(self.tenant)
        self.course = _course(self.tenant, self.admin)
        self.module = _module(self.course)
        self.content = _content(self.module)
        self.assignment = _assignment(
            self.tenant, self.course, self.module, self.content, max_score=100,
        )
        self.quiz = _quiz(self.tenant, self.assignment)

    def test_quiz_submission_above_threshold_triggers_mp_award(self):
        sub = QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=self.quiz, teacher=self.teacher,
            score=Decimal("85"),
        )
        self.assertTrue(
            MasteryPointTransaction.all_objects.filter(
                teacher=self.teacher, reference_id=sub.id,
                reason="quiz_mastery",
            ).exists(),
        )

    def test_quiz_submission_below_threshold_no_mp_award(self):
        QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=self.quiz, teacher=self.teacher,
            score=Decimal("50"),
        )
        self.assertFalse(
            MasteryPointTransaction.all_objects.filter(
                teacher=self.teacher, reason="quiz_mastery",
            ).exists(),
        )

    def test_quiz_submission_resave_does_not_double_award(self):
        sub = QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=self.quiz, teacher=self.teacher,
            score=Decimal("95"),
        )
        sub.graded_at = timezone.now()
        sub.save(update_fields=["graded_at"])
        self.assertEqual(
            MasteryPointTransaction.all_objects.filter(
                teacher=self.teacher, reference_id=sub.id,
            ).count(),
            1,
        )

    def test_assignment_graded_triggers_mp_award(self):
        sub = AssignmentSubmission.all_objects.create(
            tenant=self.tenant, assignment=self.assignment, teacher=self.teacher,
            submission_text="answer", status="GRADED",
            score=Decimal("92"), graded_at=timezone.now(),
        )
        self.assertTrue(
            MasteryPointTransaction.all_objects.filter(
                teacher=self.teacher, reference_id=sub.id,
                reason="assignment_mastery",
            ).exists(),
        )

    def test_course_completion_triggers_bonus_when_scores_high(self):
        # High-scoring quiz attempt (drives the course bonus threshold).
        QuizSubmission.all_objects.create(
            tenant=self.tenant, quiz=self.quiz, teacher=self.teacher,
            score=Decimal("90"), attempt_number=1,
        )

        # Completing every content item in the course triggers the
        # existing course_completion XP path, which in turn fires
        # award_course_mastery_bonus via the signal.
        TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.content, status="COMPLETED",
            progress_percentage=Decimal("100"),
        )
        self.assertTrue(
            MasteryPointTransaction.all_objects.filter(
                teacher=self.teacher, reference_id=self.course.id,
                reason="course_mastery_bonus",
            ).exists(),
        )


# ===========================================================================
# 4. API tests
# ===========================================================================

@override_settings(ALLOWED_HOSTS=["*"])
class MasteryPointApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = _tenant(subdomain="mpapi")
        self.host = f"{self.tenant.subdomain}.lms.com"
        self.admin = _admin(self.tenant)
        self.teacher = _teacher(self.tenant)
        self.config = get_or_create_config(self.tenant)

        award_mastery_points(
            teacher=self.teacher, reason="quiz_mastery",
            amount=Decimal("40"),
            reference_id=uuid.uuid4(), reference_type="quiz_submission",
        )
        award_mastery_points(
            teacher=self.teacher, reason="assignment_mastery",
            amount=Decimal("60"),
            reference_id=uuid.uuid4(), reference_type="assignment_submission",
        )

    def _login(self, user):
        self.client.defaults["HTTP_HOST"] = self.host
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": user.email, "password": "pass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_teacher_mastery_summary_returns_totals(self):
        self._login(self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/mastery/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(Decimal(data["total_mastery_points"]), Decimal("100.00"))

    def test_teacher_mastery_history_paginated(self):
        self._login(self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/mastery/history/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 2)

    def test_admin_leaderboard_orders_by_total(self):
        other_teacher = _teacher(self.tenant)
        award_mastery_points(
            teacher=other_teacher, reason="quiz_mastery",
            amount=Decimal("200"),
            reference_id=uuid.uuid4(), reference_type="quiz_submission",
        )

        self._login(self.admin)
        resp = self.client.get(
            "/api/v1/gamification/admin/mastery/leaderboard/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        results = resp.json()["results"]
        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0]["rank"], 1)
        self.assertEqual(
            Decimal(results[0]["total_mastery_points"]),
            Decimal("200.00"),
        )

    def test_admin_leaderboard_is_tenant_scoped(self):
        other_tenant = _tenant(subdomain="mpiso")
        other_teacher = _teacher(other_tenant)
        award_mastery_points(
            teacher=other_teacher, reason="quiz_mastery",
            amount=Decimal("500"),
            reference_id=uuid.uuid4(), reference_type="quiz_submission",
        )

        self._login(self.admin)
        resp = self.client.get(
            "/api/v1/gamification/admin/mastery/leaderboard/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        results = resp.json()["results"]
        # The other-tenant teacher must NOT appear in this tenant's board.
        for row in results:
            self.assertNotEqual(row["teacher_id"], str(other_teacher.id))

    def test_teacher_cannot_see_other_teacher_history(self):
        other = _teacher(self.tenant)
        award_mastery_points(
            teacher=other, reason="quiz_mastery",
            amount=Decimal("999"),
            reference_id=uuid.uuid4(), reference_type="quiz_submission",
        )

        self._login(self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/mastery/history/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        teacher_ids = {row["teacher"] for row in resp.json()["results"]}
        self.assertEqual(teacher_ids, {str(self.teacher.id)})
