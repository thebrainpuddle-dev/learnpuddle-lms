"""
Extended video pipeline task tests.

Covers the 4 stages NOT tested in tests_video_pipeline.py:
  - transcode_to_hls
  - generate_thumbnail
  - transcribe_video
  - finalize_video_asset

Each test class targets a single task.  Celery tasks are invoked via
`.run()` (bypasses the broker) which is the canonical unit-test pattern.
All subprocess and storage I/O is mocked so tests run without Docker /
ffmpeg / Redis.
"""

import logging
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase

from apps.courses.models import Content, Course, Module
from apps.courses.tasks import (
    finalize_video_asset,
    generate_thumbnail,
    transcode_to_hls,
    transcribe_video,
)
from apps.courses.video_models import VideoAsset, VideoTranscript
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Shared test base
# ---------------------------------------------------------------------------

class VideoTaskTestBase(TestCase):
    """Creates a full course hierarchy + VideoAsset for each test method."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Pipeline School",
            slug="pipeline-school",
            subdomain="pipeline",
            email="pipeline@test.example",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@pipeline.test",
            password="pass123",
            first_name="Admin",
            last_name="Pipeline",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Video Course",
            slug="video-course",
            description="Test",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="",
            order=1,
            is_active=True,
        )
        self.content = Content.objects.create(
            module=self.module,
            title="Test Video",
            content_type="VIDEO",
            order=1,
            file_url="",
            file_size=10,
            duration=None,
            text_content="",
            is_mandatory=True,
            is_active=True,
        )
        # Seed a dummy source file so the storage key is valid
        self.storage_key = (
            f"tenant/{self.tenant.id}/videos/{self.content.id}/source.mp4"
        )
        default_storage.save(self.storage_key, ContentFile(b"fake-video-bytes"))
        self.asset = VideoAsset.objects.create(
            content=self.content,
            source_file=self.storage_key,
            source_url="",
            status="UPLOADED",
        )


# ---------------------------------------------------------------------------
# transcode_to_hls
# ---------------------------------------------------------------------------

class TranscodeToHlsTestCase(VideoTaskTestBase):
    """transcode_to_hls: calls ffmpeg to produce HLS segments + master.m3u8."""

    @patch("apps.courses.tasks.default_storage")
    @patch("apps.courses.tasks.subprocess.check_output")
    @patch("apps.courses.tasks._download_to_tempfile")
    def test_success_sets_hls_master_url_and_updates_content(
        self, mock_dl, mock_subproc, mock_storage
    ):
        """Happy path: ffmpeg succeeds → hls_master_url saved + Content.file_url updated."""
        mock_dl.return_value = "/tmp/fake.mp4"
        mock_subproc.return_value = b""
        # tmpdir will be empty (no real ffmpeg) → fallback key is used; url() returns mock URL
        mock_storage.url.return_value = "http://cdn.example.com/master.m3u8"

        transcode_to_hls.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.hls_master_url, "http://cdn.example.com/master.m3u8")

        self.content.refresh_from_db()
        self.assertEqual(self.content.file_url, "http://cdn.example.com/master.m3u8")

    def test_skips_when_asset_already_failed(self):
        """Asset pre-marked FAILED → ffmpeg must not be called."""
        self.asset.status = "FAILED"
        self.asset.error_message = "upstream error"
        self.asset.save()

        with patch("apps.courses.tasks.subprocess.check_output") as mock_subproc:
            transcode_to_hls.run(str(self.asset.id))
            mock_subproc.assert_not_called()

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertEqual(self.asset.error_message, "upstream error")

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_marks_failed_when_source_file_missing(self, mock_dl):
        """No source_file on asset → FAILED with descriptive message."""
        self.asset.source_file = ""
        self.asset.save()

        with patch("apps.courses.tasks.subprocess.check_output") as mock_subproc:
            transcode_to_hls.run(str(self.asset.id))
            mock_subproc.assert_not_called()

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("Missing source_file", self.asset.error_message)

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_marks_failed_when_ffmpeg_binary_not_found(self, mock_dl):
        """FileNotFoundError (ffmpeg not installed) → FAILED."""
        mock_dl.return_value = "/tmp/fake.mp4"

        with patch(
            "apps.courses.tasks.subprocess.check_output",
            side_effect=FileNotFoundError,
        ):
            transcode_to_hls.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg not found", self.asset.error_message)

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_marks_failed_when_ffmpeg_exits_nonzero(self, mock_dl):
        """CalledProcessError (bad video, codec error, etc.) → FAILED."""
        mock_dl.return_value = "/tmp/fake.mp4"
        err = subprocess.CalledProcessError(1, "ffmpeg", output=b"Invalid data found")

        with patch(
            "apps.courses.tasks.subprocess.check_output",
            side_effect=err,
        ):
            transcode_to_hls.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg failed", self.asset.error_message)


# ---------------------------------------------------------------------------
# generate_thumbnail
# ---------------------------------------------------------------------------

class GenerateThumbnailTestCase(VideoTaskTestBase):
    """generate_thumbnail: calls ffmpeg to extract a poster frame at 00:00:01."""

    @patch("apps.courses.tasks.default_storage")
    @patch("apps.courses.tasks.subprocess.check_output")
    @patch("apps.courses.tasks._download_to_tempfile")
    def test_success_sets_thumbnail_url(self, mock_dl, mock_subproc, mock_storage):
        """Happy path: ffmpeg writes thumb → thumbnail_url set on asset."""
        mock_dl.return_value = "/tmp/fake.mp4"
        mock_storage.url.return_value = "http://cdn.example.com/thumb.jpg"

        # Simulate ffmpeg by creating the thumbnail file at the expected output path
        def create_thumb_side_effect(cmd, stderr, timeout):
            thumb_path = cmd[-1]  # last CLI arg is the output file
            with open(thumb_path, "wb") as fh:
                fh.write(b"\xff\xd8\xff\xe0fake-jpeg-content")
            return b""

        mock_subproc.side_effect = create_thumb_side_effect

        generate_thumbnail.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.thumbnail_url, "http://cdn.example.com/thumb.jpg")
        mock_storage.save.assert_called_once()

    def test_skips_when_asset_already_failed(self):
        """Pre-failed asset → ffmpeg not called; status unchanged."""
        self.asset.status = "FAILED"
        self.asset.error_message = "upstream error"
        self.asset.save()

        with patch("apps.courses.tasks.subprocess.check_output") as mock_subproc:
            generate_thumbnail.run(str(self.asset.id))
            mock_subproc.assert_not_called()

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_marks_failed_when_source_file_missing(self, mock_dl):
        """No source_file → FAILED without calling ffmpeg."""
        self.asset.source_file = ""
        self.asset.save()

        with patch("apps.courses.tasks.subprocess.check_output") as mock_subproc:
            generate_thumbnail.run(str(self.asset.id))
            mock_subproc.assert_not_called()

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("Missing source_file", self.asset.error_message)

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_marks_failed_when_ffmpeg_binary_not_found(self, mock_dl):
        """FileNotFoundError → FAILED."""
        mock_dl.return_value = "/tmp/fake.mp4"

        with patch(
            "apps.courses.tasks.subprocess.check_output",
            side_effect=FileNotFoundError,
        ):
            generate_thumbnail.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg not found", self.asset.error_message)

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_marks_failed_when_ffmpeg_exits_nonzero(self, mock_dl):
        """CalledProcessError → FAILED with task-specific message."""
        mock_dl.return_value = "/tmp/fake.mp4"
        err = subprocess.CalledProcessError(1, "ffmpeg", output=b"No video stream")

        with patch(
            "apps.courses.tasks.subprocess.check_output",
            side_effect=err,
        ):
            generate_thumbnail.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("ffmpeg thumbnail failed", self.asset.error_message)


# ---------------------------------------------------------------------------
# transcribe_video
# ---------------------------------------------------------------------------

class TranscribeVideoTestCase(VideoTaskTestBase):
    """
    transcribe_video: uses faster-whisper to generate VTT captions.
    This task is NON-FATAL — exceptions must never mark the asset as FAILED.
    """

    def _make_segment(self, start: float, end: float, text: str):
        """Return a SimpleNamespace that mimics a faster-whisper Segment."""
        return SimpleNamespace(start=start, end=end, text=text)

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_skips_gracefully_when_faster_whisper_not_installed(self, mock_dl):
        """ImportError for faster_whisper → returns silently, asset stays non-FAILED."""
        mock_dl.return_value = "/tmp/fake.mp4"

        with patch.dict(sys.modules, {"faster_whisper": None}):
            transcribe_video.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertNotEqual(self.asset.status, "FAILED")
        self.assertFalse(
            VideoTranscript.objects.filter(video_asset=self.asset).exists()
        )

    @patch("apps.courses.tasks.default_storage")
    @patch("apps.courses.tasks._download_to_tempfile")
    def test_creates_video_transcript_on_success(self, mock_dl, mock_storage):
        """Happy path: WhisperModel returns segments → VideoTranscript created."""
        mock_dl.return_value = "/tmp/fake.mp4"
        mock_storage.url.return_value = "http://cdn.example.com/captions.vtt"

        segments = [
            self._make_segment(0.0, 3.5, "Welcome to the lesson."),
            self._make_segment(3.5, 7.0, "Today we cover feedback strategies."),
        ]
        mock_model = Mock()
        mock_model.transcribe.return_value = (iter(segments), Mock(language="en"))

        mock_whisper = Mock()
        mock_whisper.WhisperModel.return_value = mock_model

        with patch.dict(sys.modules, {"faster_whisper": mock_whisper}):
            transcribe_video.run(str(self.asset.id))

        transcript = VideoTranscript.objects.get(video_asset=self.asset)
        self.assertEqual(transcript.language, "en")
        self.assertIn("Welcome to the lesson.", transcript.full_text)
        self.assertIn("Today we cover feedback strategies.", transcript.full_text)
        self.assertEqual(len(transcript.segments), 2)
        self.assertEqual(transcript.vtt_url, "http://cdn.example.com/captions.vtt")
        mock_storage.save.assert_called_once()

    @patch("apps.courses.tasks.default_storage")
    @patch("apps.courses.tasks._download_to_tempfile")
    def test_updates_existing_transcript_on_rerun(self, mock_dl, mock_storage):
        """Running transcription a second time updates (not duplicates) the transcript."""
        mock_dl.return_value = "/tmp/fake.mp4"
        mock_storage.url.return_value = "http://cdn.example.com/captions-v2.vtt"

        # Pre-existing stale transcript
        VideoTranscript.objects.create(
            video_asset=self.asset,
            language="en",
            full_text="Old transcript text.",
            segments=[],
            vtt_url="http://cdn.example.com/old.vtt",
        )

        new_segments = [self._make_segment(0.0, 5.0, "Updated lesson content.")]
        mock_model = Mock()
        mock_model.transcribe.return_value = (iter(new_segments), Mock(language="en"))

        mock_whisper = Mock()
        mock_whisper.WhisperModel.return_value = mock_model

        with patch.dict(sys.modules, {"faster_whisper": mock_whisper}):
            transcribe_video.run(str(self.asset.id))

        # Exactly one transcript row, updated with new content
        self.assertEqual(
            VideoTranscript.objects.filter(video_asset=self.asset).count(), 1
        )
        transcript = VideoTranscript.objects.get(video_asset=self.asset)
        self.assertIn("Updated lesson content.", transcript.full_text)
        self.assertNotIn("Old transcript text.", transcript.full_text)
        self.assertEqual(transcript.vtt_url, "http://cdn.example.com/captions-v2.vtt")

    @patch("apps.courses.tasks._download_to_tempfile")
    def test_is_nonfatal_on_exception_during_transcription(self, mock_dl):
        """Exception during model.transcribe() must NOT mark the asset as FAILED."""
        mock_dl.return_value = "/tmp/fake.mp4"

        mock_model = Mock()
        mock_model.transcribe.side_effect = RuntimeError("CUDA out of memory")

        mock_whisper = Mock()
        mock_whisper.WhisperModel.return_value = mock_model

        with patch.dict(sys.modules, {"faster_whisper": mock_whisper}):
            # Must not raise
            transcribe_video.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertNotEqual(self.asset.status, "FAILED")

    def test_skips_when_asset_already_failed(self):
        """Pre-failed asset → download never called."""
        self.asset.status = "FAILED"
        self.asset.save()

        with patch("apps.courses.tasks._download_to_tempfile") as mock_dl:
            transcribe_video.run(str(self.asset.id))
            mock_dl.assert_not_called()

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")

    def test_skips_gracefully_when_source_file_missing(self):
        """No source_file → returns early without download or FAILED status."""
        self.asset.source_file = ""
        self.asset.save()

        with patch("apps.courses.tasks._download_to_tempfile") as mock_dl:
            transcribe_video.run(str(self.asset.id))
            mock_dl.assert_not_called()

        self.asset.refresh_from_db()
        # Non-fatal: no FAILED status
        self.assertNotEqual(self.asset.status, "FAILED")


# ---------------------------------------------------------------------------
# finalize_video_asset
# ---------------------------------------------------------------------------

class FinalizeVideoAssetTestCase(VideoTaskTestBase):
    """
    finalize_video_asset: the last pipeline stage.
    HLS is the only required artifact; thumbnail is nice-to-have (warning only).
    """

    def test_marks_ready_when_hls_url_present(self):
        """Asset with hls_master_url → status becomes READY."""
        self.asset.hls_master_url = "http://cdn.example.com/master.m3u8"
        self.asset.thumbnail_url = "http://cdn.example.com/thumb.jpg"
        self.asset.status = "PROCESSING"
        self.asset.save()

        finalize_video_asset.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "READY")
        self.assertEqual(self.asset.error_message, "")

    def test_marks_failed_when_hls_url_missing(self):
        """No hls_master_url → FAILED with descriptive error message."""
        self.asset.hls_master_url = ""
        self.asset.status = "PROCESSING"
        self.asset.save()

        finalize_video_asset.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertIn("missing HLS stream", self.asset.error_message)

    def test_skips_when_asset_already_failed(self):
        """Pre-failed asset → early return; status and error_message untouched."""
        self.asset.status = "FAILED"
        self.asset.error_message = "upstream failure"
        self.asset.hls_master_url = "http://cdn.example.com/master.m3u8"
        self.asset.save()

        finalize_video_asset.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "FAILED")
        self.assertEqual(self.asset.error_message, "upstream failure")

    def test_marks_ready_without_thumbnail_but_logs_warning(self):
        """READY requires only HLS; missing thumbnail emits a WARNING log."""
        self.asset.hls_master_url = "http://cdn.example.com/master.m3u8"
        self.asset.thumbnail_url = ""
        self.asset.status = "PROCESSING"
        self.asset.save()

        with self.assertLogs("apps.courses.tasks", level=logging.WARNING) as log_ctx:
            finalize_video_asset.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "READY")
        self.assertTrue(
            any("missing thumbnail" in msg for msg in log_ctx.output),
            f"Expected 'missing thumbnail' warning; got: {log_ctx.output}",
        )

    def test_clears_stale_error_message_on_successful_finalization(self):
        """Retry success (stale error_message from previous attempt) → error cleared."""
        self.asset.hls_master_url = "http://cdn.example.com/master.m3u8"
        self.asset.error_message = "Transient error from previous attempt"
        self.asset.status = "PROCESSING"
        self.asset.save()

        finalize_video_asset.run(str(self.asset.id))

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "READY")
        self.assertEqual(self.asset.error_message, "")
