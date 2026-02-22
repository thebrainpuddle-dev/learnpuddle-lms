from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.models import Assignment, TeacherProgress
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class TeacherMvpApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="MVP School",
            slug="mvp-school",
            subdomain="mvp",
            email="mvp@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@mvp.test",
            password="pass123",
            first_name="Admin",
            last_name="MVP",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@mvp.test",
            password="pass123",
            first_name="Teacher",
            last_name="MVP",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Course Locking",
            slug="course-locking",
            description="x",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
            deadline=timezone.localdate() + timedelta(days=3),
        )
        self.module_1 = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="First module",
            order=1,
            is_active=True,
        )
        self.module_2 = Module.objects.create(
            course=self.course,
            title="Module 2",
            description="Second module",
            order=2,
            is_active=True,
        )
        self.content_1 = Content.objects.create(
            module=self.module_1,
            title="Lesson 1",
            content_type="TEXT",
            order=1,
            text_content="<p>Welcome</p>",
            is_active=True,
        )
        self.content_2 = Content.objects.create(
            module=self.module_2,
            title="Lesson 2",
            content_type="TEXT",
            order=1,
            text_content="<p>Locked</p>",
            is_active=True,
        )
        self.assignment = Assignment.objects.create(
            course=self.course,
            module=self.module_1,
            content=self.content_1,
            title="Practice Quiz",
            description="Due soon",
            instructions="",
            due_date=timezone.now() + timedelta(days=1),
            generation_source="MANUAL",
            generation_metadata={},
            is_active=True,
        )

    def _login(self):
        self.client.defaults["HTTP_HOST"] = "mvp.lms.com"
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": "teacher@mvp.test", "password": "pass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_course_detail_returns_locking_state(self):
        self._login()
        resp = self.client.get(f"/api/teacher/courses/{self.course.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        modules = resp.json()["modules"]
        self.assertEqual(len(modules), 2)

        self.assertFalse(modules[0]["is_locked"])
        self.assertTrue(modules[1]["is_locked"])
        self.assertFalse(modules[0]["contents"][0]["is_locked"])
        self.assertTrue(modules[1]["contents"][0]["is_locked"])

    def test_progress_start_blocks_locked_content(self):
        self._login()
        resp = self.client.post(f"/api/teacher/progress/content/{self.content_2.id}/start/")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "CONTENT_LOCKED")

    def test_content_unlocks_after_previous_module_completion(self):
        self._login()
        complete = self.client.post(f"/api/teacher/progress/content/{self.content_1.id}/complete/")
        self.assertEqual(complete.status_code, 200, complete.content)

        start_next = self.client.post(f"/api/teacher/progress/content/{self.content_2.id}/start/")
        self.assertEqual(start_next.status_code, 200, start_next.content)

    def test_teacher_calendar_and_gamification_summary(self):
        self._login()
        calendar = self.client.get("/api/teacher/calendar/?days=5")
        self.assertEqual(calendar.status_code, 200, calendar.content)
        payload = calendar.json()
        self.assertEqual(payload["window"]["days"], 5)
        self.assertEqual(len(payload["days"]), 5)
        event_types = {event["type"] for event in payload["events"]}
        self.assertIn("course_deadline", event_types)
        self.assertIn("assignment_due", event_types)

        game = self.client.get("/api/teacher/gamification/summary/")
        self.assertEqual(game.status_code, 200, game.content)
        game_payload = game.json()
        self.assertEqual(len(game_payload["badges"]), 5)
        self.assertEqual(game_payload["quest"]["key"], "streak_5_days")

    def test_can_claim_quest_after_five_day_streak(self):
        self._login()
        streak_course = Course.objects.create(
            tenant=self.tenant,
            title="Streak Course",
            slug="streak-course",
            description="y",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )
        streak_module = Module.objects.create(
            course=streak_course,
            title="Streak Module",
            description="",
            order=1,
            is_active=True,
        )

        for offset in range(5):
            content = Content.objects.create(
                module=streak_module,
                title=f"Streak Lesson {offset}",
                content_type="TEXT",
                order=offset + 1,
                text_content="<p>streak</p>",
                is_active=True,
            )
            progress = TeacherProgress.objects.create(
                teacher=self.teacher,
                course=streak_course,
                content=content,
                status="COMPLETED",
                progress_percentage=100,
                started_at=timezone.now() - timedelta(days=offset),
                completed_at=timezone.now() - timedelta(days=offset),
            )
            TeacherProgress.objects.filter(id=progress.id).update(
                last_accessed=timezone.now() - timedelta(days=offset)
            )

        summary = self.client.get("/api/teacher/gamification/summary/")
        self.assertEqual(summary.status_code, 200, summary.content)
        self.assertTrue(summary.json()["quest"]["claimable"])

        claim = self.client.post("/api/teacher/gamification/quests/streak_5_days/claim/")
        self.assertEqual(claim.status_code, 200, claim.content)
        self.assertTrue(claim.json()["quest"]["claimed_today"])

        claim_again = self.client.post("/api/teacher/gamification/quests/streak_5_days/claim/")
        self.assertEqual(claim_again.status_code, 400, claim_again.content)
