"""
Tests for the video processing pipeline Celery tasks.

Covers (4 of 6 untested tasks):
  - validate_duration      : ffprobe, duration limit, metadata persistence
  - generate_thumbnail     : ffmpeg, upload, thumbnail_url persistence
  - transcribe_video       : faster-whisper, VTT upload, VideoTranscript creation
  - generate_assignments   : reflection + quiz auto-creation, idempotency, non-fatal failure

All external I/O (subprocess, storage, faster-whisper, notifications) is mocked.
"""

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def video_asset(db, tenant, course, module, video_content):
    """A VideoAsset in UPLOADED status, linked to video_content."""
    from apps.courses.video_models import VideoAsset
    return VideoAsset.objects.create(
        content=video_content,
        source_file=f"tenant/{tenant.id}/videos/{video_content.id}/source.mp4",
        status="UPLOADED",
    )


@pytest.fixture
def video_asset_processing(video_asset):
    """Same as video_asset but in PROCESSING status."""
    video_asset.status = "PROCESSING"
    video_asset.save()
    return video_asset


@pytest.fixture
def video_asset_failed(video_asset):
    """A FAILED video asset (tasks should skip early)."""
    video_asset.status = "FAILED"
    video_asset.save()
    return video_asset


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _make_ffprobe_json(duration=600, width=1920, height=1080, codec="h264"):
    """Build a fake ffprobe JSON dict."""
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": codec,
                "width": width,
                "height": height,
                "duration": str(float(duration)),
            }
        ],
        "format": {
            "duration": str(float(duration)),
        },
    }


MOCK_STORAGE_PATH = "/tmp/fake_source.mp4"


# ─────────────────────────────────────────────────────────────
# validate_duration
# ─────────────────────────────────────────────────────────────

