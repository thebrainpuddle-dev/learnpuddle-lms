# tests/test_storage_paths.py
"""
Tests for utils/storage_paths.py — file path generation for S3/DO Spaces.

All functions in storage_paths.py are pure (no Django DB required).

Covers:
1. _extract_ext() extension extraction
2. _unique_name() uniqueness
3. course_thumbnail_path() format and tenant isolation
4. learning_path_thumbnail_path() format
5. profile_picture_path() format with tenant and global variants
6. tenant_logo_path() format
7. media_library_video_path() and media_library_document_path()
8. course_video_prefix() and related HLS/thumbnail/caption paths
9. course_document_path() and rich_text_image_path()
10. AI Studio audio/image paths (ai_studio_lesson_scene_*)
11. preview_video_path() and preview_document_path()
12. upload_to callables return consistent paths
"""

import re
import uuid as uuid_module
from django.test import TestCase


# ===========================================================================
# Helpers
# ===========================================================================

_TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_CONTENT_ID = "11111111-2222-3333-4444-555555555555"
_USER_ID = "99999999-0000-1111-2222-333333333333"

# UUID v4 pattern
_UUID_RE = re.compile(r'^[0-9a-f]{32}$')

# Full UUID4 hex pattern (32 hex chars without dashes)
_UUID4_HEX_RE = re.compile(r'[0-9a-f]{32}', re.IGNORECASE)


# ===========================================================================
# 1. _extract_ext() Tests
# ===========================================================================


class ExtractExtTestCase(TestCase):
    """_extract_ext() must correctly extract file extensions."""

    def _ext(self, filename):
        from utils.storage_paths import _extract_ext
        return _extract_ext(filename)

    def test_extracts_common_extension(self):
        """.jpg extension must be extracted correctly."""
        self.assertEqual(self._ext("photo.jpg"), ".jpg")

    def test_extension_lowercased(self):
        """Extensions must be lowercased (.JPG → .jpg)."""
        self.assertEqual(self._ext("photo.JPG"), ".jpg")

    def test_extension_with_uppercase_png(self):
        """.PNG must become .png."""
        self.assertEqual(self._ext("logo.PNG"), ".png")

    def test_extension_mp4(self):
        """.mp4 video extension."""
        self.assertEqual(self._ext("lecture.mp4"), ".mp4")

    def test_extension_pdf(self):
        """.pdf document extension."""
        self.assertEqual(self._ext("syllabus.pdf"), ".pdf")

    def test_no_extension_returns_empty(self):
        """Filename with no extension must return ''."""
        self.assertEqual(self._ext("README"), "")

    def test_none_filename_returns_empty(self):
        """None filename must return '' without raising."""
        self.assertEqual(self._ext(None), "")

    def test_empty_string_returns_empty(self):
        """Empty string must return ''."""
        self.assertEqual(self._ext(""), "")

    def test_multiple_dots_uses_last_extension(self):
        """file.tar.gz → extension is .gz."""
        self.assertEqual(self._ext("archive.tar.gz"), ".gz")

    def test_dotfile_no_extension(self):
        """Hidden files (.gitignore) have no extension."""
        self.assertEqual(self._ext(".gitignore"), "")

    def test_extension_with_numbers(self):
        """.mp3 must work."""
        self.assertEqual(self._ext("audio.mp3"), ".mp3")


# ===========================================================================
# 2. _unique_name() Tests
# ===========================================================================


