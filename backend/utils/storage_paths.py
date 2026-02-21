# utils/storage_paths.py
"""
Centralized storage path definitions for DO Spaces / S3.

All upload paths are defined here to ensure consistency.
Pattern: {category}/tenant/{tenant_id}/{subcategory}/{unique_filename}

DO Spaces Structure:
learnpuddle-media/
├── course_thumbnails/tenant/{tenant_id}/{uuid}.{ext}
├── learning_path_thumbnails/tenant/{tenant_id}/{uuid}.{ext}
├── profile_pictures/tenant/{tenant_id}/{user_id}.{ext}
├── tenant_logos/tenant/{tenant_id}/{uuid}.{ext}
├── media_library/tenant/{tenant_id}/
│   ├── videos/{uuid}.{ext}
│   └── documents/{uuid}.{ext}
├── course_content/tenant/{tenant_id}/
│   ├── videos/{content_id}/
│   │   ├── source.{ext}
│   │   ├── hls/master.m3u8 (+ segments)
│   │   ├── thumb.jpg
│   │   └── captions.vtt
│   └── documents/{content_id}/{uuid}.{ext}
└── previews/tenant/{tenant_id}/
    ├── videos/{uuid}.jpg
    └── documents/{uuid}.jpg
"""

import uuid
from datetime import datetime


def _unique_name(ext: str) -> str:
    """Generate unique filename with extension."""
    return f"{uuid.uuid4().hex}{ext}"


def _extract_ext(filename: str) -> str:
    """Extract lowercase extension from filename."""
    if '.' in (filename or ''):
        return '.' + filename.rsplit('.', 1)[-1].lower()
    return ''


# -----------------------------------------------------------------------------
# Course Thumbnails
# -----------------------------------------------------------------------------
def course_thumbnail_path(tenant_id: str, filename: str) -> str:
    """Path for course thumbnail images."""
    ext = _extract_ext(filename)
    return f"course_thumbnails/tenant/{tenant_id}/{_unique_name(ext)}"


def course_thumbnail_upload_to(instance, filename: str) -> str:
    """Django upload_to callable for Course.thumbnail field."""
    return course_thumbnail_path(str(instance.tenant_id), filename)


# -----------------------------------------------------------------------------
# Learning Path Thumbnails
# -----------------------------------------------------------------------------
def learning_path_thumbnail_path(tenant_id: str, filename: str) -> str:
    """Path for learning path thumbnail images."""
    ext = _extract_ext(filename)
    return f"learning_path_thumbnails/tenant/{tenant_id}/{_unique_name(ext)}"


def learning_path_thumbnail_upload_to(instance, filename: str) -> str:
    """Django upload_to callable for LearningPath.thumbnail field."""
    return learning_path_thumbnail_path(str(instance.tenant_id), filename)


# -----------------------------------------------------------------------------
# Profile Pictures
# -----------------------------------------------------------------------------
def profile_picture_path(tenant_id: str | None, user_id: str, filename: str) -> str:
    """Path for user profile pictures."""
    ext = _extract_ext(filename)
    tenant_folder = str(tenant_id) if tenant_id else 'global'
    return f"profile_pictures/tenant/{tenant_folder}/{user_id}{ext}"


def profile_picture_upload_to(instance, filename: str) -> str:
    """Django upload_to callable for User.profile_picture field."""
    return profile_picture_path(instance.tenant_id, str(instance.id), filename)


# -----------------------------------------------------------------------------
# Tenant Logos
# -----------------------------------------------------------------------------
def tenant_logo_path(tenant_id: str, filename: str) -> str:
    """Path for tenant logos."""
    ext = _extract_ext(filename)
    return f"tenant_logos/tenant/{tenant_id}/{_unique_name(ext)}"


def tenant_logo_upload_to(instance, filename: str) -> str:
    """Django upload_to callable for Tenant.logo field."""
    return tenant_logo_path(str(instance.id), filename)


# -----------------------------------------------------------------------------
# Media Library (uploaded via admin media section)
# -----------------------------------------------------------------------------
def media_library_video_path(tenant_id: str, filename: str) -> str:
    """Path for videos uploaded to media library."""
    ext = _extract_ext(filename)
    return f"media_library/tenant/{tenant_id}/videos/{_unique_name(ext)}"


def media_library_document_path(tenant_id: str, filename: str) -> str:
    """Path for documents uploaded to media library."""
    ext = _extract_ext(filename)
    return f"media_library/tenant/{tenant_id}/documents/{_unique_name(ext)}"


def media_asset_upload_to(instance, filename: str) -> str:
    """Django upload_to callable for MediaAsset.file field."""
    tenant_id = str(instance.tenant_id)
    media_type = getattr(instance, 'media_type', 'DOCUMENT')
    
    if media_type == 'VIDEO':
        return media_library_video_path(tenant_id, filename)
    else:
        return media_library_document_path(tenant_id, filename)


# -----------------------------------------------------------------------------
# Course Content - Videos (processed by video pipeline)
# -----------------------------------------------------------------------------
def course_video_prefix(tenant_id: str, content_id: str) -> str:
    """Base prefix for all course video assets."""
    return f"course_content/tenant/{tenant_id}/videos/{content_id}"


def course_video_source_path(tenant_id: str, content_id: str, filename: str) -> str:
    """Path for uploaded source video file."""
    ext = _extract_ext(filename) or '.mp4'
    return f"{course_video_prefix(tenant_id, content_id)}/source{ext}"


def course_video_hls_prefix(tenant_id: str, content_id: str) -> str:
    """Prefix for HLS output directory."""
    return f"{course_video_prefix(tenant_id, content_id)}/hls"


def course_video_thumbnail_path(tenant_id: str, content_id: str) -> str:
    """Path for video thumbnail generated by ffmpeg."""
    return f"{course_video_prefix(tenant_id, content_id)}/thumb.jpg"


def course_video_captions_path(tenant_id: str, content_id: str) -> str:
    """Path for VTT captions file."""
    return f"{course_video_prefix(tenant_id, content_id)}/captions.vtt"


# -----------------------------------------------------------------------------
# Course Content - Documents (uploaded by admin)
# -----------------------------------------------------------------------------
def course_document_path(tenant_id: str, content_id: str, filename: str) -> str:
    """Path for documents attached to course content."""
    ext = _extract_ext(filename)
    return f"course_content/tenant/{tenant_id}/documents/{content_id}/{_unique_name(ext)}"


def rich_text_image_path(tenant_id: str, filename: str) -> str:
    """Path for inline rich-text images inside module/text content."""
    ext = _extract_ext(filename) or '.png'
    return f"course_content/tenant/{tenant_id}/rich_text_images/{_unique_name(ext)}"


# -----------------------------------------------------------------------------
# Previews (thumbnails/previews for media items)
# -----------------------------------------------------------------------------
def preview_video_path(tenant_id: str, filename: str) -> str:
    """Path for video preview thumbnails."""
    ext = _extract_ext(filename) or '.jpg'
    return f"previews/tenant/{tenant_id}/videos/{_unique_name(ext)}"


def preview_document_path(tenant_id: str, filename: str) -> str:
    """Path for document preview thumbnails."""
    ext = _extract_ext(filename) or '.jpg'
    return f"previews/tenant/{tenant_id}/documents/{_unique_name(ext)}"