class TestValidateDuration:
    """Tests for the validate_duration Celery task."""

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks._run_ffprobe")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_happy_path_sets_metadata(
        self, mock_remove, mock_exists, mock_ffprobe, mock_download, video_asset
    ):
        """Valid video → status PROCESSING, metadata fields saved."""
        from apps.courses.tasks import validate_duration
        from apps.courses.video_models import VideoAsset

        mock_ffprobe.return_value = _make_ffprobe_json(duration=300, width=1280, height=720, codec="h264")

        result = validate_duration(str(video_asset.id))

        assert result == str(video_asset.id)
        video_asset.refresh_from_db()
        assert video_asset.status == "PROCESSING"
        assert video_asset.duration_seconds == 300
        assert video_asset.width == 1280
        assert video_asset.height == 720
        assert video_asset.codec == "h264"

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks._run_ffprobe")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_mirrors_duration_to_content(
        self, mock_remove, mock_exists, mock_ffprobe, mock_download, video_asset, video_content
    ):
        """validate_duration mirrors duration_seconds → Content.duration."""
        from apps.courses.tasks import validate_duration
        from apps.courses.models import Content

        mock_ffprobe.return_value = _make_ffprobe_json(duration=450)

        validate_duration(str(video_asset.id))

        content = Content.objects.get(pk=video_content.pk)
        assert content.duration == 450

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks._run_ffprobe")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_rejects_video_over_one_hour(
        self, mock_remove, mock_exists, mock_ffprobe, mock_download, video_asset
    ):
        """Videos > 3600s → asset.status = FAILED."""
        from apps.courses.tasks import validate_duration
        mock_ffprobe.return_value = _make_ffprobe_json(duration=3700)

        validate_duration(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "too long" in video_asset.error_message.lower()

    def test_skips_already_failed_asset(self, video_asset_failed):
        """FAILED asset → task returns early without touching the record."""
        from apps.courses.tasks import validate_duration

        original_error = video_asset_failed.error_message
        validate_duration(str(video_asset_failed.id))

        # Status should still be FAILED (not changed to PROCESSING)
        video_asset_failed.refresh_from_db()
        assert video_asset_failed.status == "FAILED"

    def test_skips_ready_asset(self, video_asset):
        """READY asset → task is a no-op (returns early)."""
        from apps.courses.tasks import validate_duration
        video_asset.status = "READY"
        video_asset.save()

        validate_duration(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "READY"

    def test_marks_failed_when_no_source_file(self, video_asset):
        """Missing source_file → FAILED with appropriate message."""
        from apps.courses.tasks import validate_duration
        video_asset.source_file = ""
        video_asset.save()

        validate_duration(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "missing source_file" in video_asset.error_message.lower()

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks._run_ffprobe", side_effect=FileNotFoundError("ffprobe not found"))
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_marks_failed_when_ffprobe_not_found(
        self, mock_remove, mock_exists, mock_ffprobe, mock_download, video_asset
    ):
        """FileNotFoundError (ffprobe absent) → FAILED status."""
        from apps.courses.tasks import validate_duration

        validate_duration(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "ffprobe" in video_asset.error_message.lower()

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks._run_ffprobe")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_marks_failed_when_duration_unreadable(
        self, mock_remove, mock_exists, mock_ffprobe, mock_download, video_asset
    ):
        """ffprobe returns no duration → FAILED."""
        from apps.courses.tasks import validate_duration

        # _extract_video_stream_meta returns empty dict → no duration_seconds key
        mock_ffprobe.return_value = {"streams": [], "format": {}}

        validate_duration(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"


# ─────────────────────────────────────────────────────────────
# generate_thumbnail
# ─────────────────────────────────────────────────────────────

class TestGenerateThumbnail:
    """Tests for the generate_thumbnail Celery task."""

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.subprocess.check_output")
    @patch("apps.courses.tasks.default_storage")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_happy_path_sets_thumbnail_url(
        self, mock_remove, mock_exists, mock_storage, mock_subprocess, mock_download, video_asset
    ):
        """Valid run → thumbnail_url saved on asset and persisted to DB."""
        from apps.courses.tasks import generate_thumbnail

        # subprocess.check_output creates the file; stub storage.save + url
        mock_storage.save.return_value = "media/thumbnails/thumb.jpg"
        mock_storage.url.return_value = "https://cdn.example.com/thumb.jpg"

        # Also patch tempfile.TemporaryDirectory to control tmpdir
        with patch("apps.courses.tasks.tempfile.TemporaryDirectory") as mock_tmpdir, \
             patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=False)))), \
             patch("apps.courses.tasks.os.path.join", side_effect=lambda *args: "/".join(args)):
            mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakethumb")
            mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

            result = generate_thumbnail(str(video_asset.id))

        assert result == str(video_asset.id)

        # Verify thumbnail_url was persisted to the database (regression guard:
        # confirms asset.save(update_fields=["thumbnail_url",...]) was actually called).
        video_asset.refresh_from_db()
        assert video_asset.thumbnail_url == "https://cdn.example.com/thumb.jpg", (
            f"Expected thumbnail_url to be set after generate_thumbnail, "
            f"got: {video_asset.thumbnail_url!r}"
        )

    def test_skips_failed_asset(self, video_asset_failed):
        """FAILED asset → returns early without calling ffmpeg."""
        from apps.courses.tasks import generate_thumbnail

        with patch("apps.courses.tasks._download_to_tempfile") as mock_dl:
            generate_thumbnail(str(video_asset_failed.id))
            mock_dl.assert_not_called()

    def test_marks_failed_when_no_source_file(self, video_asset):
        """Missing source_file → FAILED."""
        from apps.courses.tasks import generate_thumbnail
        video_asset.source_file = ""
        video_asset.save()

        generate_thumbnail(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "missing source_file" in video_asset.error_message.lower()

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.subprocess.check_output", side_effect=FileNotFoundError("ffmpeg"))
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_marks_failed_when_ffmpeg_not_found(
        self, mock_remove, mock_exists, mock_subprocess, mock_download, video_asset
    ):
        """FileNotFoundError (ffmpeg absent) → FAILED."""
        from apps.courses.tasks import generate_thumbnail

        with patch("apps.courses.tasks.tempfile.TemporaryDirectory") as mock_tmpdir:
            mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/faketmp")
            mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
            generate_thumbnail(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "ffmpeg" in video_asset.error_message.lower()


# ─────────────────────────────────────────────────────────────
# transcribe_video
# ─────────────────────────────────────────────────────────────

class TestTranscribeVideo:
    """Tests for the transcribe_video Celery task."""

    def test_skips_failed_asset(self, video_asset_failed):
        """FAILED asset → returns early (no transcription)."""
        from apps.courses.tasks import transcribe_video

        with patch("apps.courses.tasks._download_to_tempfile") as mock_dl:
            transcribe_video(str(video_asset_failed.id))
            mock_dl.assert_not_called()

    def test_skips_when_no_source_file(self, video_asset):
        """No source_file → returns early with a warning (non-fatal)."""
        from apps.courses.tasks import transcribe_video
        video_asset.source_file = ""
        video_asset.save()

        result = transcribe_video(str(video_asset.id))

        # Non-fatal: returns asset id, does not mark FAILED
        assert result == str(video_asset.id)
        video_asset.refresh_from_db()
        assert video_asset.status != "FAILED"

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_handles_missing_faster_whisper_gracefully(
        self, mock_remove, mock_exists, mock_download, video_asset
    ):
        """If faster-whisper is not installed → non-fatal, returns asset_id."""
        from apps.courses.tasks import transcribe_video

        # Patch the import inside the function to raise ImportError
        with patch.dict("sys.modules", {"faster_whisper": None}):
            result = transcribe_video(str(video_asset.id))

        assert result == str(video_asset.id)
        # Asset should NOT be marked FAILED (transcription is non-fatal)
        video_asset.refresh_from_db()
        assert video_asset.status != "FAILED"

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.default_storage")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_happy_path_creates_transcript(
        self, mock_remove, mock_exists, mock_storage, mock_download, video_asset
    ):
        """Full happy path: WhisperModel transcribes → VideoTranscript created in DB."""
        from apps.courses.tasks import transcribe_video
        from apps.courses.video_models import VideoTranscript

        mock_storage.save.return_value = "media/captions/captions.vtt"
        mock_storage.url.return_value = "https://cdn.example.com/captions.vtt"

        # Build a mock segment
        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 5.0
        mock_seg.text = " Hello world"

        mock_whisper_model = MagicMock()
        mock_info = MagicMock()
        mock_whisper_model.transcribe.return_value = ([mock_seg], mock_info)

        mock_whisper_class = MagicMock(return_value=mock_whisper_model)

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_whisper_class)}), \
             patch("apps.courses.tasks.tempfile.NamedTemporaryFile") as mock_tmpfile:
            # Simulate NamedTemporaryFile context manager
            mock_tmpfile.return_value.__enter__ = MagicMock(return_value=MagicMock(
                write=MagicMock(),
                name="/tmp/fake.vtt",
            ))
            mock_tmpfile.return_value.__exit__ = MagicMock(return_value=False)
            mock_tmpfile.return_value.name = "/tmp/fake.vtt"

            with patch("builtins.open", MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock()),
                __exit__=MagicMock(return_value=False),
            ))):
                result = transcribe_video(str(video_asset.id))

        assert result == str(video_asset.id)

        # Verify a VideoTranscript row was created in the database (regression guard:
        # confirms VideoTranscript.objects.get_or_create(...) was actually called and saved).
        assert VideoTranscript.objects.filter(video_asset=video_asset).exists(), (
            "Expected a VideoTranscript to be created after successful transcription"
        )
        transcript = VideoTranscript.objects.get(video_asset=video_asset)
        assert transcript.full_text == "Hello world", (
            f"Expected transcript text 'Hello world', got: {transcript.full_text!r}"
        )
        assert transcript.vtt_url == "https://cdn.example.com/captions.vtt", (
            f"Expected vtt_url to be set, got: {transcript.vtt_url!r}"
        )
        assert transcript.language == "en"

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_non_fatal_on_unexpected_exception(
        self, mock_remove, mock_exists, mock_download, video_asset
    ):
        """Unexpected exception during transcription → non-fatal (asset not FAILED)."""
        from apps.courses.tasks import transcribe_video

        mock_whisper_class = MagicMock(side_effect=RuntimeError("GPU OOM"))

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_whisper_class)}):
            result = transcribe_video(str(video_asset.id))

        # Returns asset_id, does not raise, does not mark FAILED
        assert result == str(video_asset.id)
        video_asset.refresh_from_db()
        assert video_asset.status != "FAILED"