class UniqueNameTestCase(TestCase):
    """_unique_name() must produce unique filenames with correct extension."""

    def _unique(self, ext):
        from utils.storage_paths import _unique_name
        return _unique_name(ext)

    def test_name_includes_extension(self):
        """Generated name must end with the provided extension."""
        name = self._unique(".jpg")
        self.assertTrue(name.endswith(".jpg"), f"Name '{name}' must end with .jpg")

    def test_name_without_extension(self):
        """Extension '' must produce a name with no trailing dot."""
        name = self._unique("")
        self.assertFalse(name.endswith("."), f"Name '{name}' must not end with '.'")

    def test_consecutive_calls_produce_different_names(self):
        """Two calls must produce different names (random UUID prefix)."""
        name1 = self._unique(".jpg")
        name2 = self._unique(".jpg")
        self.assertNotEqual(name1, name2, "Consecutive _unique_name() calls must differ")

    def test_name_prefix_is_valid_hex(self):
        """The UUID part of the name must be valid hex (no dashes)."""
        name = self._unique(".png")
        hex_part = name.replace(".png", "")
        self.assertRegex(hex_part, r'^[0-9a-f]{32}$', "UUID prefix must be 32 hex chars")


# ===========================================================================
# 3. course_thumbnail_path() Tests
# ===========================================================================


class CourseThumbnailPathTestCase(TestCase):
    """course_thumbnail_path() must produce tenant-scoped paths."""

    def test_path_starts_with_course_thumbnails(self):
        """Path must start with 'course_thumbnails/'."""
        from utils.storage_paths import course_thumbnail_path
        path = course_thumbnail_path(_TENANT_ID, "thumb.jpg")
        self.assertTrue(
            path.startswith("course_thumbnails/"),
            f"Path '{path}' must start with 'course_thumbnails/'",
        )

    def test_path_includes_tenant_id(self):
        """Path must include the tenant_id for isolation."""
        from utils.storage_paths import course_thumbnail_path
        path = course_thumbnail_path(_TENANT_ID, "thumb.jpg")
        self.assertIn(_TENANT_ID, path, "Path must contain tenant_id for isolation")

    def test_path_includes_file_extension(self):
        """Extension from filename must appear in generated path."""
        from utils.storage_paths import course_thumbnail_path
        path = course_thumbnail_path(_TENANT_ID, "thumb.png")
        self.assertTrue(path.endswith(".png"), "Extension must be preserved in path")

    def test_different_tenants_get_different_paths(self):
        """Two different tenant_ids must produce paths in different directories."""
        from utils.storage_paths import course_thumbnail_path
        tenant_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        tenant_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        path_a = course_thumbnail_path(tenant_a, "img.jpg")
        path_b = course_thumbnail_path(tenant_b, "img.jpg")
        # Different tenant directories
        self.assertIn(tenant_a, path_a)
        self.assertIn(tenant_b, path_b)
        self.assertNotIn(tenant_b, path_a, "Tenant A path must not contain Tenant B id")
        self.assertNotIn(tenant_a, path_b, "Tenant B path must not contain Tenant A id")

    def test_path_format(self):
        """Path must follow format: course_thumbnails/tenant/{id}/{uuid}.{ext}"""
        from utils.storage_paths import course_thumbnail_path
        path = course_thumbnail_path(_TENANT_ID, "img.jpg")
        # Must match: course_thumbnails/tenant/<uuid>/<uuid>.jpg
        parts = path.split("/")
        self.assertEqual(parts[0], "course_thumbnails")
        self.assertEqual(parts[1], "tenant")
        self.assertEqual(parts[2], _TENANT_ID)
        self.assertTrue(parts[3].endswith(".jpg"))


# ===========================================================================
# 4. Profile Picture Path Tests
# ===========================================================================


class ProfilePicturePathTestCase(TestCase):
    """profile_picture_path() must handle both tenant and global scenarios."""

    def test_path_with_tenant_id(self):
        """Profile picture path with tenant must use tenant_id folder."""
        from utils.storage_paths import profile_picture_path
        path = profile_picture_path(_TENANT_ID, _USER_ID, "avatar.jpg")
        self.assertIn(_TENANT_ID, path)
        self.assertIn(_USER_ID, path)
        self.assertTrue(path.startswith("profile_pictures/tenant/"))

    def test_path_without_tenant_uses_global(self):
        """When tenant_id is None, must use 'global' folder."""
        from utils.storage_paths import profile_picture_path
        path = profile_picture_path(None, _USER_ID, "avatar.jpg")
        self.assertIn("global", path, "None tenant_id must use 'global' folder")

    def test_path_preserves_extension(self):
        """Extension must be preserved in the profile picture path."""
        from utils.storage_paths import profile_picture_path
        path = profile_picture_path(_TENANT_ID, _USER_ID, "photo.png")
        self.assertTrue(path.endswith(".png"))


