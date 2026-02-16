import uuid

from django.core.files.storage import default_storage
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework import status

from utils.decorators import admin_only, tenant_required


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


def _save_upload(file_obj, prefix: str, tenant_id: str) -> str:
    ext = ""
    name = getattr(file_obj, "name", "")
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
    path = f"tenant/{tenant_id}/uploads/{prefix}/{uuid.uuid4().hex}{ext}"
    saved = default_storage.save(path, file_obj)
    return default_storage.url(saved)


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

    url = _save_upload(f, "tenant-logo", str(request.tenant.id))
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

    url = _save_upload(f, "course-thumbnail", str(request.tenant.id))
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UploadThrottle])
@admin_only
@tenant_required
def upload_content_file(request):
    f = request.FILES.get("file")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

    ok, err = _validate_upload(f, ALLOWED_CONTENT_EXTENSIONS, ALLOWED_CONTENT_MIMES, MAX_CONTENT_SIZE_MB)
    if not ok:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    url = _save_upload(f, "content-file", str(request.tenant.id))
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)
