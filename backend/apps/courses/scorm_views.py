"""
SCORM 1.2 endpoints.

Security concerns addressed here (MVP):

* Zip-slip protection — every extracted path is validated to stay inside the
  target directory (``os.path.realpath`` + ``os.path.commonpath``).
* Decompression-bomb protection — total uncompressed size is capped at
  ``MAX_EXTRACTED_SIZE_BYTES`` (100 MB). Any member ``file_size`` >
  ``MAX_MEMBER_SIZE_BYTES`` is rejected up-front, and cumulative size is
  enforced while streaming.
* XXE — ``imsmanifest.xml`` is parsed with :mod:`defusedxml.ElementTree` which
  disables external entity resolution.
* Tenant isolation — packages extract under
  ``MEDIA_ROOT/tenant/<tenant_id>/scorm/<package_uuid>`` and
  ``SCORMPackage`` uses :class:`TenantManager`.
* SCORM runtime commits — require the committing user to own a
  TeacherProgress row for the course that owns the SCORM content, plus a
  simple per-user-per-package rate limit (``COMMIT_RATE_PER_MINUTE``).
"""

from __future__ import annotations

import logging
import os
import uuid
import zipfile
from pathlib import Path

from defusedxml import ElementTree as DefusedET
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import Content, Course, Module
from .scorm_models import SCORMPackage, SCORMTrackingData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security limits
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024          # 50 MB zip
MAX_EXTRACTED_SIZE_BYTES = 100 * 1024 * 1024      # 100 MB total uncompressed
MAX_MEMBER_SIZE_BYTES = 50 * 1024 * 1024          # 50 MB per file
MAX_MEMBERS = 5000
COMMIT_RATE_PER_MINUTE = 60  # commits/minute/user/package


SCORM_NS_12 = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"
SCORM_NS_2004 = "http://www.imsglobal.org/xsd/imscp_v1p1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tenant_scorm_root(tenant_id) -> Path:
    return Path(settings.MEDIA_ROOT) / "tenant" / str(tenant_id) / "scorm"


def _safe_join(base: Path, member_name: str) -> Path | None:
    """Return an absolute path inside ``base`` for ``member_name`` or None.

    Rejects zip-slip attempts: absolute members, ``..`` escapes, drive
    letters, or any path whose real location falls outside ``base``.
    """
    if not member_name or member_name.startswith(("/", "\\")):
        return None
    if ".." in Path(member_name).parts:
        return None
    # Strip drive letter / volume refs (Windows-authored zips)
    if os.path.splitdrive(member_name)[0]:
        return None
    target = (base / member_name).resolve()
    try:
        base_resolved = base.resolve()
        # On Py3.9+ use is_relative_to; fall back to commonpath for portability.
        if hasattr(target, "is_relative_to"):
            if not target.is_relative_to(base_resolved):
                return None
        else:  # pragma: no cover - defensive
            if os.path.commonpath([str(target), str(base_resolved)]) != str(base_resolved):
                return None
    except (ValueError, OSError):
        return None
    return target


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> int:
    """Extract ``zf`` into ``dest`` with zip-slip + bomb guards.

    Returns total bytes written. Raises ``ValueError`` on any violation.
    """
    dest.mkdir(parents=True, exist_ok=True)
    members = zf.infolist()
    if len(members) > MAX_MEMBERS:
        raise ValueError(f"Too many files in zip (>{MAX_MEMBERS})")

    total_declared = sum(max(m.file_size, 0) for m in members)
    if total_declared > MAX_EXTRACTED_SIZE_BYTES:
        raise ValueError("Zip uncompressed size exceeds 100 MB cap")

    written = 0
    for member in members:
        if member.file_size > MAX_MEMBER_SIZE_BYTES:
            raise ValueError(f"Zip member too large: {member.filename}")

        # Directories are materialised lazily via makedirs below.
        name = member.filename
        if not name:
            continue

        target = _safe_join(dest, name)
        if target is None:
            raise ValueError(f"Unsafe path in zip: {name!r}")

        if member.is_dir() or name.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        # Stream-copy with a running budget to defeat lies about file_size.
        remaining = MAX_EXTRACTED_SIZE_BYTES - written
        with zf.open(member, "r") as src, open(target, "wb") as dst:
            while True:
                chunk = src.read(64 * 1024)
                if not chunk:
                    break
                if len(chunk) > remaining:
                    # Clean up partially written file; caller will nuke dest.
                    raise ValueError("Extraction exceeded size cap")
                dst.write(chunk)
                written += len(chunk)
                remaining -= len(chunk)

    return written


