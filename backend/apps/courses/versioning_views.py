"""
Admin-only, tenant-scoped endpoints for listing / viewing / restoring
revisions of Course / Module / Content (TASK-048).

URLs (mounted under `/api/v1/admin/`):

    GET  courses/{id}/revisions/
    GET  courses/{id}/revisions/{rev}/
    POST courses/{id}/revisions/{rev}/restore/
    (and the same three for modules/ and contents/)
"""

from __future__ import annotations

import logging

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import Content, Course, Module
from .versioning_models import ContentRevision
from .versioning_serializers import (
    ContentRevisionDetailSerializer,
    ContentRevisionListSerializer,
)
from .versioning_signals import suppress_versioning
from .versioning_snapshot import (
    CONTENT_RESTORABLE_FIELDS,
    COURSE_RESTORABLE_FIELDS,
    COURSE_RESTORABLE_M2M,
    MODULE_RESTORABLE_FIELDS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class RevisionPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


# ---------------------------------------------------------------------------
# Target resolution — enforces tenant isolation
# ---------------------------------------------------------------------------

def _resolve_course(request, course_id):
    return get_object_or_404(
        Course.all_objects.filter(tenant=request.tenant),
        pk=course_id,
    )


def _resolve_module(request, module_id):
    return get_object_or_404(
        Module.all_objects.filter(course__tenant=request.tenant),
        pk=module_id,
    )


def _resolve_content(request, content_id):
    return get_object_or_404(
        Content.all_objects.filter(module__course__tenant=request.tenant),
        pk=content_id,
    )


def _revisions_qs(request, model_cls, object_id):
    ct = ContentType.objects.get_for_model(model_cls)
    return (
        ContentRevision.objects
        .filter(content_type=ct, object_id=object_id)
        .select_related("changed_by", "content_type")
        .order_by("-revision_number")
    )


def _list_revisions(request, model_cls, object_id):
    qs = _revisions_qs(request, model_cls, object_id)
    paginator = RevisionPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ContentRevisionListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


def _get_revision(request, model_cls, object_id, revision_number):
    qs = _revisions_qs(request, model_cls, object_id)
    rev = get_object_or_404(qs, revision_number=revision_number)
    return Response(ContentRevisionDetailSerializer(rev).data)


# ---------------------------------------------------------------------------
# Restore helpers
# ---------------------------------------------------------------------------

def _coerce_defaults(snap: dict, field_names: tuple) -> dict:
    """Pull every key listed in ``field_names`` out of the snapshot dict.

    Returns a ``defaults`` dict suitable for ``update_or_create`` /
    assignment. Keys absent from ``snap`` are left out so the model
    column keeps its current value rather than being clobbered with
    ``None`` (important for forward-compat with older snapshots).
    """
    defaults: dict = {}
    for name in field_names:
        if name in snap:
            defaults[name] = snap[name]
    return defaults


def _apply_content_snapshot(module, snap):
    """Create-or-update a Content row from its snapshot dict (stable UUID).

    Iterates :data:`CONTENT_RESTORABLE_FIELDS` so every scalar field the
    snapshot captures is written back. Adding a new field only requires
    updating the registry in ``versioning_snapshot.py``.
    """
    defaults = _coerce_defaults(snap, CONTENT_RESTORABLE_FIELDS)
    defaults["module"] = module
    # Resurrect if previously soft-deleted.
    defaults["is_deleted"] = False
    defaults["deleted_at"] = None
    obj, _ = Content.all_objects.update_or_create(
        id=snap["id"],
        defaults=defaults,
    )
    return obj


def _apply_module_snapshot(course, snap):
    """Create-or-update a Module row + all its contents from a snapshot."""
    defaults = _coerce_defaults(snap, MODULE_RESTORABLE_FIELDS)
    defaults["course"] = course
    defaults["is_deleted"] = False
    defaults["deleted_at"] = None
    module, _ = Module.all_objects.update_or_create(
        id=snap["id"],
        defaults=defaults,
    )
    # Children
    desired_content_ids = set()
    for c_snap in snap.get("contents") or []:
        _apply_content_snapshot(module, c_snap)
        desired_content_ids.add(str(c_snap["id"]))
    # Soft-delete contents that aren't in the snapshot.
    Content.all_objects.filter(module=module).exclude(
        id__in=desired_content_ids
    ).update(is_deleted=True)
    return module


def _apply_course_snapshot(course, snap):
    """Apply a course snapshot to an existing Course row (tenant preserved).

    Writes every scalar field in :data:`COURSE_RESTORABLE_FIELDS`, then
    resyncs the M2Ms listed in :data:`COURSE_RESTORABLE_M2M` filtered by
    tenant to prevent cross-tenant pollution if a stale ID somehow
    survived in the snapshot.
    """
    from datetime import date
    from decimal import Decimal as _Decimal

    for field_name in COURSE_RESTORABLE_FIELDS:
        if field_name not in snap:
            continue
        value = snap[field_name]
        # Coerce string scalars back to their Django field type. The
        # snapshot deliberately stores JSON-friendly strings so two
        # consecutive serializations produce byte-identical JSON.
        if field_name == "deadline" and isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                value = None
        elif field_name == "estimated_hours" and isinstance(value, str):
            try:
                value = _Decimal(value)
            except Exception:
                value = _Decimal("0")
        setattr(course, field_name, value)
    # `is_deleted=False` is part of the registry but also clear the audit
    # timestamp explicitly (no corresponding snapshot key).
    course.deleted_at = None
    course.save()

    # M2Ms — resync filtered by tenant.
    # Forward-compat: only call .set() when the key is explicitly present in
    # the snapshot. Older snapshots that pre-date a new M2M field must not
    # silently wipe the live relation by falling back to an empty list.
    from apps.users.models import User
    for m2m_name in COURSE_RESTORABLE_M2M:
        if m2m_name not in snap:
            continue
        if not hasattr(course, m2m_name):
            continue
        ids = snap[m2m_name] or []
        manager = getattr(course, m2m_name)
        # Filter by tenant so a stale cross-tenant id in the snapshot is
        # silently dropped rather than re-attached.
        qs = User.objects.filter(id__in=ids, tenant=course.tenant)
        manager.set(qs)

    desired_module_ids = set()
    for m_snap in snap.get("modules") or []:
        _apply_module_snapshot(course, m_snap)
        desired_module_ids.add(str(m_snap["id"]))
    # Soft-delete modules not in snapshot.
    Module.all_objects.filter(course=course).exclude(
        id__in=desired_module_ids
    ).update(is_deleted=True)
    return course


def _record_restore_revision(target_instance, source_rev, user):
    """Append a new revision marking the restore in the audit trail."""
    from .versioning_snapshot import serialize_instance

    ct = ContentType.objects.get_for_model(target_instance.__class__)
    last = (
        ContentRevision.all_objects
        .filter(content_type=ct, object_id=target_instance.pk)
        .order_by("-revision_number")
        .first()
    )
    next_number = 1 if last is None else last.revision_number + 1

    # Tenant lookup mirrors signal logic.
    from .versioning_signals import _resolve_tenant  # noqa: WPS437
    tenant = _resolve_tenant(target_instance)

    ContentRevision.all_objects.create(
        tenant=tenant,
        content_type=ct,
        object_id=target_instance.pk,
        revision_number=next_number,
        snapshot_json=serialize_instance(target_instance),
        changed_by=user,
        change_summary=f"restore-from-v{source_rev.revision_number}",
    )


# ---------------------------------------------------------------------------
# Course endpoints
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_revisions_list(request, course_id):
    course = _resolve_course(request, course_id)
    return _list_revisions(request, Course, course.id)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_revision_detail(request, course_id, revision_number):
    course = _resolve_course(request, course_id)
    return _get_revision(request, Course, course.id, revision_number)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_revision_restore(request, course_id, revision_number):
    course = _resolve_course(request, course_id)
    ct = ContentType.objects.get_for_model(Course)
    rev = get_object_or_404(
        ContentRevision.objects.filter(content_type=ct, object_id=course.id),
        revision_number=revision_number,
    )

    try:
        with transaction.atomic():
            with suppress_versioning():
                _apply_course_snapshot(course, rev.snapshot_json)
            course.refresh_from_db()
            _record_restore_revision(course, rev, request.user)
    except Exception:
        logger.exception("Course restore failed")
        return Response(
            {"error": "Failed to restore revision"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    log_audit(
        action="RESTORE_REVISION",
        target_type="Course",
        target_id=str(course.id),
        target_repr=course.title,
        changes={"restored_from_revision": rev.revision_number},
        request=request,
    )

    # Return the restored course via the existing detail serializer.
    from .serializers import CourseDetailSerializer
    return Response(
        CourseDetailSerializer(course, context={"request": request}).data,
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Module endpoints
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def module_revisions_list(request, module_id):
    module = _resolve_module(request, module_id)
    return _list_revisions(request, Module, module.id)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def module_revision_detail(request, module_id, revision_number):
    module = _resolve_module(request, module_id)
    return _get_revision(request, Module, module.id, revision_number)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def module_revision_restore(request, module_id, revision_number):
    module = _resolve_module(request, module_id)
    ct = ContentType.objects.get_for_model(Module)
    rev = get_object_or_404(
        ContentRevision.objects.filter(content_type=ct, object_id=module.id),
        revision_number=revision_number,
    )

    try:
        with transaction.atomic():
            with suppress_versioning():
                _apply_module_snapshot(module.course, rev.snapshot_json)
            module.refresh_from_db()
            _record_restore_revision(module, rev, request.user)
    except Exception:
        logger.exception("Module restore failed")
        return Response(
            {"error": "Failed to restore revision"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    log_audit(
        action="RESTORE_REVISION",
        target_type="Module",
        target_id=str(module.id),
        target_repr=module.title,
        changes={"restored_from_revision": rev.revision_number},
        request=request,
    )

    from .serializers import ModuleSerializer
    return Response(
        ModuleSerializer(module, context={"request": request}).data,
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Content endpoints
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def content_revisions_list(request, content_id):
    content = _resolve_content(request, content_id)
    return _list_revisions(request, Content, content.id)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def content_revision_detail(request, content_id, revision_number):
    content = _resolve_content(request, content_id)
    return _get_revision(request, Content, content.id, revision_number)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def content_revision_restore(request, content_id, revision_number):
    content = _resolve_content(request, content_id)
    ct = ContentType.objects.get_for_model(Content)
    rev = get_object_or_404(
        ContentRevision.objects.filter(content_type=ct, object_id=content.id),
        revision_number=revision_number,
    )

    try:
        with transaction.atomic():
            with suppress_versioning():
                _apply_content_snapshot(content.module, rev.snapshot_json)
            content.refresh_from_db()
            _record_restore_revision(content, rev, request.user)
    except Exception:
        logger.exception("Content restore failed")
        return Response(
            {"error": "Failed to restore revision"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    log_audit(
        action="RESTORE_REVISION",
        target_type="Content",
        target_id=str(content.id),
        target_repr=content.title,
        changes={"restored_from_revision": rev.revision_number},
        request=request,
    )

    from .serializers import ContentSerializer
    return Response(
        ContentSerializer(content, context={"request": request}).data,
        status=status.HTTP_200_OK,
    )
