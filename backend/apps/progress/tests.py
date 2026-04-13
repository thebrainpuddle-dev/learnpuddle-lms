# apps/progress/tests.py
"""
Tenant isolation tests for the progress app models.

Verifies that TenantManager correctly scopes all queries to the current tenant.
Every model with a tenant FK + TenantManager is covered here:
  - TeacherProgress
  - Assignment
  - Quiz
  - QuizQuestion
  - QuizSubmission
  - AssignmentSubmission
  - TeacherQuestClaim

Test strategy:
  1. Create objects for two different tenants
  2. Set the context to tenant_a (via set_current_tenant)
  3. Assert that Model.objects.all() returns only tenant_a records
  4. Assert that Model.all_objects.all() returns all records across tenants
"""

from django.test import TestCase
from django.utils import timezone

from apps.courses.models import Content, Course, Module
from apps.progress.models import (
    Assignment,
    AssignmentSubmission,
    Quiz,
    QuizQuestion,
    QuizSubmission,
    TeacherProgress,
    TeacherQuestClaim,
)
from apps.tenants.models import Tenant
from apps.users.models import User
from utils.tenant_middleware import clear_current_tenant, set_current_tenant


# ────────────────────────────────────────────────────────────────────────────
# Shared fixture helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_tenant(name, subdomain):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"{subdomain}@test.com", is_active=True,
    )


def _make_admin(tenant, idx):
    return User.objects.create_user(
        email=f"admin{idx}@tenant{idx}.test",
        password="testpass123",
        first_name="Admin", last_name=str(idx),
        tenant=tenant, role="SCHOOL_ADMIN", is_active=True,
    )


def _make_teacher(tenant, idx):
    return User.objects.create_user(
        email=f"teacher{idx}@tenant{idx}.test",
        password="testpass123",
        first_name="Teacher", last_name=str(idx),
        tenant=tenant, role="TEACHER", is_active=True,
    )


def _make_course(tenant, admin, idx):
    return Course.objects.create(
        tenant=tenant, title=f"Course {idx}", slug=f"course-{idx}",
        description="x", created_by=admin,
        is_published=True, is_active=True, assigned_to_all=True,
    )


def _make_module(course, idx):
    return Module.objects.create(
        course=course, title=f"Module {idx}", description="", order=idx, is_active=True,
    )


def _make_content(module, idx):
    return Content.objects.create(
        module=module, title=f"Content {idx}", content_type="TEXT",
        order=idx, file_url="", file_size=0, duration=10,
        text_content="hello", is_mandatory=True, is_active=True,
    )


# ────────────────────────────────────────────────────────────────────────────
# TeacherProgress tenant isolation
# ────────────────────────────────────────────────────────────────────────────

class TeacherProgressTenantIsolationTestCase(TestCase):
    """TenantManager on TeacherProgress filters by the current tenant."""

    def setUp(self):
        self.tenant_a = _make_tenant("School A", "iso-a")
        self.tenant_b = _make_tenant("School B", "iso-b")

        admin_a = _make_admin(self.tenant_a, 1)
        admin_b = _make_admin(self.tenant_b, 2)
        self.teacher_a = _make_teacher(self.tenant_a, 1)
        self.teacher_b = _make_teacher(self.tenant_b, 2)

        self.course_a = _make_course(self.tenant_a, admin_a, 1)
        self.course_b = _make_course(self.tenant_b, admin_b, 2)

        mod_a = _make_module(self.course_a, 1)
        mod_b = _make_module(self.course_b, 2)
        self.content_a = _make_content(mod_a, 1)
        self.content_b = _make_content(mod_b, 2)

        # Use all_objects manager to bypass TenantManager during setup
        self.prog_a = TeacherProgress.all_objects.create(
            tenant=self.tenant_a,
            teacher=self.teacher_a,
            course=self.course_a,
            content=self.content_a,
        )
        self.prog_b = TeacherProgress.all_objects.create(
            tenant=self.tenant_b,
            teacher=self.teacher_b,
            course=self.course_b,
            content=self.content_b,
        )

    def tearDown(self):
        clear_current_tenant()

    def test_objects_all_filters_to_tenant_a(self):
        set_current_tenant(self.tenant_a)
        ids = list(TeacherProgress.objects.all().values_list("id", flat=True))
        self.assertIn(self.prog_a.id, ids)
        self.assertNotIn(self.prog_b.id, ids)

    def test_objects_all_filters_to_tenant_b(self):
        set_current_tenant(self.tenant_b)
        ids = list(TeacherProgress.objects.all().values_list("id", flat=True))
        self.assertIn(self.prog_b.id, ids)
        self.assertNotIn(self.prog_a.id, ids)

    def test_all_objects_bypasses_tenant_filter(self):
        """all_objects manager returns records across all tenants."""
        ids = list(TeacherProgress.all_objects.all().values_list("id", flat=True))
        self.assertIn(self.prog_a.id, ids)
        self.assertIn(self.prog_b.id, ids)

    def test_no_active_tenant_context_does_not_filter(self):
        """When no tenant context is active, TenantManager performs no filtering.
        Both records are visible — the TenantManager guard only applies when a
        tenant is present. Real API requests always have a tenant set by middleware.
        """
        clear_current_tenant()
        self.assertEqual(TeacherProgress.objects.all().count(), 2)


