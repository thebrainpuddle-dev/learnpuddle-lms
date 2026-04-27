"""
Tests for the remaining zero-coverage video pipeline Celery tasks:
  - transcode_to_hls       : ffmpeg HLS transcode, upload, URL persistence, failure modes
  - finalize_video_asset   : final status transition (READY) or failure gate

These complement the existing test_video_tasks.py file which already covers
validate_duration, generate_thumbnail, transcribe_video, and generate_assignments.

All external I/O (subprocess, storage, network) is mocked.
"""

from unittest.mock import MagicMock, patch

import pytest
import subprocess

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
def video_asset_failed(video_asset):
    """A FAILED video asset (tasks should skip early)."""
    video_asset.status = "FAILED"
    video_asset.save()
    return video_asset


MOCK_STORAGE_PATH = "/tmp/fake_source.mp4"


# ─────────────────────────────────────────────────────────────
# transcode_to_hls
# ─────────────────────────────────────────────────────────────

class TestTranscodeToHls:
    """Tests for the transcode_to_hls Celery task."""

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.subprocess.check_output", return_value=b"")
    @patch("apps.courses.tasks._upload_dir")
    @patch("apps.courses.tasks._safe_storage_url")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_happy_path_sets_hls_master_url(
        self,
        mock_remove,
        mock_exists,
        mock_url,
        mock_upload,
        mock_subprocess,
        mock_download,
        video_asset,
    ):
        """Happy path: ffmpeg succeeds → hls_master_url set on asset and mirrored to Content."""
        from apps.courses.tasks import transcode_to_hls
        from apps.courses.models import Content

        mock_upload.return_value = {"master.m3u8": "hls/prefix/master.m3u8"}
        mock_url.return_value = "https://cdn.example.com/master.m3u8"

        result = transcode_to_hls(str(video_asset.id))

        assert result == str(video_asset.id)
        video_asset.refresh_from_db()
        assert video_asset.hls_master_url == "https://cdn.example.com/master.m3u8"

        # Content.file_url should be updated to the HLS master URL
        content = Content.objects.get(pk=video_asset.content_id)
        assert content.file_url == "https://cdn.example.com/master.m3u8"

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.subprocess.check_output", return_value=b"")
    @patch("apps.courses.tasks._upload_dir")
    @patch("apps.courses.tasks._safe_storage_url")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_happy_path_invokes_ffmpeg_with_hls_args(
        self,
        mock_remove,
        mock_exists,
        mock_url,
        mock_upload,
        mock_subprocess,
        mock_download,
        video_asset,
    ):
        """ffmpeg command should include HLS-specific flags."""
        from apps.courses.tasks import transcode_to_hls

        mock_upload.return_value = {"master.m3u8": "hls/master.m3u8"}
        mock_url.return_value = "https://cdn.example.com/master.m3u8"

        transcode_to_hls(str(video_asset.id))

        assert mock_subprocess.called
        cmd = mock_subprocess.call_args[0][0]
        assert "ffmpeg" in cmd
        assert "-hls_time" in cmd
        assert "-hls_playlist_type" in cmd
        assert "vod" in cmd
        # Output path should end in .m3u8
        assert any(str(arg).endswith(".m3u8") for arg in cmd)

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.subprocess.check_output", return_value=b"")
    @patch("apps.courses.tasks._upload_dir")
    @patch("apps.courses.tasks._safe_storage_url")
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_falls_back_to_default_master_key_when_not_in_upload_map(
        self,
        mock_remove,
        mock_exists,
        mock_url,
        mock_upload,
        mock_subprocess,
        mock_download,
        video_asset,
    ):
        """If upload dict doesn't contain master.m3u8 key, falls back to prefix/master.m3u8."""
        from apps.courses.tasks import transcode_to_hls

        # Upload dict missing 'master.m3u8' entry
        mock_upload.return_value = {"seg_00001.ts": "prefix/seg_00001.ts"}
        mock_url.return_value = "https://cdn.example.com/fallback-master.m3u8"

        result = transcode_to_hls(str(video_asset.id))
        assert result == str(video_asset.id)

        # _safe_storage_url should have been called with a path ending in master.m3u8
        called_with = mock_url.call_args[0][0]
        assert called_with.endswith("/master.m3u8")

    def test_skips_already_failed_asset(self, video_asset_failed):
        """FAILED asset → task returns early without attempting any work."""
        from apps.courses.tasks import transcode_to_hls

        with patch("apps.courses.tasks._download_to_tempfile") as mock_dl, \
             patch("apps.courses.tasks.subprocess.check_output") as mock_sp:
            result = transcode_to_hls(str(video_asset_failed.id))

        assert result == str(video_asset_failed.id)
        mock_dl.assert_not_called()
        mock_sp.assert_not_called()

        video_asset_failed.refresh_from_db()
        assert video_asset_failed.status == "FAILED"

    def test_marks_failed_when_no_source_file(self, video_asset):
        """Missing source_file → FAILED status with appropriate message."""
        from apps.courses.tasks import transcode_to_hls

        video_asset.source_file = ""
        video_asset.save()

        result = transcode_to_hls(str(video_asset.id))

        assert result == str(video_asset.id)
        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "missing source_file" in video_asset.error_message.lower()

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch(
        "apps.courses.tasks.subprocess.check_output",
        side_effect=FileNotFoundError("ffmpeg not found"),
    )
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_marks_failed_when_ffmpeg_not_found(
        self,
        mock_remove,
        mock_exists,
        mock_subprocess,
        mock_download,
        video_asset,
    ):
        """FileNotFoundError from subprocess.check_output → FAILED."""
        from apps.courses.tasks import transcode_to_hls

        result = transcode_to_hls(str(video_asset.id))
        assert result == str(video_asset.id)

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "ffmpeg" in video_asset.error_message.lower()

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_marks_failed_on_ffmpeg_nonzero_exit(
        self,
        mock_remove,
        mock_exists,
        mock_download,
        video_asset,
    ):
        """ffmpeg returning nonzero exit → CalledProcessError → FAILED with ffmpeg error message."""
        from apps.courses.tasks import transcode_to_hls

        err = subprocess.CalledProcessError(
            returncode=1, cmd=["ffmpeg"], output=b"invalid input format"
        )
        with patch("apps.courses.tasks.subprocess.check_output", side_effect=err):
            result = transcode_to_hls(str(video_asset.id))

        assert result == str(video_asset.id)
        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "ffmpeg failed" in video_asset.error_message.lower()

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_retries_on_subprocess_timeout(
        self,
        mock_remove,
        mock_exists,
        mock_download,
        video_asset,
    ):
        """TimeoutExpired → self.retry() should be called (task retries, not fails)."""
        from apps.courses.tasks import transcode_to_hls

        err = subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=300)

        # Patch the retry method on the Celery task object to a no-op that raises
        # the same way Celery's retry does.
        with patch("apps.courses.tasks.subprocess.check_output", side_effect=err), \
             patch.object(transcode_to_hls, "retry", return_value=None) as mock_retry:
            transcode_to_hls(str(video_asset.id))

        assert mock_retry.called
        # Asset must NOT be marked FAILED on a timeout (it will be retried)
        video_asset.refresh_from_db()
        assert video_asset.status != "FAILED"

    @patch("apps.courses.tasks._download_to_tempfile", return_value=MOCK_STORAGE_PATH)
    @patch("apps.courses.tasks.subprocess.check_output", return_value=b"")
    @patch("apps.courses.tasks._upload_dir", side_effect=RuntimeError("storage down"))
    @patch("apps.courses.tasks.os.path.exists", return_value=True)
    @patch("apps.courses.tasks.os.remove")
    def test_unexpected_exception_sets_status_failed_and_reraises(
        self,
        mock_remove,
        mock_exists,
        mock_upload,
        mock_subprocess,
        mock_download,
        video_asset,
    ):
        """Unknown exception during upload → asset marked FAILED and exception re-raised."""
        from apps.courses.tasks import transcode_to_hls

        with pytest.raises(RuntimeError, match="storage down"):
            transcode_to_hls(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"


# ─────────────────────────────────────────────────────────────
# finalize_video_asset
# ─────────────────────────────────────────────────────────────

class TestFinalizeVideoAsset:
    """Tests for the finalize_video_asset Celery task."""

    def test_skips_already_failed_asset(self, video_asset_failed):
        """FAILED asset → task returns early, status stays FAILED."""
        from apps.courses.tasks import finalize_video_asset

        result = finalize_video_asset(str(video_asset_failed.id))
        assert result == str(video_asset_failed.id)

        video_asset_failed.refresh_from_db()
        assert video_asset_failed.status == "FAILED"

    def test_marks_failed_when_hls_missing(self, video_asset):
        """No hls_master_url → asset is marked FAILED (HLS is the critical artifact)."""
        from apps.courses.tasks import finalize_video_asset

        video_asset.hls_master_url = ""
        video_asset.save()

        result = finalize_video_asset(str(video_asset.id))
        assert result == str(video_asset.id)

        video_asset.refresh_from_db()
        assert video_asset.status == "FAILED"
        assert "hls" in video_asset.error_message.lower()

    def test_sets_ready_when_hls_present(self, video_asset):
        """HLS URL present → status → READY and error_message cleared."""
        from apps.courses.tasks import finalize_video_asset

        video_asset.hls_master_url = "https://cdn.example.com/master.m3u8"
        video_asset.thumbnail_url = "https://cdn.example.com/thumb.jpg"
        video_asset.error_message = "a previous transient error"
        video_asset.save()

        result = finalize_video_asset(str(video_asset.id))
        assert result == str(video_asset.id)

        video_asset.refresh_from_db()
        assert video_asset.status == "READY"
        assert video_asset.error_message == ""

    def test_ready_even_without_thumbnail(self, video_asset):
        """Missing thumbnail is NOT fatal — asset becomes READY with only HLS."""
        from apps.courses.tasks import finalize_video_asset

        video_asset.hls_master_url = "https://cdn.example.com/master.m3u8"
        video_asset.thumbnail_url = ""
        video_asset.save()

        finalize_video_asset(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status == "READY"

    def test_logs_warning_when_ready_without_thumbnail(self, video_asset, caplog):
        """When asset goes READY but has no thumbnail, a warning is logged."""
        import logging
        from apps.courses.tasks import finalize_video_asset

        video_asset.hls_master_url = "https://cdn.example.com/master.m3u8"
        video_asset.thumbnail_url = ""
        video_asset.save()

        with caplog.at_level(logging.WARNING, logger="apps.courses.tasks"):
            finalize_video_asset(str(video_asset.id))

        # The task logs: "finalize_video_asset: asset %s is READY but missing thumbnail"
        assert any(
            "missing thumbnail" in rec.getMessage().lower() for rec in caplog.records
        )

    def test_does_not_change_ready_asset_to_failed_when_thumbnail_missing(self, video_asset):
        """HLS present + thumbnail missing should NOT result in FAILED."""
        from apps.courses.tasks import finalize_video_asset

        video_asset.hls_master_url = "https://cdn.example.com/master.m3u8"
        video_asset.thumbnail_url = ""
        video_asset.save()

        finalize_video_asset(str(video_asset.id))

        video_asset.refresh_from_db()
        assert video_asset.status != "FAILED"

    def test_raises_when_asset_does_not_exist(self, db):
        """Unknown asset id → VideoAsset.DoesNotExist is raised."""
        from apps.courses.tasks import finalize_video_asset
        from apps.courses.video_models import VideoAsset

        with pytest.raises(VideoAsset.DoesNotExist):
            finalize_video_asset("00000000-0000-0000-0000-000000000000")
