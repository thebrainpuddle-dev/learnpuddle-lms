import threading

from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.assessment_models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuizAttempt,
    QuizConfig,
)
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class AssessmentApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Assess School",
            slug="assess-school",
            subdomain="assess",
            email="assess@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@assess.test",
            password="pass123",
            first_name="Admin",
            last_name="A",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@assess.test",
            password="pass123",
            first_name="T",
            last_name="Q",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Course",
            slug="course",
            description="x",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="M", description="", order=1, is_active=True,
        )
        self.content = Content.objects.create(
            module=self.module,
            title="Quiz 1",
            content_type="TEXT",
            order=1,
            file_url="",
            file_size=0,
            duration=0,
            text_content="",
            is_mandatory=True,
            is_active=True,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _host(self):
        self.client.defaults["HTTP_HOST"] = "assess.lms.com"

    def _login(self, email, password="pass123"):
        self._host()
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def _make_bank_with_questions(self):
        bank = QuestionBank.objects.create(
            tenant=self.tenant, title="Math Basics",
        )
        q1 = Question.objects.create(
            tenant=self.tenant,
            bank=bank,
            question_type="MCQ",
            prompt="2+2?",
            points=2,
        )
        QuestionChoice.objects.create(question=q1, text="3", is_correct=False, order=1)
        QuestionChoice.objects.create(question=q1, text="4", is_correct=True, order=2)
        QuestionChoice.objects.create(question=q1, text="5", is_correct=False, order=3)

        q2 = Question.objects.create(
            tenant=self.tenant,
            bank=bank,
            question_type="TRUE_FALSE",
            prompt="Python is typed?",
            points=1,
        )
        QuestionChoice.objects.create(question=q2, text="True", is_correct=True, order=1)
        QuestionChoice.objects.create(question=q2, text="False", is_correct=False, order=2)

        q3 = Question.objects.create(
            tenant=self.tenant,
            bank=bank,
            question_type="MULTI",
            prompt="Prime numbers?",
            points=3,
        )
        QuestionChoice.objects.create(question=q3, text="2", is_correct=True, order=1)
        QuestionChoice.objects.create(question=q3, text="4", is_correct=False, order=2)
        QuestionChoice.objects.create(question=q3, text="7", is_correct=True, order=3)
        QuestionChoice.objects.create(question=q3, text="9", is_correct=False, order=4)
        return bank, q1, q2, q3

    # ------------------------------------------------------------------
    # Admin: question-bank CRUD + questions
    # ------------------------------------------------------------------
    def test_admin_creates_bank_and_questions(self):
        self._login("admin@assess.test")
        resp = self.client.post(
            "/api/v1/admin/question-banks/",
            {"title": "Bank 1", "description": "desc"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        bank_id = resp.json()["id"]

        # Add a question
        resp = self.client.post(
            f"/api/v1/admin/question-banks/{bank_id}/questions/",
            {
                "question_type": "MCQ",
                "prompt": "Which is HTTPS port?",
                "points": 1,
                "choices": [
                    {"text": "80", "is_correct": False, "order": 1},
                    {"text": "443", "is_correct": True, "order": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.json()["choices"]), 2)

        # List
        resp = self.client.get(f"/api/v1/admin/question-banks/{bank_id}/questions/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()["results"]), 1)

    # ------------------------------------------------------------------
    # Admin: quiz config
    # ------------------------------------------------------------------
    def test_admin_configures_quiz(self):
        self._login("admin@assess.test")
        bank, *_ = self._make_bank_with_questions()

        resp = self.client.patch(
            f"/api/v1/admin/contents/{self.content.id}/quiz-config/",
            {
                "time_limit_seconds": 600,
                "max_attempts": 3,
                "pass_threshold_percent": "60.0",
                "shuffle_questions": True,
                "shuffle_choices": True,
                "random_selection_count": 2,
                "source_question_banks": [str(bank.id)],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["max_attempts"], 3)
        self.assertEqual(resp.json()["random_selection_count"], 2)
        self.assertIn(str(bank.id), resp.json()["source_question_banks"])

    # ------------------------------------------------------------------
    # Teacher: start + submit + scoring
    # ------------------------------------------------------------------
    def test_teacher_start_and_submit_scoring(self):
        bank, q1, q2, q3 = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            time_limit_seconds=0,
            max_attempts=2,
            pass_threshold_percent=50,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")

        resp = self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        attempt_id = data["id"]
        self.assertEqual(len(data["questions"]), 3)
        self.assertEqual(data["max_score"], 6.0)
        # No is_correct leaked to teacher
        for q in data["questions"]:
            for c in q["choices"]:
                self.assertNotIn("is_correct", c)

        # Build correct answers from snapshot (server-stored)
        attempt = QuizAttempt.objects.get(id=attempt_id)
        answers = {}
        for q in attempt.questions_snapshot:
            if q["type"] == "MCQ":
                correct_id = next(c["id"] for c in q["choices"] if c["is_correct"])
                answers[q["id"]] = correct_id
            elif q["type"] == "TRUE_FALSE":
                correct_id = next(c["id"] for c in q["choices"] if c["is_correct"])
                answers[q["id"]] = correct_id
            elif q["type"] == "MULTI":
                correct_ids = [c["id"] for c in q["choices"] if c["is_correct"]]
                answers[q["id"]] = correct_ids

        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers, "time_spent_seconds": 42},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], "SUBMITTED")
        self.assertEqual(body["score"], 6.0)
        self.assertEqual(body["max_score"], 6.0)
        self.assertTrue(body["passed"])

        # Re-submit same attempt should fail
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_teacher_max_attempts_enforced(self):
        bank, *_ = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            max_attempts=1,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")

        resp = self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        self.assertEqual(resp.status_code, 201, resp.content)

        # Second attempt should be denied
        resp = self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_teacher_attempt_list(self):
        bank, *_ = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=3,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")
        self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")

        resp = self.client.get("/api/v1/teacher/quiz-attempts/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertGreaterEqual(len(resp.json()["results"]), 1)

    # ------------------------------------------------------------------
    # Admin: gradebook
    # ------------------------------------------------------------------
    def test_admin_gradebook_aggregates(self):
        bank, *_ = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=3,
            pass_threshold_percent=50,
        )
        config.source_question_banks.add(bank)

        # Teacher attempts the quiz
        self._login("teacher@assess.test")
        start = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        answers = {}
        for q in attempt.questions_snapshot:
            if q["choices"]:
                correct = [c["id"] for c in q["choices"] if c["is_correct"]]
                answers[q["id"]] = correct if q["type"] == "MULTI" else (correct[0] if correct else None)
        self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers},
            format="json",
        )

        # Admin pulls gradebook
        self.client.credentials()
        self._login("admin@assess.test")
        resp = self.client.get(f"/api/v1/admin/gradebook/courses/{self.course.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json()["results"]
        self.assertGreaterEqual(len(rows), 1)
        teacher_row = next(r for r in rows if r["teacher_email"] == "teacher@assess.test")
        self.assertEqual(teacher_row["quiz_attempts"], 1)
        self.assertEqual(teacher_row["quiz_passed"], 1)
        self.assertAlmostEqual(teacher_row["quiz_best_score_percent"], 100.0, places=1)


# ======================================================================
# Revision-2 regression tests for reviewer-found issues.
# ======================================================================
@override_settings(ALLOWED_HOSTS=["*"])
class AssessmentRevisionRegressionTests(AssessmentApiTestCase):
    """Regression tests for the issues raised in revision 1 review."""

    # ------------------------------------------------------------------
    # H1 — answer key must never leak mid-attempt.
    # ------------------------------------------------------------------
    def test_H1_list_attempts_strips_answer_key_in_progress(self):
        bank, *_ = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            max_attempts=3,
            show_correct_answers_after=True,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")
        self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")

        resp = self.client.get("/api/v1/teacher/quiz-attempts/")
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json()["results"]
        self.assertGreaterEqual(len(rows), 1)
        in_progress_rows = [r for r in rows if r["status"] == "IN_PROGRESS"]
        self.assertTrue(in_progress_rows)
        for row in in_progress_rows:
            for q in row["questions_snapshot"]:
                self.assertNotIn("explanation", q)
                for c in q["choices"]:
                    self.assertNotIn("is_correct", c)

    def test_H1_list_attempts_strips_answer_key_when_config_hides(self):
        bank, *_ = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            max_attempts=3,
            show_correct_answers_after=False,
            pass_threshold_percent=50,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")
        start = self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        answers = {}
        for q in attempt.questions_snapshot:
            if q["choices"]:
                correct = [c["id"] for c in q["choices"] if c["is_correct"]]
                answers[q["id"]] = (
                    correct if q["type"] == "MULTI" else (correct[0] if correct else None)
                )
        self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers},
            format="json",
        )

        resp = self.client.get("/api/v1/teacher/quiz-attempts/")
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json()["results"]
        self.assertTrue(rows)
        for row in rows:
            for q in row["questions_snapshot"]:
                self.assertNotIn("explanation", q)
                for c in q["choices"]:
                    self.assertNotIn("is_correct", c)

    def test_H1_list_attempts_reveals_answer_key_only_when_allowed(self):
        bank, *_ = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            max_attempts=3,
            show_correct_answers_after=True,
            pass_threshold_percent=50,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")
        start = self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        answers = {}
        for q in attempt.questions_snapshot:
            if q["choices"]:
                correct = [c["id"] for c in q["choices"] if c["is_correct"]]
                answers[q["id"]] = (
                    correct if q["type"] == "MULTI" else (correct[0] if correct else None)
                )
        self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers},
            format="json",
        )
        resp = self.client.get("/api/v1/teacher/quiz-attempts/")
        submitted = [r for r in resp.json()["results"] if r["status"] == "SUBMITTED"]
        self.assertTrue(submitted)
        # At least one choice must still carry is_correct when showing is allowed.
        flagged = False
        for row in submitted:
            for q in row["questions_snapshot"]:
                for c in q["choices"]:
                    if "is_correct" in c:
                        flagged = True
        self.assertTrue(flagged)

    # ------------------------------------------------------------------
    # H3 — gradebook "best score %" must take max of per-attempt percents.
    # ------------------------------------------------------------------
    def test_H3_gradebook_best_percent_uses_per_attempt_math(self):
        bank, q1, q2, q3 = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            max_attempts=5,
            pass_threshold_percent=50,
            random_selection_count=1,
        )
        config.source_question_banks.add(bank)

        # Attempt A: score=0 on a max=2 attempt (the MCQ only)
        attempt_a = QuizAttempt.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            content=self.content,
            attempt_number=1,
            status="SUBMITTED",
            questions_snapshot=[{"id": str(q1.id), "type": "MCQ", "points": 2, "choices": []}],
            answers={},
            score=0,
            max_score=2,
            passed=False,
        )
        # Attempt B: perfect score on a max=1 attempt (TRUE_FALSE only)
        attempt_b = QuizAttempt.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            content=self.content,
            attempt_number=2,
            status="SUBMITTED",
            questions_snapshot=[{"id": str(q2.id), "type": "TRUE_FALSE", "points": 1, "choices": []}],
            answers={},
            score=1,
            max_score=1,
            passed=True,
        )

        self._login("admin@assess.test")
        resp = self.client.get(f"/api/v1/admin/gradebook/courses/{self.course.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        teacher_row = next(
            r for r in resp.json()["results"]
            if r["teacher_email"] == "teacher@assess.test"
        )
        self.assertEqual(teacher_row["quiz_attempts"], 2)
        # Old (buggy) math would be max(0,1) / max(2,1) = 50.0.
        # Correct math is max(0/2, 1/1) = 100.0.
        self.assertAlmostEqual(teacher_row["quiz_best_score_percent"], 100.0, places=1)

    # ------------------------------------------------------------------
    # M2 — cross-tenant bank IDs must be rejected with 400.
    # ------------------------------------------------------------------
    def test_M2_cross_tenant_bank_rejected_with_400(self):
        # Build a second tenant + bank the real tenant should NOT see.
        other_tenant = Tenant.objects.create(
            name="Other School", slug="other", subdomain="other",
            email="other@test.com", is_active=True,
        )
        other_bank = QuestionBank.objects.create(
            tenant=other_tenant, title="Foreign Bank",
        )

        self._login("admin@assess.test")
        resp = self.client.patch(
            f"/api/v1/admin/contents/{self.content.id}/quiz-config/",
            {"source_question_banks": [str(other_bank.id)]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertIn("error", body)
        self.assertEqual(body["error"].get("code"), "CROSS_TENANT_BANK")

    # ------------------------------------------------------------------
    # M3 — answers arriving past the deadline must be discarded.
    # ------------------------------------------------------------------
    def test_M3_late_submission_scores_zero(self):
        from django.utils import timezone
        from datetime import timedelta

        bank, q1, *_ = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            time_limit_seconds=60,
            max_attempts=1,
            pass_threshold_percent=50,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")
        start = self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        self.assertEqual(start.status_code, 201, start.content)
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        # Back-date started_at 10 minutes so elapsed > time_limit + 5.
        QuizAttempt.objects.filter(id=attempt.id).update(
            started_at=timezone.now() - timedelta(minutes=10),
        )
        attempt.refresh_from_db()
        answers = {}
        for q in attempt.questions_snapshot:
            if q["choices"]:
                correct = [c["id"] for c in q["choices"] if c["is_correct"]]
                answers[q["id"]] = (
                    correct if q["type"] == "MULTI" else (correct[0] if correct else None)
                )
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], "EXPIRED")
        # Late-arriving answers are discarded → score 0 even with correct payload.
        self.assertEqual(float(body["score"]), 0.0)
        self.assertFalse(body["passed"])

    # ------------------------------------------------------------------
    # M4 — question type / choice validation.
    # ------------------------------------------------------------------
    def test_M4_mcq_requires_exactly_one_correct(self):
        self._login("admin@assess.test")
        # Create a bank first.
        r = self.client.post(
            "/api/v1/admin/question-banks/",
            {"title": "Validation Bank"},
            format="json",
        )
        bank_id = r.json()["id"]

        # MCQ with zero correct choices → 400.
        resp = self.client.post(
            f"/api/v1/admin/question-banks/{bank_id}/questions/",
            {
                "question_type": "MCQ",
                "prompt": "pick one",
                "points": 1,
                "choices": [
                    {"text": "a", "is_correct": False, "order": 1},
                    {"text": "b", "is_correct": False, "order": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

        # MCQ with multiple correct choices → 400.
        resp = self.client.post(
            f"/api/v1/admin/question-banks/{bank_id}/questions/",
            {
                "question_type": "MCQ",
                "prompt": "pick one",
                "points": 1,
                "choices": [
                    {"text": "a", "is_correct": True, "order": 1},
                    {"text": "b", "is_correct": True, "order": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_M4_multi_requires_at_least_two_correct(self):
        self._login("admin@assess.test")
        r = self.client.post(
            "/api/v1/admin/question-banks/",
            {"title": "Multi Bank"},
            format="json",
        )
        bank_id = r.json()["id"]
        resp = self.client.post(
            f"/api/v1/admin/question-banks/{bank_id}/questions/",
            {
                "question_type": "MULTI",
                "prompt": "pick many",
                "points": 2,
                "choices": [
                    {"text": "a", "is_correct": True, "order": 1},
                    {"text": "b", "is_correct": False, "order": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_M4_empty_choice_text_rejected(self):
        self._login("admin@assess.test")
        r = self.client.post(
            "/api/v1/admin/question-banks/",
            {"title": "Empty Bank"},
            format="json",
        )
        bank_id = r.json()["id"]
        resp = self.client.post(
            f"/api/v1/admin/question-banks/{bank_id}/questions/",
            {
                "question_type": "MCQ",
                "prompt": "pick one",
                "points": 1,
                "choices": [
                    {"text": "   ", "is_correct": True, "order": 1},
                    {"text": "b", "is_correct": False, "order": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    # ------------------------------------------------------------------
    # M1 — partial credit on MULTI when enabled.
    # ------------------------------------------------------------------
    def test_M1_multi_partial_credit_awards_fraction(self):
        bank, q1, q2, q3 = self._make_bank_with_questions()
        config = QuizConfig.objects.create(
            tenant=self.tenant,
            content=self.content,
            max_attempts=1,
            pass_threshold_percent=50,
            multi_partial_credit=True,
        )
        config.source_question_banks.add(bank)

        self._login("teacher@assess.test")
        start = self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)

        # Build answers: MCQ correct, TRUE_FALSE correct, MULTI only 1 of 2
        # correct options -> 1/2 credit → 1.5 points out of 3 for MULTI.
        answers = {}
        for q in attempt.questions_snapshot:
            if q["type"] == "MULTI":
                correct = [c["id"] for c in q["choices"] if c["is_correct"]]
                answers[q["id"]] = [correct[0]]  # pick only first of two correct
            elif q["choices"]:
                correct = [c["id"] for c in q["choices"] if c["is_correct"]]
                answers[q["id"]] = correct[0]
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        # 2 (MCQ) + 1 (TF) + 1.5 (MULTI partial) = 4.5 out of 6.
        self.assertAlmostEqual(float(body["score"]), 4.5, places=1)


# ======================================================================
# H2 — race on parallel start must serialize (TransactionTestCase so that
# each thread sees real transactions against the DB).
# ======================================================================
@override_settings(ALLOWED_HOSTS=["*"])
class QuizAttemptRaceTests(TransactionTestCase):
    """Concurrent quiz_attempt_start calls must not overrun max_attempts."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Race School", slug="race", subdomain="race",
            email="race@test.com", is_active=True,
        )
        self.admin = User.objects.create_user(
            email="radmin@race.test", password="pass123",
            first_name="R", last_name="A",
            tenant=self.tenant, role="SCHOOL_ADMIN", is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="rteacher@race.test", password="pass123",
            first_name="R", last_name="T",
            tenant=self.tenant, role="TEACHER", is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant, title="RC", slug="rc", description="",
            created_by=self.admin, is_published=True, is_active=True,
            assigned_to_all=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="RM", description="", order=1, is_active=True,
        )
        self.content = Content.objects.create(
            module=self.module, title="Race Quiz", content_type="TEXT",
            order=1, file_url="", file_size=0, duration=0,
            text_content="", is_mandatory=True, is_active=True,
        )
        bank = QuestionBank.objects.create(tenant=self.tenant, title="RB")
        q = Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="MCQ",
            prompt="?", points=1,
        )
        QuestionChoice.objects.create(question=q, text="a", is_correct=True, order=1)
        QuestionChoice.objects.create(question=q, text="b", is_correct=False, order=2)
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
        )
        cfg.source_question_banks.add(bank)

    def test_H2_parallel_start_calls_do_not_overrun_max_attempts(self):
        # Log in once; reuse the bearer token from a single session for both
        # threads. Each thread uses its own APIClient so the credentials dict
        # is not clobbered.
        client0 = APIClient()
        client0.defaults["HTTP_HOST"] = "race.lms.com"
        resp = client0.post(
            "/api/users/auth/login/",
            {"email": "rteacher@race.test", "password": "pass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]

        url = f"/api/v1/teacher/quizzes/{self.content.id}/start/"
        results = []
        lock = threading.Lock()

        def _call():
            c = APIClient()
            c.defaults["HTTP_HOST"] = "race.lms.com"
            c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
            r = c.post(url)
            with lock:
                results.append(r.status_code)
            # Each worker owns its own DB connection; close to avoid leaks.
            for conn in connections.all():
                conn.close()

        t1 = threading.Thread(target=_call)
        t2 = threading.Thread(target=_call)
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Exactly one 201 and exactly one denial (403 or 409, never 500).
        self.assertEqual(len(results), 2)
        self.assertEqual(results.count(201), 1, results)
        self.assertEqual(sum(1 for s in results if s in (403, 409)), 1, results)
        # The DB must have at most one attempt row for this teacher+content.
        self.assertEqual(
            QuizAttempt.objects.filter(
                teacher=self.teacher, content=self.content,
            ).count(),
            1,
        )
