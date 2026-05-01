import subprocess
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase

from apps.courses.models import Course, Module, Content
from apps.courses.video_models import VideoAsset, VideoTranscript
from apps.courses.tasks import (
    finalize_video_asset,
    generate_assignments,
    generate_thumbnail,
    transcode_to_hls,
    transcribe_video,
    validate_duration,
)
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


# ---------------------------------------------------------------------------
# finalize_video_asset — pure DB task, no external dependencies
# ---------------------------------------------------------------------------


class FinalizeVideoAssetTestCase(TestCase):
    """
    Tests for finalize_video_asset Celery task.

    finalize_video_asset has no external tool dependencies: it only checks
    whether hls_master_url is set and updates asset.status accordingly.
    These tests run without any patching.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Finalize School",
            slug="finalize-school",
            subdomain="finalize",
            email="admin@finalize.test",
            is_active=True,
        )
        from apps.users.models import User
        self.admin = User.objects.create_user(
            email="admin@finalize.test",
            password="pass123",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Finalize Course",
            slug="finalize-course",
            description="",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="M1", description="", order=1, is_active=True
        )
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

    def _make_asset(self, **kwargs):
        return VideoAsset.objects.create(
            content=self.content,
            source_file="tenant/1/videos/1/source.mp4",
            source_url="",
            **kwargs,
        )

    def test_finalize_skips_when_already_failed(self):
        """
        If asset.status == 'FAILED' before finalize runs, the task must
        return without changing anything (idempotency guard).
        """
        asset = self._make_asset(
            status="FAILED",
            error_message="Previous step failed",
            hls_master_url="",
        )
        finalize_video_asset.run(str(asset.id))
        asset.refresh_from_db()
        self.assertEqual(asset.status, "FAILED")
        self.assertEqual(asset.error_message, "Previous step failed")

    def test_finalize_marks_failed_when_hls_url_missing(self):
        """
        If hls_master_url is empty the video is not streamable.
        finalize_video_asset must mark the asset FAILED with an informative
        error message.
        """
        asset = self._make_asset(status="PROCESSING", hls_master_url="")
        finalize_video_asset.run(str(asset.id))
        asset.refresh_from_db()
        self.assertEqual(asset.status, "FAILED")
        self.assertIn("hls", asset.error_message.lower())

    def test_finalize_marks_ready_when_hls_url_present(self):
        """
        If hls_master_url is set the video is streamable.
        finalize_video_asset must mark the asset READY and clear any error.
        """
        asset = self._make_asset(
            status="PROCESSING",
            hls_master_url="https://cdn.example.com/tenant/1/videos/1/master.m3u8",
        )
        finalize_video_asset.run(str(asset.id))
        asset.refresh_from_db()
        self.assertEqual(asset.status, "READY")
        self.assertEqual(asset.error_message, "")

    def test_finalize_ready_even_when_thumbnail_missing(self):
        """
        Thumbnail is a nice-to-have. finalize_video_asset must still mark
        the asset READY if hls_master_url is set but thumbnail_url is empty.
        A warning is logged but the teacher can still watch the video.
        """
        asset = self._make_asset(
            status="PROCESSING",
            hls_master_url="https://cdn.example.com/tenant/1/videos/1/master.m3u8",
            thumbnail_url="",  # deliberately absent
        )
        finalize_video_asset.run(str(asset.id))
        asset.refresh_from_db()
        self.assertEqual(
            asset.status,
            "READY",
            "Missing thumbnail must not prevent asset from becoming READY",
        )


# ---------------------------------------------------------------------------
# transcode_to_hls — requires ffmpeg; mocked in all tests
# ---------------------------------------------------------------------------


class TranscodeToHlsTestCase(TestCase):
    """
    Tests for transcode_to_hls Celery task.

    ffmpeg and storage I/O are mocked. Tests focus on the task's branching
    logic and error handling, not on ffmpeg output quality.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Transcode School",
            slug="transcode-school",
            subdomain="transcode",
            email="admin@transcode.test",
            is_active=True,
        )
        from apps.users.models import User
        self.admin = User.objects.create_user(
            email="admin@transcode.test",
            password="pass123",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Transcode Course",
            slug="transcode-course",
            description="",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="M1", description="", order=1, is_active=True
        )
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
        key = f"tenant/{self.tenant.id}/videos/{self.content.id}/source.mp4"
        default_storage.save(key, ContentFile(b"fake"))
        self.asset = VideoAsset.objects.create(
            content=self.content,
            source_file=key,
            source_url="",
            status="PROCESSING",
        )

    def test_transcode_skips_when_status_is_failed(self):
        """
        If a previous pipeline step marked the asset FAILED, transcode_to_hls
        must exit immediately without calling ffmpeg.
        """
        self.asset.status = "FAILED"
        self.asset.error_message = "Upstream failure"
        self.asset.save(update_fields=["status", "error_message", "updated_at"])

        # No subprocess mock — if ffmpeg were called the test would fail
        # with FileNotFoundError (ffmpeg not installed in test env).
        transcode_to_hls.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertEqual(self.asset.error_message, "Upstream failure")

    def test_transcode_marks_failed_when_source_file_missing(self):
        """
        If source_file is empty the task cannot download anything.
        It must mark the asset FAILED with an informative message.
        """
        self.asset.source_file = ""
        self.asset.save(update_fields=["source_file", "updated_at"])

        transcode_to_hls.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("source_file", self.asset.error_message.lower())

    @patch("apps.courses.tasks._download_to_tempfile")
    @patch("apps.courses.tasks.subprocess.check_output")
    def test_transcode_marks_failed_when_ffmpeg_not_found(
        self, mock_check_output, mock_download
    ):
        """
        If ffmpeg is not installed on the worker, subprocess raises
        FileNotFoundError. The task must catch it and mark the asset FAILED.
        """
        mock_download.return_value = "/tmp/nonexistent_fake.mp4"
        mock_check_output.side_effect = FileNotFoundError("ffmpeg: not found")

        transcode_to_hls.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg", self.asset.error_message.lower())

    @patch("apps.courses.tasks._download_to_tempfile")
    @patch("apps.courses.tasks.subprocess.check_output")
    def test_transcode_marks_failed_on_ffmpeg_process_error(
        self, mock_check_output, mock_download
    ):
        """
        If ffmpeg exits non-zero, subprocess.CalledProcessError is raised.
        The task must catch it and mark the asset FAILED with the error output.
        """
        mock_download.return_value = "/tmp/nonexistent_fake.mp4"
        err = subprocess.CalledProcessError(1, "ffmpeg", output=b"error: invalid codec")
        mock_check_output.side_effect = err

        transcode_to_hls.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg", self.asset.error_message.lower())


