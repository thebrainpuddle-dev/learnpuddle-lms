import uuid

from django.core.files.storage import default_storage
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import admin_only, tenant_required


def _save_upload(file_obj, prefix: str) -> str:
    ext = ""
    name = getattr(file_obj, "name", "")
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
    path = f"uploads/{prefix}/{uuid.uuid4().hex}{ext}"
    saved = default_storage.save(path, file_obj)
    return default_storage.url(saved)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def upload_tenant_logo(request):
    f = request.FILES.get("file") or request.FILES.get("logo")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
    url = _save_upload(f, "tenant-logo")
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def upload_course_thumbnail(request):
    f = request.FILES.get("file") or request.FILES.get("thumbnail")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
    url = _save_upload(f, "course-thumbnail")
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def upload_content_file(request):
    f = request.FILES.get("file")
    if not f:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
    url = _save_upload(f, "content-file")
    return Response({"url": request.build_absolute_uri(url)}, status=status.HTTP_201_CREATED)