# ────────────────────────────────────────────────────────────────────────────
# Assignment tenant isolation
# ────────────────────────────────────────────────────────────────────────────

class AssignmentTenantIsolationTestCase(TestCase):

    def setUp(self):
        self.tenant_a = _make_tenant("Assign School A", "assign-a")
        self.tenant_b = _make_tenant("Assign School B", "assign-b")

        admin_a = _make_admin(self.tenant_a, 11)
        admin_b = _make_admin(self.tenant_b, 12)

        self.course_a = _make_course(self.tenant_a, admin_a, 11)
        self.course_b = _make_course(self.tenant_b, admin_b, 12)

        self.assign_a = Assignment.all_objects.create(
            tenant=self.tenant_a, course=self.course_a,
            title="Assignment A", description="desc",
        )
        self.assign_b = Assignment.all_objects.create(
            tenant=self.tenant_b, course=self.course_b,
            title="Assignment B", description="desc",
        )

    def tearDown(self):
        clear_current_tenant()

    def test_tenant_a_sees_only_tenant_a_assignments(self):
        set_current_tenant(self.tenant_a)
        ids = list(Assignment.objects.all().values_list("id", flat=True))
        self.assertIn(self.assign_a.id, ids)
        self.assertNotIn(self.assign_b.id, ids)

    def test_tenant_b_sees_only_tenant_b_assignments(self):
        set_current_tenant(self.tenant_b)
        ids = list(Assignment.objects.all().values_list("id", flat=True))
        self.assertIn(self.assign_b.id, ids)
        self.assertNotIn(self.assign_a.id, ids)

    def test_all_objects_returns_both(self):
        ids = list(Assignment.all_objects.all().values_list("id", flat=True))
        self.assertIn(self.assign_a.id, ids)
        self.assertIn(self.assign_b.id, ids)


# ────────────────────────────────────────────────────────────────────────────
# Quiz + QuizQuestion + QuizSubmission tenant isolation
# ────────────────────────────────────────────────────────────────────────────

class QuizModelsTenantIsolationTestCase(TestCase):

    def setUp(self):
        self.tenant_a = _make_tenant("Quiz School A", "quiz-iso-a")
        self.tenant_b = _make_tenant("Quiz School B", "quiz-iso-b")

        admin_a = _make_admin(self.tenant_a, 21)
        admin_b = _make_admin(self.tenant_b, 22)
        self.teacher_a = _make_teacher(self.tenant_a, 21)
        self.teacher_b = _make_teacher(self.tenant_b, 22)

        course_a = _make_course(self.tenant_a, admin_a, 21)
        course_b = _make_course(self.tenant_b, admin_b, 22)

        assign_a = Assignment.all_objects.create(
            tenant=self.tenant_a, course=course_a, title="A", description="d"
        )
        assign_b = Assignment.all_objects.create(
            tenant=self.tenant_b, course=course_b, title="B", description="d"
        )

        self.quiz_a = Quiz.all_objects.create(tenant=self.tenant_a, assignment=assign_a)
        self.quiz_b = Quiz.all_objects.create(tenant=self.tenant_b, assignment=assign_b)

        self.question_a = QuizQuestion.all_objects.create(
            tenant=self.tenant_a, quiz=self.quiz_a, order=1,
            question_type="MCQ", prompt="Q?",
            options=["A", "B"], correct_answer={"option_index": 0},
        )
        self.question_b = QuizQuestion.all_objects.create(
            tenant=self.tenant_b, quiz=self.quiz_b, order=1,
            question_type="MCQ", prompt="Q?",
            options=["A", "B"], correct_answer={"option_index": 0},
        )

        self.submission_a = QuizSubmission.all_objects.create(
            tenant=self.tenant_a, quiz=self.quiz_a, teacher=self.teacher_a, answers={},
        )
        self.submission_b = QuizSubmission.all_objects.create(
            tenant=self.tenant_b, quiz=self.quiz_b, teacher=self.teacher_b, answers={},
        )

    def tearDown(self):
        clear_current_tenant()

    def test_quiz_filters_to_tenant_a(self):
        set_current_tenant(self.tenant_a)
        ids = list(Quiz.objects.all().values_list("id", flat=True))
        self.assertIn(self.quiz_a.id, ids)
        self.assertNotIn(self.quiz_b.id, ids)

    def test_quiz_question_filters_to_tenant_a(self):
        set_current_tenant(self.tenant_a)
        ids = list(QuizQuestion.objects.all().values_list("id", flat=True))
        self.assertIn(self.question_a.id, ids)
        self.assertNotIn(self.question_b.id, ids)

    def test_quiz_submission_filters_to_tenant_a(self):
        set_current_tenant(self.tenant_a)
        ids = list(QuizSubmission.objects.all().values_list("id", flat=True))
        self.assertIn(self.submission_a.id, ids)
        self.assertNotIn(self.submission_b.id, ids)

    def test_quiz_all_objects_bypasses_filter(self):
        ids = list(Quiz.all_objects.all().values_list("id", flat=True))
        self.assertIn(self.quiz_a.id, ids)
        self.assertIn(self.quiz_b.id, ids)

    def test_quiz_question_all_objects_bypasses_filter(self):
        ids = list(QuizQuestion.all_objects.all().values_list("id", flat=True))
        self.assertIn(self.question_a.id, ids)
        self.assertIn(self.question_b.id, ids)