def _validate_launch_url(launch: str, package_root: Path) -> str:
    """Validate and normalise a manifest launch URL (M2).

    Rejects any launch URL that:
      * contains a scheme (``://``) — absolute http(s)/file/javascript URLs.
      * is absolute on POSIX or Windows (``/`` / ``\\`` prefix).
      * contains ``..`` traversal segments.
      * contains a drive letter (e.g. ``C:\\...``).

    Additionally verifies that the resolved path ``package_root / launch``
    stays inside ``package_root``.

    Returns the cleaned (possibly query-stripped) relative launch URL.
    """
    if not isinstance(launch, str) or not launch.strip():
        raise ValueError("Empty launch URL in manifest")

    raw = launch.strip()

    # Fragment and query must be preserved in the returned URL (SCORM APIs
    # may need them) but path validation runs against the path component.
    path_part = raw.split("?", 1)[0].split("#", 1)[0]

    if "://" in raw:
        raise ValueError(f"Absolute URL not permitted as launch: {raw!r}")
    if raw.startswith(("/", "\\")):
        raise ValueError(f"Absolute path not permitted as launch: {raw!r}")
    if os.path.splitdrive(raw)[0]:
        raise ValueError(f"Drive-letter path not permitted as launch: {raw!r}")
    if ".." in Path(path_part).parts:
        raise ValueError(f"Traversal not permitted in launch: {raw!r}")

    # Resolve and confirm the target file lives inside the package root.
    try:
        target = (package_root / path_part).resolve()
        base_resolved = package_root.resolve()
    except (OSError, ValueError) as exc:
        raise ValueError(f"Launch URL could not be resolved: {raw!r}") from exc

    if hasattr(target, "is_relative_to"):
        if not target.is_relative_to(base_resolved):
            raise ValueError(f"Launch URL escapes package root: {raw!r}")
    else:  # pragma: no cover - defensive
        if os.path.commonpath([str(target), str(base_resolved)]) != str(base_resolved):
            raise ValueError(f"Launch URL escapes package root: {raw!r}")

    return raw