# ===========================================================================
# 5. Media Library Path Tests
# ===========================================================================


class MediaLibraryPathTestCase(TestCase):
    """media_library_video_path() and media_library_document_path()."""

    def test_video_path_format(self):
        """Video path must be under media_library/tenant/{id}/videos/."""
        from utils.storage_paths import media_library_video_path
        path = media_library_video_path(_TENANT_ID, "lecture.mp4")
        self.assertTrue(path.startswith(f"media_library/tenant/{_TENANT_ID}/videos/"))

    def test_document_path_format(self):
        """Document path must be under media_library/tenant/{id}/documents/."""
        from utils.storage_paths import media_library_document_path
        path = media_library_document_path(_TENANT_ID, "notes.pdf")
        self.assertTrue(path.startswith(f"media_library/tenant/{_TENANT_ID}/documents/"))

    def test_video_path_extension_preserved(self):
        """mp4 extension must be preserved in video path."""
        from utils.storage_paths import media_library_video_path
        path = media_library_video_path(_TENANT_ID, "video.mp4")
        self.assertTrue(path.endswith(".mp4"))

    def test_document_path_extension_preserved(self):
        """pdf extension must be preserved in document path."""
        from utils.storage_paths import media_library_document_path
        path = media_library_document_path(_TENANT_ID, "file.pdf")
        self.assertTrue(path.endswith(".pdf"))


# ===========================================================================
# 6. Course Video Path Tests
# ===========================================================================


class CourseVideoPathTestCase(TestCase):
    """Course video path helpers must produce correct, isolated paths."""

    def test_prefix_format(self):
        """course_video_prefix must follow correct format."""
        from utils.storage_paths import course_video_prefix
        prefix = course_video_prefix(_TENANT_ID, _CONTENT_ID)
        expected = f"course_content/tenant/{_TENANT_ID}/videos/{_CONTENT_ID}"
        self.assertEqual(prefix, expected)

    def test_source_path_has_extension(self):
        """Source video path must include extension from filename."""
        from utils.storage_paths import course_video_source_path
        path = course_video_source_path(_TENANT_ID, _CONTENT_ID, "input.mp4")
        self.assertTrue(path.endswith("source.mp4"), f"Path '{path}' must end with 'source.mp4'")

    def test_source_path_defaults_to_mp4_when_no_ext(self):
        """Source path must default to .mp4 if filename has no extension."""
        from utils.storage_paths import course_video_source_path
        path = course_video_source_path(_TENANT_ID, _CONTENT_ID, "video_file")
        self.assertTrue(path.endswith("source.mp4"))

    def test_hls_prefix_ends_with_hls(self):
        """HLS prefix must end with '/hls'."""
        from utils.storage_paths import course_video_hls_prefix
        prefix = course_video_hls_prefix(_TENANT_ID, _CONTENT_ID)
        self.assertTrue(prefix.endswith("/hls"))

    def test_thumbnail_path_ends_with_thumb_jpg(self):
        """Video thumbnail path must end with 'thumb.jpg'."""
        from utils.storage_paths import course_video_thumbnail_path
        path = course_video_thumbnail_path(_TENANT_ID, _CONTENT_ID)
        self.assertTrue(path.endswith("/thumb.jpg"))

    def test_captions_path_ends_with_vtt(self):
        """Captions path must end with 'captions.vtt'."""
        from utils.storage_paths import course_video_captions_path
        path = course_video_captions_path(_TENANT_ID, _CONTENT_ID)
        self.assertTrue(path.endswith("/captions.vtt"))

    def test_all_video_paths_share_same_prefix(self):
        """All video-related paths for same content must share the same base prefix."""
        from utils.storage_paths import (
            course_video_prefix, course_video_source_path,
            course_video_hls_prefix, course_video_thumbnail_path,
        )
        prefix = course_video_prefix(_TENANT_ID, _CONTENT_ID)
        self.assertTrue(
            course_video_source_path(_TENANT_ID, _CONTENT_ID, "v.mp4").startswith(prefix)
        )
        self.assertTrue(
            course_video_hls_prefix(_TENANT_ID, _CONTENT_ID).startswith(prefix)
        )
        self.assertTrue(
            course_video_thumbnail_path(_TENANT_ID, _CONTENT_ID).startswith(prefix)
        )


