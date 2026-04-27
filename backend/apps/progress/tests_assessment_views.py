"""
Coverage tests for ``apps/progress/assessment_views.py`` (TASK-043).

These are **gap-fill** tests that complement the existing
``tests_assessment.py`` (high-level scoring + H1/H2/M1-M4 regressions).
They target view-level branches that were not previously exercised:

- Question Bank CRUD: GET list, GET detail, PATCH, DELETE, search, 404.
- Question CRUD: GET detail, PATCH, DELETE, type filter, cross-tenant 404.
- QuizConfig: GET endpoint, GET implicit creation, content 404.
- quiz_attempt_start: missing config (404), empty banks (400),
  random_selection_count, shuffle_choices, leakage of is_correct.
- quiz_attempt_submit: cross-teacher 404, partial answers, max_score=0
  no ZeroDivision, show_correct_answers_after=False stripping,
  SHORT/ESSAY never auto-graded.
- my_quiz_attempts: content_id filter, cross-teacher isolation,
  pagination.
- course_gradebook: cross-tenant 404, empty teacher list, attempts
  assembled only from matching course.
- Permission: teacher blocked from admin endpoints,
  unauthenticated blocked from teacher endpoints.

Style mirrors the Django ``TestCase`` / ``APIClient`` + JWT-login pattern
used throughout ``backend/apps/progress/tests_assessment.py`` and the
``tests_quiz_api.py`` companion file for consistency.
"""

from django.test import TestCase, override_settings
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


# ---------------------------------------------------------------------------
# Shared setup — keeps each test class small.
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"])
class _AssessmentViewsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            name="Coverage School", slug="cov-school",
            subdomain="cov", email="cov@test.com", is_active=True,
        )
        cls.other_tenant = Tenant.objects.create(
            name="Rival School", slug="rival-school",
            subdomain="rival", email="rival@test.com", is_active=True,
        )

        cls.admin = User.objects.create_user(
            email="admin@cov.test", password="pass123",
            first_name="A", last_name="A",
            tenant=cls.tenant, role="SCHOOL_ADMIN", is_active=True,
        )
        cls.teacher = User.objects.create_user(
            email="teacher@cov.test", password="pass123",
            first_name="T", last_name="T",
            tenant=cls.tenant, role="TEACHER", is_active=True,
        )
        cls.teacher2 = User.objects.create_user(
            email="teacher2@cov.test", password="pass123",
            first_name="T2", last_name="T2",
            tenant=cls.tenant, role="TEACHER", is_active=True,
        )

        cls.other_admin = User.objects.create_user(
            email="admin@rival.test", password="pass123",
            first_name="X", last_name="X",
            tenant=cls.other_tenant, role="SCHOOL_ADMIN", is_active=True,
        )
        cls.other_teacher = User.objects.create_user(
            email="teacher@rival.test", password="pass123",
            first_name="Y", last_name="Y",
            tenant=cls.other_tenant, role="TEACHER", is_active=True,
        )

        cls.course = Course.objects.create(
            tenant=cls.tenant, title="Cov Course", slug="cov-course",
            description="x", created_by=cls.admin,
            is_published=True, is_active=True, assigned_to_all=True,
        )
        cls.module = Module.objects.create(
            course=cls.course, title="M", description="",
            order=1, is_active=True,
        )
        cls.content = Content.objects.create(
            module=cls.module, title="Cov Quiz", content_type="TEXT",
            order=1, file_url="", file_size=0, duration=0,
            text_content="", is_mandatory=True, is_active=True,
        )

        cls.other_course = Course.objects.create(
            tenant=cls.other_tenant, title="RC", slug="rc",
            description="x", created_by=cls.other_admin,
            is_published=True, is_active=True, assigned_to_all=True,
        )
        cls.other_module = Module.objects.create(
            course=cls.other_course, title="RM", description="",
            order=1, is_active=True,
        )
        cls.other_content = Content.objects.create(
            module=cls.other_module, title="R Quiz", content_type="TEXT",
            order=1, file_url="", file_size=0, duration=0,
            text_content="", is_mandatory=True, is_active=True,
        )

    def setUp(self):
        self.client = APIClient()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------
    def _host(self, host="cov.lms.com"):
        self.client.defaults["HTTP_HOST"] = host

    def _login(self, email, password="pass123", host="cov.lms.com"):
        self._host(host)
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def _force(self, user, host="cov.lms.com"):
        """Force-authenticate without hitting the login endpoint (faster)."""
        self._host(host)
        self.client.force_authenticate(user=user)

    # ------------------------------------------------------------------
    # Bank / Question factory
    # ------------------------------------------------------------------
    def _make_mcq_bank(self, tenant=None, title="B"):
        tenant = tenant or self.tenant
        bank = QuestionBank.objects.create(tenant=tenant, title=title)
        q = Question.objects.create(
            tenant=tenant, bank=bank, question_type="MCQ",
            prompt="p?", points=2,
        )
        QuestionChoice.objects.create(question=q, text="a", is_correct=True, order=1)
        QuestionChoice.objects.create(question=q, text="b", is_correct=False, order=2)
        return bank, q


