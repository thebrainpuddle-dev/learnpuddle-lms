from django.core.files.storage import default_storage
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework import status

from utils.decorators import admin_only, tenant_required, teacher_or_admin
from utils.storage_paths import (
    tenant_logo_path,
    course_thumbnail_path,
    course_document_path,
    rich_text_image_path,
)
from utils.s3_utils import sign_url

from apps.courses.models import RichTextImageAsset


class UploadThrottle(ScopedRateThrottle):
    scope = 'upload'


# ---------------------------------------------------------------------------
# Upload validation helpers
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
}
MAX_IMAGE_SIZE_MB = 5  # 5 MB

ALLOWED_CONTENT_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".txt", ".md", ".csv",
}
ALLOWED_CONTENT_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/markdown", "text/csv",
}
MAX_CONTENT_SIZE_MB = 50  # 50 MB
MAX_EDITOR_IMAGE_SIZE_MB = 8  # 8 MB


def _validate_upload(file_obj, allowed_exts, allowed_mimes, max_size_mb):
    """
    Validate an uploaded file against extension, MIME type, and size limits.
    Returns (ok: bool, error_message: str | None).
    """
    name = getattr(file_obj, "name", "") or ""
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()

    mime = getattr(file_obj, "content_type", "") or ""

    # Reject files with neither extension nor MIME type
    if not ext and not mime:
        return False, "File must have a recognizable extension or MIME type."

    if ext and ext not in allowed_exts:
        return False, f"File type '{ext}' is not allowed. Accepted: {', '.join(sorted(allowed_exts))}"

    if mime and mime not in allowed_mimes:
        return False, f"MIME type '{mime}' is not allowed."

    size_bytes = getattr(file_obj, "size", 0) or 0
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        return False, f"File too large ({size_bytes / (1024*1024):.1f} MB). Maximum: {max_size_mb} MB."

    return True, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UploadThrottle])
@admin_only
@tenant_required
def upload_tenant_logo(request):
    f = request.FILES.get("file") or request.FILES.get("logo")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

    ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, MAX_IMAGE_SIZE_MB)
    if not ok:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    tenant_id = str(request.tenant.id)
    filename = getattr(f, "name", "logo.png")
    path = tenant_logo_path(tenant_id, filename)
    saved = default_storage.save(path, f)
    url = default_storage.url(saved)
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UploadThrottle])
@admin_only
@tenant_required
def upload_course_thumbnail(request):
    f = request.FILES.get("file") or request.FILES.get("thumbnail")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

    ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, MAX_IMAGE_SIZE_MB)
    if not ok:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    tenant_id = str(request.tenant.id)
    filename = getattr(f, "name", "thumbnail.png")
    path = course_thumbnail_path(tenant_id, filename)
    saved = default_storage.save(path, f)
    url = default_storage.url(saved)
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UploadThrottle])
@teacher_or_admin
@tenant_required
def upload_content_file(request):
    """
    Upload a document/content file for course content.
    Requires content_id query param to organize files properly.
    Available to admins and teacher-authoring roles.
    """
    if request.user.role in ["TEACHER", "HOD", "IB_COORDINATOR"] and not getattr(
        request.tenant, "feature_teacher_authoring", False
    ):
        return Response(
            {"error": "Teacher course authoring is not available on your plan.", "upgrade_required": True},
            status=status.HTTP_403_FORBIDDEN,
        )

    f = request.FILES.get("file")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

    ok, err = _validate_upload(f, ALLOWED_CONTENT_EXTENSIONS, ALLOWED_CONTENT_MIMES, MAX_CONTENT_SIZE_MB)
    if not ok:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    tenant_id = str(request.tenant.id)
    filename = getattr(f, "name", "document.pdf")
    content_id = request.query_params.get("content_id", "general")
    path = course_document_path(tenant_id, content_id, filename)
    saved = default_storage.save(path, f)
    url = default_storage.url(saved)
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UploadThrottle])
@teacher_or_admin
@tenant_required
def upload_editor_image(request):
    """
    Upload an inline image for the rich-text editor.

    Stores file in tenant-scoped object storage and returns:
    - `asset_ref`: stable canonical reference used inside stored HTML (`rtimg:<uuid>`)
    - `preview_url`: signed/public URL for immediate editor display
    """
    if request.user.role in ["TEACHER", "HOD", "IB_COORDINATOR"] and not getattr(
        request.tenant, "feature_teacher_authoring", False
    ):
        return Response(
            {"error": "Teacher course authoring is not available on your plan.", "upgrade_required": True},
            status=status.HTTP_403_FORBIDDEN,
        )

    f = request.FILES.get("file") or request.FILES.get("image")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

    ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, MAX_EDITOR_IMAGE_SIZE_MB)
    if not ok:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    tenant_id = str(request.tenant.id)
    filename = getattr(f, "name", "editor-image.png")
    path = rich_text_image_path(tenant_id, filename)
    saved = default_storage.save(path, f)

    asset = RichTextImageAsset.objects.create(
        tenant=request.tenant,
        storage_key=saved,
        file_size=getattr(f, "size", None),
        uploaded_by=request.user,
    )

    preview_url = sign_url(saved, expires_in=3600)
    if not preview_url.startswith("http"):
        preview_url = request.build_absolute_uri(preview_url)

    return Response(
        {
            "asset_id": str(asset.id),
            "asset_ref": f"rtimg:{asset.id}",
            "preview_url": preview_url,
            "file_size": asset.file_size,
        },
        status=status.HTTP_201_CREATED,
    )