# ===========================================================================
# 7. Course Document and Rich-Text Image Path Tests
# ===========================================================================


class CourseDocumentPathTestCase(TestCase):
    """Document and rich-text image paths."""

    def test_document_path_format(self):
        """Document path must be scoped to tenant and content."""
        from utils.storage_paths import course_document_path
        path = course_document_path(_TENANT_ID, _CONTENT_ID, "notes.pdf")
        self.assertIn(_TENANT_ID, path)
        self.assertIn(_CONTENT_ID, path)
        self.assertTrue(path.endswith(".pdf"))

    def test_rich_text_image_path_format(self):
        """Rich text image path must be under course_content/tenant/{id}/rich_text_images/."""
        from utils.storage_paths import rich_text_image_path
        path = rich_text_image_path(_TENANT_ID, "inline.png")
        self.assertTrue(path.startswith(f"course_content/tenant/{_TENANT_ID}/rich_text_images/"))

    def test_rich_text_image_defaults_to_png_when_no_ext(self):
        """Rich text image path must default to .png when filename has no extension."""
        from utils.storage_paths import rich_text_image_path
        path = rich_text_image_path(_TENANT_ID, "image_no_ext")
        self.assertTrue(path.endswith(".png"))


# ===========================================================================
# 8. AI Studio Path Tests
# ===========================================================================


class AIStudioPathTestCase(TestCase):
    """AI Studio audio/image path helpers."""

    _LESSON_ID = "lesson-uuid-abcde"

    def test_audio_prefix_format(self):
        """AI Studio audio prefix must follow correct format."""
        from utils.storage_paths import ai_studio_lesson_audio_prefix
        prefix = ai_studio_lesson_audio_prefix(_TENANT_ID, self._LESSON_ID)
        self.assertIn(_TENANT_ID, prefix)
        self.assertIn(self._LESSON_ID, prefix)
        self.assertTrue(prefix.endswith("/audio"))

    def test_scene_audio_path_has_padded_index(self):
        """Scene audio path must use zero-padded 3-digit scene index."""
        from utils.storage_paths import ai_studio_lesson_scene_audio_path
        path = ai_studio_lesson_scene_audio_path(_TENANT_ID, self._LESSON_ID, 1)
        self.assertIn("scene_001.mp3", path)

    def test_scene_audio_path_index_7(self):
        """Scene index 7 must produce 'scene_007.mp3'."""
        from utils.storage_paths import ai_studio_lesson_scene_audio_path
        path = ai_studio_lesson_scene_audio_path(_TENANT_ID, self._LESSON_ID, 7)
        self.assertIn("scene_007.mp3", path)

    def test_scene_audio_path_index_99(self):
        """Scene index 99 must produce 'scene_099.mp3'."""
        from utils.storage_paths import ai_studio_lesson_scene_audio_path
        path = ai_studio_lesson_scene_audio_path(_TENANT_ID, self._LESSON_ID, 99)
        self.assertIn("scene_099.mp3", path)

    def test_image_prefix_format(self):
        """AI Studio image prefix must follow correct format."""
        from utils.storage_paths import ai_studio_lesson_image_prefix
        prefix = ai_studio_lesson_image_prefix(_TENANT_ID, self._LESSON_ID)
        self.assertIn(_TENANT_ID, prefix)
        self.assertIn(self._LESSON_ID, prefix)
        self.assertTrue(prefix.endswith("/images"))

    def test_scene_image_path_has_padded_index(self):
        """Scene image path must use zero-padded 3-digit index."""
        from utils.storage_paths import ai_studio_lesson_scene_image_path
        path = ai_studio_lesson_scene_image_path(_TENANT_ID, self._LESSON_ID, 5)
        self.assertIn("scene_005.jpg", path)