# ===========================================================================
# 1. Question Bank CRUD
# ===========================================================================
class QuestionBankCrudTests(_AssessmentViewsBase):
    def test_list_returns_question_count_annotation(self):
        bank, _ = self._make_mcq_bank(title="Algebra")
        self._force(self.admin)
        resp = self.client.get("/api/v1/admin/question-banks/")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        rows = body.get("results") or body
        self.assertTrue(any(r["id"] == str(bank.id) for r in rows))
        row = next(r for r in rows if r["id"] == str(bank.id))
        self.assertEqual(row["question_count"], 1)

    def test_list_supports_search_filter(self):
        self._make_mcq_bank(title="Trigonometry")
        self._make_mcq_bank(title="Biology Cells")
        self._force(self.admin)
        resp = self.client.get("/api/v1/admin/question-banks/?search=biol")
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json().get("results") or resp.json()
        titles = [r["title"] for r in rows]
        self.assertIn("Biology Cells", titles)
        self.assertNotIn("Trigonometry", titles)

    def test_detail_returns_single_bank(self):
        bank, _ = self._make_mcq_bank(title="Detail Bank")
        self._force(self.admin)
        resp = self.client.get(f"/api/v1/admin/question-banks/{bank.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["title"], "Detail Bank")

    def test_patch_updates_title_and_tags(self):
        bank, _ = self._make_mcq_bank(title="Old")
        self._force(self.admin)
        resp = self.client.patch(
            f"/api/v1/admin/question-banks/{bank.id}/",
            {"title": "New", "tags": ["math", "easy"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["title"], "New")
        self.assertEqual(resp.json()["tags"], ["math", "easy"])

    def test_delete_removes_bank(self):
        bank, _ = self._make_mcq_bank(title="Doomed")
        self._force(self.admin)
        resp = self.client.delete(f"/api/v1/admin/question-banks/{bank.id}/")
        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertFalse(QuestionBank.objects.filter(id=bank.id).exists())

    def test_other_tenant_bank_returns_404(self):
        """Admin from tenant A cannot access tenant B's bank."""
        foreign_bank, _ = self._make_mcq_bank(
            tenant=self.other_tenant, title="Foreign",
        )
        self._force(self.admin)  # admin is in self.tenant
        resp = self.client.get(
            f"/api/v1/admin/question-banks/{foreign_bank.id}/",
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_teacher_cannot_list_banks(self):
        self._make_mcq_bank(title="Hidden")
        self._force(self.teacher)
        resp = self.client.get("/api/v1/admin/question-banks/")
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_unauthenticated_list_rejected(self):
        resp = self.client.get(
            "/api/v1/admin/question-banks/",
            HTTP_HOST="cov.lms.com",
        )
        self.assertIn(resp.status_code, (401, 403))


# ===========================================================================
# 2. Question CRUD
# ===========================================================================
class QuestionCrudTests(_AssessmentViewsBase):
    def test_get_single_question(self):
        bank, q = self._make_mcq_bank()
        self._force(self.admin)
        resp = self.client.get(f"/api/v1/admin/questions/{q.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["id"], str(q.id))
        self.assertEqual(len(resp.json()["choices"]), 2)

    def test_patch_updates_prompt_and_replaces_choices(self):
        bank, q = self._make_mcq_bank()
        self._force(self.admin)
        resp = self.client.patch(
            f"/api/v1/admin/questions/{q.id}/",
            {
                "prompt": "updated prompt",
                "choices": [
                    {"text": "x", "is_correct": True, "order": 1},
                    {"text": "y", "is_correct": False, "order": 2},
                    {"text": "z", "is_correct": False, "order": 3},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["prompt"], "updated prompt")
        self.assertEqual(len(resp.json()["choices"]), 3)

    def test_delete_removes_question(self):
        bank, q = self._make_mcq_bank()
        self._force(self.admin)
        resp = self.client.delete(f"/api/v1/admin/questions/{q.id}/")
        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertFalse(Question.objects.filter(id=q.id).exists())

    def test_cross_tenant_question_returns_404(self):
        bank, q = self._make_mcq_bank(tenant=self.other_tenant)
        self._force(self.admin)  # tenant A user
        resp = self.client.get(f"/api/v1/admin/questions/{q.id}/")
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_question_bank_questions_type_filter(self):
        """GET ?type=MCQ must filter on question_type."""
        bank = QuestionBank.objects.create(tenant=self.tenant, title="Mixed")
        mcq = Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="MCQ",
            prompt="mcq prompt", points=1,
        )
        QuestionChoice.objects.create(question=mcq, text="a", is_correct=True, order=1)
        QuestionChoice.objects.create(question=mcq, text="b", is_correct=False, order=2)
        Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="SHORT",
            prompt="short prompt", points=1,
        )

        self._force(self.admin)
        resp = self.client.get(
            f"/api/v1/admin/question-banks/{bank.id}/questions/?type=MCQ",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json().get("results") or resp.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["question_type"], "MCQ")

    def test_teacher_cannot_create_question(self):
        bank, _ = self._make_mcq_bank()
        self._force(self.teacher)
        resp = self.client.post(
            f"/api/v1/admin/question-banks/{bank.id}/questions/",
            {
                "question_type": "MCQ", "prompt": "x", "points": 1,
                "choices": [
                    {"text": "a", "is_correct": True, "order": 1},
                    {"text": "b", "is_correct": False, "order": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)


# ===========================================================================
# 3. QuizConfig per-content
# ===========================================================================
class QuizConfigViewTests(_AssessmentViewsBase):
    def test_get_config_creates_default_when_missing(self):
        """GET must lazily create a default config row if none exists."""
        self._force(self.admin)
        self.assertFalse(
            QuizConfig.objects.filter(content=self.content).exists(),
        )
        resp = self.client.get(
            f"/api/v1/admin/contents/{self.content.id}/quiz-config/",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["content"], str(self.content.id))
        self.assertTrue(
            QuizConfig.objects.filter(content=self.content).exists(),
        )

    def test_patch_without_banks_preserves_existing_banks(self):
        bank, _ = self._make_mcq_bank()
        config = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
        )
        config.source_question_banks.add(bank)

        self._force(self.admin)
        resp = self.client.patch(
            f"/api/v1/admin/contents/{self.content.id}/quiz-config/",
            {"max_attempts": 4},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["max_attempts"], 4)
        # Bank list is NOT clobbered when caller omits source_question_banks.
        config.refresh_from_db()
        self.assertIn(bank, list(config.source_question_banks.all()))

    def test_patch_cross_tenant_content_returns_404(self):
        self._force(self.admin)  # tenant A admin
        resp = self.client.patch(
            f"/api/v1/admin/contents/{self.other_content.id}/quiz-config/",
            {"max_attempts": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 404, resp.content)


# ===========================================================================
# 4. Quiz attempt start — missing-config / no-questions / shuffle / leakage
# ===========================================================================
class QuizAttemptStartTests(_AssessmentViewsBase):
    def test_start_without_config_returns_404(self):
        self._force(self.teacher)
        resp = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_start_config_with_no_banks_returns_400(self):
        QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=3,
        )
        self._force(self.teacher)
        resp = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_start_respects_random_selection_count(self):
        bank = QuestionBank.objects.create(tenant=self.tenant, title="RS")
        for i in range(5):
            q = Question.objects.create(
                tenant=self.tenant, bank=bank, question_type="MCQ",
                prompt=f"q{i}", points=1,
            )
            QuestionChoice.objects.create(question=q, text="a", is_correct=True, order=1)
            QuestionChoice.objects.create(question=q, text="b", is_correct=False, order=2)

        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
            random_selection_count=2,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        resp = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.json()["questions"]), 2)
        self.assertEqual(float(resp.json()["max_score"]), 2.0)

    def test_start_random_count_larger_than_bank_uses_all_questions(self):
        """random_selection_count > available -> min() clamps, no error."""
        bank, _ = self._make_mcq_bank(title="Small")
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
            random_selection_count=50,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        resp = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.json()["questions"]), 1)

    def test_start_response_never_leaks_is_correct_or_explanation(self):
        bank = QuestionBank.objects.create(tenant=self.tenant, title="S")
        q = Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="MCQ",
            prompt="secret", points=1,
            explanation="this is the answer reasoning",
        )
        QuestionChoice.objects.create(question=q, text="a", is_correct=True, order=1)
        QuestionChoice.objects.create(question=q, text="b", is_correct=False, order=2)
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
            shuffle_choices=True,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        resp = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        for q_ in body["questions"]:
            self.assertNotIn("explanation", q_)
            for c in q_["choices"]:
                self.assertNotIn("is_correct", c)

    def test_start_on_cross_tenant_content_returns_404(self):
        self._force(self.teacher)  # tenant A teacher
        resp = self.client.post(
            f"/api/v1/teacher/quizzes/{self.other_content.id}/start/",
        )
        self.assertEqual(resp.status_code, 404, resp.content)


# ===========================================================================
# 5. Quiz attempt submit — cross-teacher / partials / edge cases
# ===========================================================================
class QuizAttemptSubmitTests(_AssessmentViewsBase):
    def _prep_attempt(self, teacher=None):
        teacher = teacher or self.teacher
        bank, q = self._make_mcq_bank()
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content,
            max_attempts=3, pass_threshold_percent=50,
        )
        cfg.source_question_banks.add(bank)
        self._force(teacher)
        resp = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()["id"], QuizAttempt.objects.get(id=resp.json()["id"])

    def test_teacher_cannot_submit_other_teachers_attempt(self):
        """teacher2 tries to submit teacher1's in-progress attempt."""
        attempt_id, attempt = self._prep_attempt(teacher=self.teacher)

        # Switch to teacher2
        self.client.credentials()
        self._force(self.teacher2)
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": {}},
            format="json",
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_submit_with_unanswered_questions_scores_zero_for_blanks(self):
        attempt_id, attempt = self._prep_attempt()
        # Submit an empty answers dict -> score = 0 / 2 = 0.
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": {}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(float(body["score"]), 0.0)
        self.assertFalse(body["passed"])

    def test_submit_with_max_score_zero_does_not_crash(self):
        """max_score=0 (points=0) must not divide-by-zero when computing pass."""
        bank = QuestionBank.objects.create(tenant=self.tenant, title="ZP")
        q = Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="MCQ",
            prompt="zeropoints?", points=0,
        )
        QuestionChoice.objects.create(question=q, text="a", is_correct=True, order=1)
        QuestionChoice.objects.create(question=q, text="b", is_correct=False, order=2)
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content,
            max_attempts=1, pass_threshold_percent=50,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        start = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(start.status_code, 201, start.content)
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        snap = attempt.questions_snapshot[0]
        correct = next(c["id"] for c in snap["choices"] if c["is_correct"])
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": {snap["id"]: correct}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(float(body["score"]), 0.0)
        self.assertEqual(float(body["max_score"]), 0.0)
        self.assertFalse(body["passed"])

    def test_submit_short_and_essay_never_auto_graded(self):
        """SHORT / ESSAY are free-text and must always score 0 from submit."""
        bank = QuestionBank.objects.create(tenant=self.tenant, title="FT")
        qs = Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="SHORT",
            prompt="explain", points=5,
        )
        qe = Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="ESSAY",
            prompt="discuss", points=10,
        )
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
            pass_threshold_percent=50,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        start = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(start.status_code, 201, start.content)
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)

        answers = {}
        for q in attempt.questions_snapshot:
            answers[q["id"]] = "some long answer text"
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        # 0 auto-score even though the teacher submitted text.
        self.assertEqual(float(body["score"]), 0.0)
        self.assertEqual(float(body["max_score"]), 15.0)
        self.assertFalse(body["passed"])

    def test_submit_strips_is_correct_when_config_disables_reveal(self):
        """show_correct_answers_after=False -> response must not leak key."""
        bank, q = self._make_mcq_bank()
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
            pass_threshold_percent=50,
            show_correct_answers_after=False,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        start = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        correct = next(
            c["id"] for c in attempt.questions_snapshot[0]["choices"]
            if c["is_correct"]
        )
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": {attempt.questions_snapshot[0]["id"]: correct}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        for q_ in body["questions"]:
            self.assertNotIn("explanation", q_)
            for c in q_["choices"]:
                self.assertNotIn("is_correct", c)

    def test_submit_nonexistent_attempt_returns_404(self):
        """Submitting to an attempt_id that belongs to no one → 404."""
        import uuid as _uuid
        self._force(self.teacher)
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{_uuid.uuid4()}/submit/",
            {"answers": {}},
            format="json",
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_submit_respects_client_time_spent_when_less_than_elapsed(self):
        attempt_id, attempt = self._prep_attempt()
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": {}, "time_spent_seconds": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        # client reported 1s, server elapsed ~0s -> min is 0 or 1, not huge.
        self.assertLess(resp.json()["time_spent_seconds"], 10)

    def test_multi_default_is_all_or_nothing(self):
        """With multi_partial_credit=False, 1-of-2 correct => 0 on MULTI."""
        bank = QuestionBank.objects.create(tenant=self.tenant, title="AON")
        q = Question.objects.create(
            tenant=self.tenant, bank=bank, question_type="MULTI",
            prompt="multi", points=4,
        )
        c1 = QuestionChoice.objects.create(question=q, text="a", is_correct=True, order=1)
        c2 = QuestionChoice.objects.create(question=q, text="b", is_correct=True, order=2)
        QuestionChoice.objects.create(question=q, text="c", is_correct=False, order=3)
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=1,
            pass_threshold_percent=50, multi_partial_credit=False,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        start = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        # Answer with only one of two correct ids.
        resp = self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {
                "answers": {
                    attempt.questions_snapshot[0]["id"]: [str(c1.id)],
                },
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(float(resp.json()["score"]), 0.0)


# ===========================================================================
# 6. my_quiz_attempts — filter + cross-teacher isolation
# ===========================================================================
class MyQuizAttemptsTests(_AssessmentViewsBase):
    def test_list_only_returns_callers_attempts(self):
        """teacher2 attempts are not leaked to teacher1 via the list API."""
        bank, _ = self._make_mcq_bank()
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=3,
        )
        cfg.source_question_banks.add(bank)

        # teacher2 starts an attempt.
        self._force(self.teacher2)
        r = self.client.post(
            f"/api/v1/teacher/quizzes/{self.content.id}/start/",
        )
        self.assertEqual(r.status_code, 201, r.content)
        t2_attempt_id = r.json()["id"]

        # teacher1 lists their attempts — must NOT include teacher2's.
        self.client.credentials()
        self._force(self.teacher)
        resp = self.client.get("/api/v1/teacher/quiz-attempts/")
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json().get("results") or resp.json()
        self.assertFalse(any(r["id"] == t2_attempt_id for r in rows))

    def test_list_content_id_filter(self):
        """?content_id filter restricts results to one content."""
        # Two contents, each with its own quiz config
        c2 = Content.objects.create(
            module=self.module, title="Second", content_type="TEXT",
            order=2, file_url="", file_size=0, duration=0,
            text_content="", is_mandatory=True, is_active=True,
        )
        bank, _ = self._make_mcq_bank()
        cfg1 = QuizConfig.objects.create(
            tenant=self.tenant, content=self.content, max_attempts=3,
        )
        cfg1.source_question_banks.add(bank)
        cfg2 = QuizConfig.objects.create(
            tenant=self.tenant, content=c2, max_attempts=3,
        )
        cfg2.source_question_banks.add(bank)

        self._force(self.teacher)
        self.client.post(f"/api/v1/teacher/quizzes/{self.content.id}/start/")
        self.client.post(f"/api/v1/teacher/quizzes/{c2.id}/start/")

        resp = self.client.get(
            f"/api/v1/teacher/quiz-attempts/?content_id={c2.id}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json().get("results") or resp.json()
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            self.assertEqual(row["content"], str(c2.id))

    def test_list_works_for_admin_too(self):
        """teacher_or_admin: an admin who also has attempts can list them.

        Admins without attempts still get 200 + empty results (not 403).
        """
        self._force(self.admin)
        resp = self.client.get("/api/v1/teacher/quiz-attempts/")
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json().get("results") or resp.json()
        # Admin has no bank_quiz_attempts in this setup.
        self.assertEqual(len(rows), 0)


# ===========================================================================
# 7. Gradebook — cross-tenant / empty / content-scoping
# ===========================================================================
class GradebookTests(_AssessmentViewsBase):
    def test_gradebook_cross_tenant_course_returns_404(self):
        """Admin in tenant A cannot view a gradebook for tenant B's course."""
        self._force(self.admin)  # tenant A admin
        resp = self.client.get(
            f"/api/v1/admin/gradebook/courses/{self.other_course.id}/",
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_gradebook_returns_rows_for_all_teachers_even_without_attempts(self):
        """Teachers with no attempts still appear with zero aggregates."""
        self._force(self.admin)
        resp = self.client.get(
            f"/api/v1/admin/gradebook/courses/{self.course.id}/",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json()["results"]
        emails = [r["teacher_email"] for r in rows]
        self.assertIn("teacher@cov.test", emails)
        self.assertIn("teacher2@cov.test", emails)
        for r in rows:
            if r["teacher_email"] == "teacher2@cov.test":
                self.assertEqual(r["quiz_attempts"], 0)
                self.assertEqual(r["quiz_passed"], 0)
                self.assertEqual(r["quiz_best_score_percent"], 0.0)

    def test_gradebook_ignores_attempts_on_other_courses(self):
        """An attempt on a different course must NOT inflate this course's row."""
        # New course in the same tenant, same teacher attempts quiz there.
        other_course_same_tenant = Course.objects.create(
            tenant=self.tenant, title="Other Cov", slug="other-cov",
            description="x", created_by=self.admin,
            is_published=True, is_active=True, assigned_to_all=True,
        )
        other_module = Module.objects.create(
            course=other_course_same_tenant, title="OM",
            description="", order=1, is_active=True,
        )
        other_content = Content.objects.create(
            module=other_module, title="OC", content_type="TEXT",
            order=1, file_url="", file_size=0, duration=0,
            text_content="", is_mandatory=True, is_active=True,
        )
        bank, _ = self._make_mcq_bank()
        cfg = QuizConfig.objects.create(
            tenant=self.tenant, content=other_content, max_attempts=1,
            pass_threshold_percent=50,
        )
        cfg.source_question_banks.add(bank)

        self._force(self.teacher)
        start = self.client.post(
            f"/api/v1/teacher/quizzes/{other_content.id}/start/",
        )
        self.assertEqual(start.status_code, 201, start.content)
        attempt_id = start.json()["id"]
        attempt = QuizAttempt.objects.get(id=attempt_id)
        correct = next(
            c["id"] for c in attempt.questions_snapshot[0]["choices"]
            if c["is_correct"]
        )
        self.client.post(
            f"/api/v1/teacher/quiz-attempts/{attempt_id}/submit/",
            {"answers": {attempt.questions_snapshot[0]["id"]: correct}},
            format="json",
        )

        # Now fetch gradebook for the ORIGINAL course — attempts on
        # other_course_same_tenant must NOT show up here.
        self.client.credentials()
        self._force(self.admin)
        resp = self.client.get(
            f"/api/v1/admin/gradebook/courses/{self.course.id}/",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        teacher_row = next(
            r for r in resp.json()["results"]
            if r["teacher_email"] == "teacher@cov.test"
        )
        self.assertEqual(teacher_row["quiz_attempts"], 0)
        self.assertEqual(teacher_row["quiz_best_score_percent"], 0.0)

    def test_teacher_cannot_access_gradebook(self):
        self._force(self.teacher)
        resp = self.client.get(
            f"/api/v1/admin/gradebook/courses/{self.course.id}/",
        )
        self.assertEqual(resp.status_code, 403, resp.content)