# ─────────────────────────────────────────────────────────────
# generate_assignments
# ─────────────────────────────────────────────────────────────

class TestGenerateAssignments:
    """Tests for the generate_assignments Celery task."""

    @pytest.fixture
    def video_asset_with_transcript(self, db, video_asset, tenant):
        """VideoAsset with a VideoTranscript attached."""
        from apps.courses.video_models import VideoTranscript
        from django.utils import timezone
        VideoTranscript.objects.create(
            video_asset=video_asset,
            language="en",
            full_text="Classroom management is about creating a positive environment for learning.",
            segments=[{"start": 0, "end": 10, "text": "Classroom management..."}],
            vtt_url="",
            generated_at=timezone.now(),
        )
        return video_asset

    def _mock_quiz_questions(self):
        """Return 6 deterministic quiz question payloads."""
        return [
            {
                "question_type": "MCQ",
                "prompt": f"Question {i}?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": {"answer": "A"},
                "explanation": "Because A.",
                "points": 1,
            }
            for i in range(1, 7)
        ]

    @patch("apps.courses.tasks._generate_quiz_questions")
    @patch("apps.courses.tasks._notify_new_assignments")
    def test_creates_reflection_and_quiz_assignments(
        self, mock_notify, mock_gen_questions, video_asset_with_transcript, tenant
    ):
        """Happy path: two assignments + Quiz + 6 QuizQuestions created."""
        from apps.courses.tasks import generate_assignments
        from apps.progress.models import Assignment, Quiz, QuizQuestion

        mock_gen_questions.return_value = self._mock_quiz_questions()

        result = generate_assignments(str(video_asset_with_transcript.id))

        assert result == str(video_asset_with_transcript.id)

        # Should have 2 VIDEO_AUTO assignments
        assignments = Assignment.objects.filter(
            course=video_asset_with_transcript.content.module.course,
            generation_source="VIDEO_AUTO",
        )
        assert assignments.count() == 2

        titles = set(assignments.values_list("title", flat=True))
        assert any("Reflection" in t for t in titles)
        assert any("Quiz" in t for t in titles)

        # Quiz object should exist
        quiz_assignment = assignments.get(title__startswith="Quiz")
        quiz = Quiz.objects.get(assignment=quiz_assignment)
        assert quiz.is_auto_generated is True

        # 6 QuizQuestions
        assert quiz.questions.count() == 6

    @patch("apps.courses.tasks._generate_quiz_questions")
    @patch("apps.courses.tasks._notify_new_assignments")
    def test_idempotent_when_questions_already_exist(
        self, mock_notify, mock_gen_questions, video_asset_with_transcript, tenant
    ):
        """Second run with existing questions → no duplicate questions created."""
        from apps.courses.tasks import generate_assignments
        from apps.progress.models import QuizQuestion, Quiz, Assignment

        mock_gen_questions.return_value = self._mock_quiz_questions()

        # First run
        generate_assignments(str(video_asset_with_transcript.id))
        # Second run
        generate_assignments(str(video_asset_with_transcript.id))

        # Still only 6 questions (no duplicates)
        quiz_assignment = Assignment.objects.get(
            course=video_asset_with_transcript.content.module.course,
            generation_source="VIDEO_AUTO",
            title__startswith="Quiz",
        )
        quiz = Quiz.objects.get(assignment=quiz_assignment)
        assert quiz.questions.count() == 6
        # _generate_quiz_questions called only once (second run exits early)
        assert mock_gen_questions.call_count == 1

    def test_skips_failed_asset(self, video_asset_failed):
        """FAILED asset → returns early without creating assignments."""
        from apps.courses.tasks import generate_assignments
        from apps.progress.models import Assignment

        generate_assignments(str(video_asset_failed.id))

        assert not Assignment.objects.filter(
            generation_source="VIDEO_AUTO",
        ).exists()

    @patch("apps.courses.tasks._generate_quiz_questions", side_effect=RuntimeError("LLM timeout"))
    @patch("apps.courses.tasks._notify_new_assignments")
    def test_non_fatal_on_quiz_generation_failure(
        self, mock_notify, mock_gen_questions, video_asset_with_transcript
    ):
        """Quiz generation failure → non-fatal (no exception raised, asset not FAILED)."""
        from apps.courses.tasks import generate_assignments

        # Should not raise
        result = generate_assignments(str(video_asset_with_transcript.id))
        assert result == str(video_asset_with_transcript.id)

        video_asset_with_transcript.refresh_from_db()
        assert video_asset_with_transcript.status != "FAILED"

    @patch("apps.courses.tasks._generate_quiz_questions")
    @patch("apps.courses.tasks._notify_new_assignments")
    def test_notifies_assigned_teachers(
        self, mock_notify, mock_gen_questions, video_asset_with_transcript
    ):
        """New assignments trigger _notify_new_assignments()."""
        from apps.courses.tasks import generate_assignments

        mock_gen_questions.return_value = self._mock_quiz_questions()

        generate_assignments(str(video_asset_with_transcript.id))

        assert mock_notify.called

    @patch("apps.courses.tasks._generate_quiz_questions")
    @patch("apps.courses.tasks._notify_new_assignments")
    def test_works_without_transcript(
        self, mock_notify, mock_gen_questions, video_asset, tenant
    ):
        """No transcript → uses content.title as source text (still creates assignments)."""
        from apps.courses.tasks import generate_assignments
        from apps.progress.models import Assignment

        mock_gen_questions.return_value = self._mock_quiz_questions()

        result = generate_assignments(str(video_asset.id))
        assert result == str(video_asset.id)

        assignments = Assignment.objects.filter(
            course=video_asset.content.module.course,
            generation_source="VIDEO_AUTO",
        )
        assert assignments.count() == 2

    @patch("apps.courses.tasks._generate_quiz_questions")
    @patch("apps.courses.tasks._notify_new_assignments")
    def test_generation_metadata_contains_video_asset_id(
        self, mock_notify, mock_gen_questions, video_asset_with_transcript
    ):
        """generation_metadata on each assignment includes the video_asset_id."""
        from apps.courses.tasks import generate_assignments
        from apps.progress.models import Assignment

        mock_gen_questions.return_value = self._mock_quiz_questions()
        generate_assignments(str(video_asset_with_transcript.id))

        for a in Assignment.objects.filter(generation_source="VIDEO_AUTO"):
            assert str(video_asset_with_transcript.id) in str(a.generation_metadata)

    @patch("apps.courses.tasks._generate_quiz_questions")
    @patch("apps.courses.tasks._notify_new_assignments")
    def test_tenant_context_cleared_after_task(
        self, mock_notify, mock_gen_questions, video_asset_with_transcript
    ):
        """Tenant context var must be cleared even when task succeeds."""
        from apps.courses.tasks import generate_assignments
        from utils.tenant_middleware import get_current_tenant

        mock_gen_questions.return_value = self._mock_quiz_questions()
        generate_assignments(str(video_asset_with_transcript.id))

        assert get_current_tenant() is None