def _parse_manifest(manifest_abs: Path) -> tuple[str, str]:
    """Parse imsmanifest.xml and return ``(version, launch_url)``.

    Uses defusedxml to prevent XXE attacks. Supports SCORM 1.2 and 2004
    namespace roots but only advertises ``version="2004"`` when the newer
    namespace is present. The launch URL is validated via
    :func:`_validate_launch_url` to enforce a relative, in-package path.
    """
    try:
        tree = DefusedET.parse(str(manifest_abs))
    except Exception as exc:  # pragma: no cover - error path tested separately
        raise ValueError(f"Malformed imsmanifest.xml: {exc}") from exc

    root = tree.getroot()
    tag = root.tag.lower()
    version = "2004" if SCORM_NS_2004 in tag else "1.2"

    # MVP: find the first resource with an href attribute — the reviewer
    # accepted this for SCORM 1.2 packages (single-resource typical). A
    # follow-up task will walk ``organizations > organization(@default) >
    # item(@identifierref) → resource(@identifier)`` for multi-resource
    # 2004 packages.
    launch: str | None = None
    for elem in root.iter():
        # Strip namespace prefix
        local = elem.tag.split("}", 1)[-1].lower()
        if local == "resource":
            href = elem.get("href")
            if href:
                launch = href
                break
    if not launch:
        raise ValueError("imsmanifest.xml has no launchable resource with href")

    package_root = manifest_abs.parent
    launch = _validate_launch_url(launch, package_root)
    return version, launch


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@admin_only
@tenant_required
def scorm_upload(request):
    """Upload + import a SCORM package.

    Required form fields:
        - file            : the .zip upload
        - course_id       : UUID
        - module_id       : UUID
        - title           : display title

    Creates a ``Content`` row (type=SCORM) and a 1:1 ``SCORMPackage``.
    """
    upload = request.FILES.get("file")
    if not upload:
        return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

    if upload.size and upload.size > MAX_UPLOAD_SIZE_BYTES:
        return Response(
            {"error": "Upload exceeds 50 MB limit"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    course_id = request.data.get("course_id")
    module_id = request.data.get("module_id")
    title = (request.data.get("title") or "SCORM Package").strip()[:300]
    if not course_id or not module_id:
        return Response(
            {"error": "course_id and module_id are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    course = get_object_or_404(Course.objects.all(), id=course_id, tenant=request.tenant)
    module = get_object_or_404(
        Module.objects.filter(course=course, is_active=True), id=module_id
    )

    package_uuid = uuid.uuid4()
    root = _tenant_scorm_root(request.tenant.id) / str(package_uuid)

    try:
        # Open zip from the uploaded file. Django's UploadedFile is a
        # file-like and zipfile accepts a file object.
        with zipfile.ZipFile(upload, "r") as zf:
            # L2 — match case-insensitively and normalise Windows separators.
            # Some authoring tools emit ``IMSManifest.xml`` or backslash
            # paths, both of which are valid SCORM packages.
            names = [m.filename for m in zf.infolist()]
            normalised = [n.replace("\\", "/").lower() for n in names]
            has_root_manifest = "imsmanifest.xml" in normalised or any(
                n.endswith("/imsmanifest.xml") and n.count("/") == 1
                for n in normalised
            )
            if not has_root_manifest:
                return Response(
                    {"error": "Zip does not contain imsmanifest.xml at root"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            written = _safe_extract_zip(zf, root)
    except zipfile.BadZipFile:
        return Response({"error": "Invalid zip file"}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as exc:
        # Clean up partially extracted content
        _rmtree_safe(root)
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.exception("SCORM extract failed")
        _rmtree_safe(root)
        return Response(
            {"error": "Could not extract SCORM package"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    manifest_abs = root / "imsmanifest.xml"
    if not manifest_abs.exists():
        _rmtree_safe(root)
        return Response(
            {"error": "imsmanifest.xml not at package root after extraction"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        version, launch_url = _parse_manifest(manifest_abs)
    except ValueError as exc:
        _rmtree_safe(root)
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    package_path_rel = f"tenant/{request.tenant.id}/scorm/{package_uuid}"

    with transaction.atomic():
        # Order at the end of the module
        last_order = (
            Content.all_objects.filter(module=module)
            .order_by("-order")
            .values_list("order", flat=True)
            .first()
        ) or 0
        content = Content.objects.create(
            module=module,
            title=title,
            content_type="SCORM",
            order=last_order + 1,
            is_mandatory=True,
            is_active=True,
        )
        package = SCORMPackage.objects.create(
            tenant=request.tenant,
            content=content,
            manifest_path=f"{package_path_rel}/imsmanifest.xml",
            launch_url=launch_url,
            version=version,
            package_path=package_path_rel,
            package_size=written,
            uploaded_by=request.user,
        )

    log_audit(
        action="CREATE",
        target_type="SCORMPackage",
        target_id=str(package.id),
        target_repr=title,
        request=request,
        changes={"content_id": str(content.id), "version": version},
    )

    return Response(
        {
            "package_id": str(package.id),
            "content_id": str(content.id),
            "launch_url": launch_url,
            "package_path": package_path_rel,
            "version": version,
            "package_size": written,
        },
        status=status.HTTP_201_CREATED,
    )


def _rmtree_safe(path: Path) -> None:
    """Recursively remove a directory, ignoring errors."""
    import shutil

    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:  # pragma: no cover
        logger.exception("Failed to clean up %s", path)


@csrf_exempt
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
@tenant_required
def scorm_commit(request):
    """SCORM 1.2 runtime commit endpoint.

    Body: ``{"package_id": "...", "cmi": {...}}``

    Authorization: the user must be authenticated AND enrolled (via
    TeacherProgress) in the course that owns the SCORM content, OR be an
    admin. Rate-limited per (user, package).
    """
    package_id = request.data.get("package_id")
    cmi = request.data.get("cmi")
    if not package_id or not isinstance(cmi, dict):
        return Response(
            {"error": "package_id and cmi (object) are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # L1 — belt-and-braces: even though TenantMiddleware enforces this,
    # re-assert tenant match in case middleware ordering regresses.
    user = request.user
    if getattr(user, "tenant_id", None) and user.tenant_id != request.tenant.id:
        logger.warning(
            "SCORM commit cross-tenant attempt user=%s tenant=%s request_tenant=%s",
            user.id, user.tenant_id, request.tenant.id,
        )
        return Response(
            {"error": "Tenant mismatch"},
            status=status.HTTP_403_FORBIDDEN,
        )

    package = get_object_or_404(
        SCORMPackage.objects.select_related("content__module__course"),
        id=package_id,
        tenant=request.tenant,
    )

    # --- Authorization: admins always ok; otherwise require enrollment.
    if user.role not in {"SCHOOL_ADMIN", "SUPER_ADMIN"}:
        course = package.content.module.course
        from apps.progress.models import TeacherProgress

        enrolled = TeacherProgress.objects.filter(
            teacher=user, course=course
        ).exists()
        if not enrolled:
            return Response(
                {"error": "Not enrolled in this course"},
                status=status.HTTP_403_FORBIDDEN,
            )

    # --- Rate-limit: key per (user, package), 60/min. Must fail CLOSED on
    # cache outage (H2) — otherwise Redis downtime silently disables the
    # limiter and invites flood attacks.
    rate_key = f"scorm:commit:{user.id}:{package_id}"
    try:
        current = cache.get(rate_key)
    except Exception:
        logger.exception("SCORM rate-limit cache unavailable (get)")
        return Response(
            {"error": "service_unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if current is None:
        current = 0
    if current >= COMMIT_RATE_PER_MINUTE:
        return Response(
            {"error": "Commit rate limit exceeded"},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    try:
        cache.set(rate_key, current + 1, timeout=60)
    except Exception:
        logger.exception("SCORM rate-limit cache unavailable (set)")
        return Response(
            {"error": "service_unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # --- Persist tracking row.
    lesson_status = str(cmi.get("cmi.core.lesson_status") or cmi.get("lesson_status") or "")[:32]
    session_time = str(cmi.get("cmi.core.session_time") or cmi.get("session_time") or "")[:32]
    total_time = str(cmi.get("cmi.core.total_time") or cmi.get("total_time") or "")[:32]
    score_raw = cmi.get("cmi.core.score.raw") or cmi.get("score_raw")
    try:
        score_raw_f = float(score_raw) if score_raw not in (None, "") else None
    except (TypeError, ValueError):
        score_raw_f = None

    tracking, _created = SCORMTrackingData.objects.update_or_create(
        package=package,
        user=user,
        defaults={
            "tenant": request.tenant,
            "lesson_status": lesson_status,
            "session_time": session_time,
            "total_time": total_time,
            "score_raw": score_raw_f,
            "cmi": cmi,
        },
    )

    return Response(
        {
            "ok": True,
            "tracking_id": str(tracking.id),
            "lesson_status": tracking.lesson_status,
            "score_raw": tracking.score_raw,
        },
        status=status.HTTP_200_OK,
    )
