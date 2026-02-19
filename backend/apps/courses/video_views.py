import uuid

from celery import chain, group
from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from utils.decorators import admin_only, tenant_required, check_feature
from utils.storage_paths import course_video_source_path


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

    return Response(
        {
            "content": ContentSerializer(content).data,
            "video_asset": (
                {
                    "id": str(asset.id),
                    "status": asset.status,
                    "error_message": asset.error_message,
                    "duration_seconds": asset.duration_seconds,
                    "hls_master_url": _maybe_absolute(request, asset.hls_master_url),
                    "thumbnail_url": _maybe_absolute(request, asset.thumbnail_url),
                    "source_url": _maybe_absolute(request, asset.source_url),
                }
                if asset
                else None
            ),
            "transcript": (
                {
                    "language": transcript.language,
                    "full_text_preview": (transcript.full_text[:240] + "...") if transcript.full_text else "",
                    "vtt_url": _maybe_absolute(request, transcript.vtt_url),
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
