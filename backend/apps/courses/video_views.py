import re
import uuid
import logging
import requests

from celery import chain, group
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from utils.decorators import admin_only, tenant_required, check_feature, teacher_or_admin
from utils.storage_paths import course_video_source_path
from utils.s3_utils import sign_url

logger = logging.getLogger(__name__)


from apps.progress.models import Assignment
from apps.tenants.services import get_tenant_usage

from .models import Course, Module, Content
from .serializers import ContentSerializer
from .video_models import VideoAsset, VideoTranscript
from .tasks import (
    validate_duration,
    transcode_to_hls,
    generate_thumbnail,
    transcribe_video,
    generate_assignments,
    finalize_video_asset,
)


class VideoUploadThrottle(ScopedRateThrottle):
    scope = 'video_upload'


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv"}
ALLOWED_VIDEO_MIMES = {
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/webm",
    "video/x-matroska", "video/x-ms-wmv", "video/mpeg",
}


def _ext_from_name(name: str) -> str:
    if "." in (name or ""):
        return "." + name.rsplit(".", 1)[-1].lower()
    return ""


def _maybe_absolute(request, url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return request.build_absolute_uri(url)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([VideoUploadThrottle])
@admin_only
@tenant_required
@check_feature("feature_video_upload")
def upload_video_content(request, course_id, module_id):
    """
    Upload a video file, create Content(VIDEO) + VideoAsset, and enqueue processing.
    Validates: file type, file size, storage quota.
    """
    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)

    f = request.FILES.get("file") or request.FILES.get("video")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

    # ── Validate file type ──────────────────────────────────────────────
    ext = _ext_from_name(getattr(f, "name", ""))
    mime = getattr(f, "content_type", "")
    if not ext and not mime:
        return Response(
            {"error": "File must have a recognizable extension or MIME type."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if ext and ext not in ALLOWED_VIDEO_EXTENSIONS:
        return Response(
            {"error": f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if mime and mime not in ALLOWED_VIDEO_MIMES:
        return Response(
            {"error": f"Unsupported MIME type '{mime}'. Upload a video file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Validate file size ──────────────────────────────────────────────
    file_size = getattr(f, "size", 0) or 0
    max_bytes = getattr(settings, "MAX_VIDEO_UPLOAD_SIZE_MB", 500) * 1024 * 1024
    if file_size > max_bytes:
        return Response(
            {"error": f"File too large ({file_size // (1024*1024)}MB). Maximum is {max_bytes // (1024*1024)}MB."},
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    # ── Validate storage quota ──────────────────────────────────────────
    tenant = request.tenant
    usage = get_tenant_usage(tenant)
    used_mb = usage["storage_mb"]["used"]
    limit_mb = usage["storage_mb"]["limit"]
    upload_mb = file_size / (1024 * 1024)
    if used_mb + upload_mb > limit_mb:
        return Response(
            {"error": f"Storage quota exceeded. Used {used_mb:.1f}MB of {limit_mb}MB. Upload is {upload_mb:.1f}MB.", "upgrade_required": True},
            status=status.HTTP_403_FORBIDDEN,
        )

    title = request.data.get("title") or getattr(f, "name", "") or "Video"
    order = int(request.data.get("order") or (module.contents.count() + 1))
    is_mandatory = str(request.data.get("is_mandatory", "true")).lower() == "true"
    language = (request.data.get("language") or "en").strip() or "en"

    # Create content with a known UUID so we can use it in storage keys.
    content_id = uuid.uuid4()
    content = Content.objects.create(
        id=content_id,
        module=module,
        title=title,
        content_type="VIDEO",
        order=order,
        file_url="",
        file_size=file_size or None,
        duration=None,
        text_content="",
        is_mandatory=is_mandatory,
        is_active=True,
    )

    tenant_id = str(tenant.id)
    filename = f"source{ext or '.mp4'}"
    source_key = course_video_source_path(tenant_id, str(content.id), filename)
    saved_key = default_storage.save(source_key, f)

    asset = VideoAsset.objects.create(
        content=content,
        source_file=saved_key,
        source_url=_maybe_absolute(request, default_storage.url(saved_key)),
        status="UPLOADED",
    )

    # Enqueue processing pipeline.
    # Critical chain must complete for READY status: validate → transcode → thumbnail → finalize.
    # Non-fatal tasks (transcribe, assignments) run as fire-and-forget after finalize succeeds.
    asset_id = str(asset.id)
    critical = chain(
        validate_duration.s(asset_id),
        transcode_to_hls.s(),
        generate_thumbnail.s(),
        finalize_video_asset.s(),
    )
    critical.apply_async(
        link=group(
            transcribe_video.si(asset_id, language),
            generate_assignments.si(asset_id),
        )
    )

    return Response(
        {
            "content": ContentSerializer(content).data,
            "video_asset": {
                "id": str(asset.id),
                "status": asset.status,
                "source_url": asset.source_url,
                "hls_master_url": "",
                "thumbnail_url": "",
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def video_status(request, course_id, module_id, content_id):
    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    content = get_object_or_404(Content, id=content_id, module=module, content_type="VIDEO")
    asset = getattr(content, "video_asset", None)

    transcript = None
    if asset:
        transcript = getattr(asset, "transcript", None)

    assignments = list(
        Assignment.objects.filter(course=course, module=module, content=content, generation_source="VIDEO_AUTO")
        .order_by("created_at")
        .values("id", "title")
    )

    # Build proxy URL for HLS playback (signs segment URLs on the fly)
    # URL ends with .m3u8 so HLS.js recognizes it as an HLS source
    hls_proxy_url = ""
    if asset and asset.hls_master_url:
        hls_proxy_url = request.build_absolute_uri(f"/api/courses/hls/{content_id}/master.m3u8")
    
    return Response(
        {
            "content": ContentSerializer(content).data,
            "video_asset": (
                {
                    "id": str(asset.id),
                    "status": asset.status,
                    "error_message": asset.error_message,
                    "duration_seconds": asset.duration_seconds,
                    "hls_master_url": hls_proxy_url,
                    "thumbnail_url": sign_url(asset.thumbnail_url) if asset.thumbnail_url else "",
                    "source_url": sign_url(asset.source_url) if asset.source_url else "",
                }
                if asset
                else None
            ),
            "transcript": (
                {
                    "language": transcript.language,
                    "full_text_preview": (transcript.full_text[:240] + "...") if transcript.full_text else "",
                    "vtt_url": sign_url(transcript.vtt_url) if transcript.vtt_url else "",
                    "generated_at": transcript.generated_at,
                }
                if transcript
                else None
            ),
            "assignments": assignments,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def regenerate_transcript(request, course_id, module_id, content_id):
    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    content = get_object_or_404(Content, id=content_id, module=module, content_type="VIDEO")
    asset = getattr(content, "video_asset", None)
    if not asset:
        return Response({"error": "VideoAsset not found"}, status=status.HTTP_404_NOT_FOUND)

    language = (request.data.get("language") or "en").strip() or "en"
    # Fixed: use .delay() directly, not chain() with trailing comma
    transcribe_video.delay(str(asset.id), language=language)
    return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def regenerate_assignments(request, course_id, module_id, content_id):
    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    content = get_object_or_404(Content, id=content_id, module=module, content_type="VIDEO")
    asset = getattr(content, "video_asset", None)
    if not asset:
        return Response({"error": "VideoAsset not found"}, status=status.HTTP_404_NOT_FOUND)

    # Fixed: use .delay() directly, not chain() with trailing comma
    generate_assignments.delay(str(asset.id))
    return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def hls_playlist_view(request, content_id):
    """
    Serve the HLS master.m3u8 playlist with signed segment URLs.
    
    This endpoint:
    1. Fetches the original master.m3u8 from S3
    2. Parses and replaces segment references (*.ts) with signed S3 URLs
    3. Returns the modified playlist
    
    This solves 403 errors when HLS.js tries to fetch segments from private S3 buckets.
    """
    content = get_object_or_404(Content, id=content_id, content_type="VIDEO")
    
    # Verify the content belongs to the current tenant
    if content.module.course.tenant_id != request.tenant.id:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)
    
    asset = getattr(content, "video_asset", None)
    if not asset or not asset.hls_master_url:
        return Response({"error": "HLS playlist not available"}, status=status.HTTP_404_NOT_FOUND)
    
    # Get the original m3u8 URL (signed for fetching)
    original_m3u8_url = sign_url(asset.hls_master_url, expires_in=300)
    
    try:
        # Fetch the original m3u8 content
        resp = requests.get(original_m3u8_url, timeout=10)
        resp.raise_for_status()
        m3u8_content = resp.text
    except requests.RequestException as e:
        logger.error(f"Failed to fetch m3u8 for content {content_id}: {e}")
        return Response({"error": "Failed to fetch playlist"}, status=status.HTTP_502_BAD_GATEWAY)
    
    # Determine the base path for segments (same directory as master.m3u8)
    # hls_master_url is like: course_content/tenant/{tenant_id}/videos/{content_id}/hls/master.m3u8
    # We need the prefix: course_content/tenant/{tenant_id}/videos/{content_id}/hls/
    hls_base_path = asset.hls_master_url.rsplit("/", 1)[0] + "/"
    
    # Sign all segment URLs in the playlist
    # Segments are referenced as relative paths like: seg_00000.ts, seg_00001.ts
    def sign_segment(match):
        segment_name = match.group(0)
        # Skip lines that are comments or don't look like segment files
        if segment_name.startswith("#") or not segment_name.endswith(".ts"):
            return segment_name
        segment_path = hls_base_path + segment_name
        return sign_url(segment_path, expires_in=14400)  # 4 hours for playback
    
    # Replace segment references with signed URLs
    # Match lines that are .ts files (not starting with #)
    modified_m3u8 = []
    for line in m3u8_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.endswith(".ts"):
            # This is a segment reference, sign it
            segment_path = hls_base_path + line
            modified_m3u8.append(sign_url(segment_path, expires_in=14400))
        else:
            modified_m3u8.append(line)
    
    modified_content = "\n".join(modified_m3u8)
    
    return HttpResponse(
        modified_content,
        content_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Access-Control-Allow-Origin": "*",
        }
    )
