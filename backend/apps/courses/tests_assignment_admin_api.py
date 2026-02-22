from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.courses.video_models import VideoAsset, VideoTranscript
from apps.progress.models import Assignment
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class AssignmentAdminApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.tenant = Tenant.objects.create(
            name="Assignment School",
            slug="assignment-school",
            subdomain="assignment",
            email="assignment@test.com",
            is_active=True,
        )
        self.other_tenant = Tenant.objects.create(
            name="Other School",
            slug="other-school",
            subdomain="other",
            email="other@test.com",
            is_active=True,
        )

        self.admin = User.objects.create_user(
            email="admin@assignment.test",
            password="pass123",
            first_name="Admin",
            last_name="Assignment",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.other_admin = User.objects.create_user(
            email="admin@other.test",
            password="pass123",
            first_name="Admin",
            last_name="Other",
            tenant=self.other_tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )

        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Course A",
            slug="course-a",
            description="Course description",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title="Module A",
            description="Module description",
            order=1,
            is_active=True,
        )
        self.text_content = Content.objects.create(
            module=self.module,
            title="Text Lesson",
            content_type="TEXT",
            order=1,
            text_content="<p>Safety training procedures and escalation matrix.</p>",
            is_mandatory=True,
            is_active=True,
        )
        self.video_content = Content.objects.create(
            module=self.module,
            title="Video Lesson",
            content_type="VIDEO",
            order=2,
            file_url="",
            text_content="",
            is_mandatory=True,
            is_active=True,
        )
        video_asset = VideoAsset.objects.create(
            content=self.video_content,
            source_file="",
            source_url="",
            status="READY",
        )
        VideoTranscript.objects.create(
            video_asset=video_asset,
            language="en",
            full_text="This module explains compliance reporting and incident documentation.",
            segments=[],
            vtt_url="",
        )

        self.other_course = Course.objects.create(
            tenant=self.other_tenant,
            title="Course B",
            slug="course-b",
            description="Other course",
            created_by=self.other_admin,
            is_published=True,
            is_active=True,
        )

    def _login(self, host: str, email: str, password: str):
        self.client.defaults["HTTP_HOST"] = host
        resp = self.client.post("/api/users/auth/login/", {"email": email, "password": password}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_assignment_crud_for_module_scope_quiz(self):
        self._login("assignment.lms.com", "admin@assignment.test", "pass123")

        create_resp = self.client.post(
            f"/api/courses/{self.course.id}/assignments/",
            data={
                "title": "Module Quiz",
                "description": "Quiz for module A",
                "instructions": "Answer all questions",
                "scope_type": "MODULE",
                "module_id": str(self.module.id),
                "assignment_type": "QUIZ",
                "questions": [
                    {
                        "question_type": "MCQ",
                        "selection_mode": "SINGLE",
                        "prompt": "Pick the right answer",
                        "options": ["A", "B", "C"],
                        "correct_answer": {"option_index": 1},
                        "points": 1,
                    },
                    {
                        "question_type": "MCQ",
                        "selection_mode": "MULTIPLE",
                        "prompt": "Pick all applicable items",
                        "options": ["A", "B", "C", "D"],
                        "correct_answer": {"option_indices": [0, 2]},
                        "points": 2,
                    },
                    {
                        "question_type": "TRUE_FALSE",
                        "prompt": "Incident logs are optional",
                        "correct_answer": {"value": False},
                        "points": 1,
                    },
                    {
                        "question_type": "SHORT_ANSWER",
                        "prompt": "Describe escalation flow",
                        "points": 2,
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.content)
        assignment_id = create_resp.json()["id"]

        list_resp = self.client.get(f"/api/courses/{self.course.id}/assignments/?scope=MODULE")
        self.assertEqual(list_resp.status_code, 200, list_resp.content)
        self.assertEqual(len(list_resp.json()), 1)
        self.assertEqual(list_resp.json()[0]["assignment_type"], "QUIZ")

        detail_resp = self.client.get(f"/api/courses/{self.course.id}/assignments/{assignment_id}/")
        self.assertEqual(detail_resp.status_code, 200, detail_resp.content)
        self.assertEqual(len(detail_resp.json()["questions"]), 4)

        patch_resp = self.client.patch(
            f"/api/courses/{self.course.id}/assignments/{assignment_id}/",
            data={"title": "Updated Quiz Title"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200, patch_resp.content)
        self.assertEqual(patch_resp.json()["title"], "Updated Quiz Title")

        delete_resp = self.client.delete(f"/api/courses/{self.course.id}/assignments/{assignment_id}/")
        self.assertEqual(delete_resp.status_code, 204, delete_resp.content)
        self.assertFalse(Assignment.objects.filter(id=assignment_id).exists())

    def test_assignment_validation_for_multiple_mcq(self):
        self._login("assignment.lms.com", "admin@assignment.test", "pass123")

        resp = self.client.post(
            f"/api/courses/{self.course.id}/assignments/",
            data={
                "title": "Invalid Quiz",
                "scope_type": "COURSE",
                "assignment_type": "QUIZ",
                "questions": [
                    {
                        "question_type": "MCQ",
                        "selection_mode": "MULTIPLE",
                        "prompt": "Broken question",
                        "options": ["A", "B"],
                        "correct_answer": {"option_indices": [0]},
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("at least 2 correct answers", resp.json()["error"])

    def test_ai_generate_creates_manual_quiz_with_origin_metadata(self):
        self._login("assignment.lms.com", "admin@assignment.test", "pass123")

        resp = self.client.post(
            f"/api/courses/{self.course.id}/assignments/ai-generate/",
            data={
                "scope_type": "MODULE",
                "module_id": str(self.module.id),
                "question_count": 5,
                "include_short_answer": True,
                "title_hint": "Compliance Basics",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["assignment_type"], "QUIZ")
        self.assertEqual(body["generation_source"], "MANUAL")
        self.assertEqual(body["generation_metadata"]["origin"], "AI_ON_DEMAND")
        self.assertGreaterEqual(len(body["questions"]), 2)

    def test_cross_tenant_assignment_api_isolation(self):
        self._login("assignment.lms.com", "admin@assignment.test", "pass123")
        resp = self.client.get(f"/api/courses/{self.other_course.id}/assignments/")
        self.assertEqual(resp.status_code, 404, resp.content)