# ---------------------------------------------------------------------------
# generate_thumbnail — requires ffmpeg; mocked in all tests
# ---------------------------------------------------------------------------


class GenerateThumbnailTestCase(TestCase):
    """
    Tests for generate_thumbnail Celery task.

    ffmpeg is mocked. Tests focus on skip/error guards and the happy path
    (thumbnail_url is set after a successful ffmpeg run).
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Thumbnail School",
            slug="thumbnail-school",
            subdomain="thumbnail",
            email="admin@thumbnail.test",
            is_active=True,
        )
        from apps.users.models import User
        self.admin = User.objects.create_user(
            email="admin@thumbnail.test",
            password="pass123",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Thumbnail Course",
            slug="thumbnail-course",
            description="",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="M1", description="", order=1, is_active=True
        )
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
        key = f"tenant/{self.tenant.id}/videos/{self.content.id}/source.mp4"
        default_storage.save(key, ContentFile(b"fake"))
        self.asset = VideoAsset.objects.create(
            content=self.content,
            source_file=key,
            source_url="",
            status="PROCESSING",
        )

    def test_thumbnail_skips_when_status_is_failed(self):
        """
        If a previous pipeline step marked the asset FAILED, generate_thumbnail
        must exit immediately without calling ffmpeg.
        """
        self.asset.status = "FAILED"
        self.asset.error_message = "Upstream failure"
        self.asset.save(update_fields=["status", "error_message", "updated_at"])

        generate_thumbnail.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertEqual(self.asset.error_message, "Upstream failure")
        self.assertEqual(self.asset.thumbnail_url, "")

    def test_thumbnail_marks_failed_when_source_file_missing(self):
        """
        If source_file is empty the task cannot extract a frame.
        It must mark the asset FAILED with an informative message mentioning source_file.
        """
        self.asset.source_file = ""
        self.asset.save(update_fields=["source_file", "updated_at"])

        generate_thumbnail.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("source_file", self.asset.error_message.lower())

    @patch("apps.courses.tasks._download_to_tempfile")
    @patch("apps.courses.tasks.subprocess.check_output")
    def test_thumbnail_marks_failed_when_ffmpeg_not_found(
        self, mock_check_output, mock_download
    ):
        """
        If ffmpeg is not installed, the task must catch FileNotFoundError
        and mark the asset FAILED.
        """
        mock_download.return_value = "/tmp/nonexistent_fake.mp4"
        mock_check_output.side_effect = FileNotFoundError("ffmpeg: not found")

        generate_thumbnail.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg", self.asset.error_message.lower())

    @patch("apps.courses.tasks._download_to_tempfile")
    @patch("apps.courses.tasks.subprocess.check_output")
    def test_thumbnail_marks_failed_on_ffmpeg_process_error(
        self, mock_check_output, mock_download
    ):
        """
        If ffmpeg exits non-zero, CalledProcessError is raised.
        The task must catch it and mark the asset FAILED.
        """
        mock_download.return_value = "/tmp/nonexistent_fake.mp4"
        err = subprocess.CalledProcessError(1, "ffmpeg", output=b"Invalid data")
        mock_check_output.side_effect = err

        generate_thumbnail.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg", self.asset.error_message.lower())


# ---------------------------------------------------------------------------
# transcribe_video — optional pipeline step; non-fatal failures
# ---------------------------------------------------------------------------


class TranscribeVideoTestCase(TestCase):
    """
    Tests for transcribe_video Celery task.

    transcribe_video is NON-FATAL: failures must never set asset.status='FAILED'.
    Tests verify the task handles missing source files and absent Whisper library
    gracefully (returns without error, no DB mutation other than transcript rows).
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Transcribe School",
            slug="transcribe-school",
            subdomain="transcribe",
            email="admin@transcribe.test",
            is_active=True,
        )
        from apps.users.models import User
        self.admin = User.objects.create_user(
            email="admin@transcribe.test",
            password="pass123",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Transcribe Course",
            slug="transcribe-course",
            description="",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="M1", description="", order=1, is_active=True
        )
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
        key = f"tenant/{self.tenant.id}/videos/{self.content.id}/source.mp4"
        default_storage.save(key, ContentFile(b"fake"))
        self.asset = VideoAsset.objects.create(
            content=self.content,
            source_file=key,
            source_url="",
            status="READY",
        )

    def test_transcribe_skips_when_status_is_failed(self):
        """
        If the asset is in FAILED state, transcribe_video must exit immediately.
        The FAILED status must NOT be altered.
        """
        self.asset.status = "FAILED"
        self.asset.error_message = "Upstream failure"
        self.asset.save(update_fields=["status", "error_message", "updated_at"])

        transcribe_video.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertFalse(
            VideoTranscript.objects.filter(video_asset=self.asset).exists(),
            "No transcript should be created for a FAILED asset",
        )

    def test_transcribe_skips_gracefully_when_source_file_missing(self):
        """
        If source_file is empty, transcribe_video must return without error
        (non-fatal skip). The asset status must remain unchanged.
        """
        self.asset.source_file = ""
        self.asset.save(update_fields=["source_file", "updated_at"])

        original_status = self.asset.status
        # Should not raise
        transcribe_video.run(str(self.asset.id))
        self.asset.refresh_from_db()
        self.assertEqual(
            self.asset.status,
            original_status,
            "Missing source_file must not change asset status (non-fatal skip)",
        )
        self.assertFalse(
            VideoTranscript.objects.filter(video_asset=self.asset).exists(),
        )

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_transcribe_skips_gracefully_when_whisper_not_installed(
        self, mock_download
    ):
        """
        If faster-whisper is not installed (ImportError), transcribe_video must
        return without error and without mutating asset.status.

        This is the expected state in CI and on workers without GPU/Whisper.
        """
        mock_download.return_value = "/tmp/nonexistent_fake.mp4"

        # Simulate faster-whisper not installed by patching the import inside the task.
        # The task does: `from faster_whisper import WhisperModel`
        # We patch builtins.__import__ to raise ImportError for faster_whisper.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("No module named 'faster_whisper'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            transcribe_video.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(
            self.asset.status,
            "READY",
            "Absent Whisper library must not change asset status (non-fatal skip)",
        )
        self.assertFalse(
            VideoTranscript.objects.filter(video_asset=self.asset).exists(),
            "No transcript should be created when Whisper is not installed",
        )

