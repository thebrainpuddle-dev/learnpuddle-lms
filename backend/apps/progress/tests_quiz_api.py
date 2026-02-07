from django.test import TestCase
from rest_framework.test import APIClient

from apps.courses.models import Course, Module, Content
from apps.progress.models import Assignment, Quiz, QuizQuestion
from apps.tenants.models import Tenant
from apps.users.models import User


class QuizApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Quiz School",
            slug="quiz-school",
            subdomain="quiz",
            email="quiz@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@quiz.test",
            password="pass123",
            first_name="Admin",
            last_name="Quiz",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@quiz.test",
            password="pass123",
            first_name="Teacher",
            last_name="Quiz",
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
        self.module = Module.objects.create(course=self.course, title="M", description="", order=1, is_active=True)
        self.content = Content.objects.create(
            module=self.module,
            title="V",
            content_type="VIDEO",
            order=1,
            file_url="",
            file_size=1,
            duration=120,
            text_content="",
            is_mandatory=True,
            is_active=True,
        )
        self.assignment = Assignment.objects.create(
            course=self.course,
            module=self.module,
            content=self.content,
            title="Quiz: V",
            description="quiz",
            instructions="",
            generation_source="VIDEO_AUTO",
            generation_metadata={},
        )
        self.quiz = Quiz.objects.create(assignment=self.assignment, is_auto_generated=True)
        self.q1 = QuizQuestion.objects.create(
            quiz=self.quiz,
            order=1,
            question_type="MCQ",
            prompt="Pick",
            options=["A", "B", "C", "D"],
            correct_answer={"option_index": 2},
            points=1,
        )

    def _login(self):
        self.client.defaults["HTTP_HOST"] = "quiz.lms.com"
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": "teacher@quiz.test", "password": "pass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_quiz_detail_and_submit(self):
        self._login()
        detail = self.client.get(f"/api/teacher/quizzes/{self.assignment.id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(len(detail.json()["questions"]), 1)

        submit = self.client.post(
            f"/api/teacher/quizzes/{self.assignment.id}/submit/",
            data={"answers": {str(self.q1.id): {"option_index": 2}}},
            format="json",
        )
        self.assertEqual(submit.status_code, 200, submit.content)
        self.assertEqual(submit.json()["score"], 1.0)

