from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase

from apps.courses.models import Course, Module, Content
from apps.courses.video_models import VideoAsset, VideoTranscript
from apps.courses.tasks import validate_duration, generate_assignments
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.progress.models import Assignment, QuizQuestion


class VideoPipelineTaskTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Demo",
            slug="demo-task",
            subdomain="demo",
            email="demo@task.test",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@demo.task",
            password="pass123",
            first_name="Admin",
            last_name="Demo",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@demo.task",
            password="pass123",
            first_name="Teacher",
            last_name="Demo",
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
        self.module = Module.objects.create(course=self.course, title="Module", description="", order=1, is_active=True)
        self.content = Content.objects.create(
            module=self.module,
            title="Video",
            content_type="VIDEO",
            order=1,
            file_url="",
            file_size=10,
            duration=None,
            text_content="",
            is_mandatory=True,
            is_active=True,
        )

        # Create a dummy source file in storage
        key = f"tenant/{self.tenant.id}/videos/{self.content.id}/source.mp4"
        default_storage.save(key, ContentFile(b"fake-video-bytes"))
        self.asset = VideoAsset.objects.create(content=self.content, source_file=key, source_url="", status="UPLOADED")

    @patch("apps.courses.tasks._run_ffprobe")
    @patch("apps.courses.tasks._download_to_tempfile")
    def test_validate_duration_fails_over_1hr(self, mock_dl, mock_probe):
        # Avoid file I/O in unit test: pretend download returned a path
        mock_dl.return_value = "/tmp/fake.mp4"
        mock_probe.return_value = {
            "format": {"duration": "4000.0"},
            "streams": [{"codec_type": "video", "width": 1280, "height": 720, "codec_name": "h264"}],
        }

        validate_duration.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("too long", self.asset.error_message.lower())

    def test_generate_assignments_is_idempotent(self):
        VideoTranscript.objects.create(
            video_asset=self.asset,
            language="en",
            full_text="This lesson covers classroom management, routines, and feedback strategies.",
            segments=[],
            vtt_url="",
        )

        generate_assignments.run(str(self.asset.id))
        first_assignments = Assignment.objects.filter(course=self.course, content=self.content, generation_source="VIDEO_AUTO").count()
        first_questions = QuizQuestion.objects.filter(quiz__assignment__course=self.course, quiz__assignment__content=self.content).count()

        generate_assignments.run(str(self.asset.id))
        second_assignments = Assignment.objects.filter(course=self.course, content=self.content, generation_source="VIDEO_AUTO").count()
        second_questions = QuizQuestion.objects.filter(quiz__assignment__course=self.course, quiz__assignment__content=self.content).count()

        qs = Assignment.objects.filter(course=self.course, content=self.content, generation_source="VIDEO_AUTO")
        self.assertGreaterEqual(qs.count(), 2)  # reflection + quiz
        self.assertEqual(first_assignments, second_assignments)
        self.assertEqual(first_questions, second_questions)