# ────────────────────────────────────────────────────────────────────────────
# AssignmentSubmission tenant isolation
# ────────────────────────────────────────────────────────────────────────────

class AssignmentSubmissionTenantIsolationTestCase(TestCase):

    def setUp(self):
        self.tenant_a = _make_tenant("Sub School A", "sub-iso-a")
        self.tenant_b = _make_tenant("Sub School B", "sub-iso-b")

        admin_a = _make_admin(self.tenant_a, 31)
        admin_b = _make_admin(self.tenant_b, 32)
        self.teacher_a = _make_teacher(self.tenant_a, 31)
        self.teacher_b = _make_teacher(self.tenant_b, 32)

        course_a = _make_course(self.tenant_a, admin_a, 31)
        course_b = _make_course(self.tenant_b, admin_b, 32)

        assign_a = Assignment.all_objects.create(
            tenant=self.tenant_a, course=course_a, title="A", description="d"
        )
        assign_b = Assignment.all_objects.create(
            tenant=self.tenant_b, course=course_b, title="B", description="d"
        )

        self.sub_a = AssignmentSubmission.objects.create(
            tenant=self.tenant_a, assignment=assign_a, teacher=self.teacher_a,
        )
        self.sub_b = AssignmentSubmission.objects.create(
            tenant=self.tenant_b, assignment=assign_b, teacher=self.teacher_b,
        )

    def tearDown(self):
        clear_current_tenant()

    def test_tenant_a_sees_only_own_submissions(self):
        set_current_tenant(self.tenant_a)
        ids = list(AssignmentSubmission.objects.all().values_list("id", flat=True))
        self.assertIn(self.sub_a.id, ids)
        self.assertNotIn(self.sub_b.id, ids)

    def test_all_objects_returns_both(self):
        ids = list(AssignmentSubmission.all_objects.all().values_list("id", flat=True))
        self.assertIn(self.sub_a.id, ids)
        self.assertIn(self.sub_b.id, ids)


# ────────────────────────────────────────────────────────────────────────────
# TeacherQuestClaim tenant isolation
# ────────────────────────────────────────────────────────────────────────────

class TeacherQuestClaimTenantIsolationTestCase(TestCase):

    def setUp(self):
        self.tenant_a = _make_tenant("Quest School A", "quest-iso-a")
        self.tenant_b = _make_tenant("Quest School B", "quest-iso-b")

        self.teacher_a = _make_teacher(self.tenant_a, 41)
        self.teacher_b = _make_teacher(self.tenant_b, 42)

        today = timezone.localdate()

        self.claim_a = TeacherQuestClaim.objects.create(
            tenant=self.tenant_a, teacher=self.teacher_a,
            quest_key="daily_login", claim_date=today, points_awarded=10,
        )
        self.claim_b = TeacherQuestClaim.objects.create(
            tenant=self.tenant_b, teacher=self.teacher_b,
            quest_key="daily_login", claim_date=today, points_awarded=10,
        )

    def tearDown(self):
        clear_current_tenant()

    def test_tenant_a_sees_only_own_claims(self):
        set_current_tenant(self.tenant_a)
        ids = list(TeacherQuestClaim.objects.all().values_list("id", flat=True))
        self.assertIn(self.claim_a.id, ids)
        self.assertNotIn(self.claim_b.id, ids)

    def test_tenant_b_sees_only_own_claims(self):
        set_current_tenant(self.tenant_b)
        ids = list(TeacherQuestClaim.objects.all().values_list("id", flat=True))
        self.assertIn(self.claim_b.id, ids)
        self.assertNotIn(self.claim_a.id, ids)

    def test_all_objects_returns_all_tenants(self):
        ids = list(TeacherQuestClaim.all_objects.all().values_list("id", flat=True))
        self.assertIn(self.claim_a.id, ids)
        self.assertIn(self.claim_b.id, ids)