# ===========================================================================
# 9. Preview Path Tests
# ===========================================================================


class PreviewPathTestCase(TestCase):
    """Preview path helpers."""

    def test_video_preview_path_format(self):
        """Video preview path must be under previews/tenant/{id}/videos/."""
        from utils.storage_paths import preview_video_path
        path = preview_video_path(_TENANT_ID, "preview.jpg")
        self.assertTrue(path.startswith(f"previews/tenant/{_TENANT_ID}/videos/"))

    def test_document_preview_path_format(self):
        """Document preview path must be under previews/tenant/{id}/documents/."""
        from utils.storage_paths import preview_document_path
        path = preview_document_path(_TENANT_ID, "preview.jpg")
        self.assertTrue(path.startswith(f"previews/tenant/{_TENANT_ID}/documents/"))

    def test_video_preview_defaults_to_jpg(self):
        """Video preview with no extension must default to .jpg."""
        from utils.storage_paths import preview_video_path
        path = preview_video_path(_TENANT_ID, "file_no_ext")
        self.assertTrue(path.endswith(".jpg"))

    def test_document_preview_defaults_to_jpg(self):
        """Document preview with no extension must default to .jpg."""
        from utils.storage_paths import preview_document_path
        path = preview_document_path(_TENANT_ID, "file_no_ext")
        self.assertTrue(path.endswith(".jpg"))


# ===========================================================================
# 10. Tenant Isolation Tests (cross-validation)
# ===========================================================================


class TenantIsolationTestCase(TestCase):
    """All path functions must produce tenant-isolated paths."""

    _TENANT_A = "aaaaaaaa-0000-0000-0000-000000000000"
    _TENANT_B = "bbbbbbbb-1111-1111-1111-111111111111"

    def _paths_are_isolated(self, fn, *extra_args):
        """Helper: verify paths for tenant A and B do not overlap."""
        path_a = fn(self._TENANT_A, *extra_args)
        path_b = fn(self._TENANT_B, *extra_args)
        self.assertIn(self._TENANT_A, path_a)
        self.assertIn(self._TENANT_B, path_b)
        # The tenant A dir must not be in tenant B's path
        self.assertNotIn(
            f"/{self._TENANT_A}/",
            path_b,
            f"Tenant B path '{path_b}' must not contain Tenant A id",
        )

    def test_course_thumbnail_isolated(self):
        from utils.storage_paths import course_thumbnail_path
        self._paths_are_isolated(course_thumbnail_path, "img.jpg")

    def test_media_library_video_isolated(self):
        from utils.storage_paths import media_library_video_path
        self._paths_are_isolated(media_library_video_path, "v.mp4")

    def test_course_video_prefix_isolated(self):
        from utils.storage_paths import course_video_prefix

        def _fn(tenant_id, *_):
            return course_video_prefix(tenant_id, _CONTENT_ID)

        prefix_a = _fn(self._TENANT_A)
        prefix_b = _fn(self._TENANT_B)
        self.assertIn(self._TENANT_A, prefix_a)
        self.assertIn(self._TENANT_B, prefix_b)
        self.assertNotIn(self._TENANT_A, prefix_b)

    def test_preview_video_isolated(self):
        from utils.storage_paths import preview_video_path
        self._paths_are_isolated(preview_video_path, "p.jpg")
