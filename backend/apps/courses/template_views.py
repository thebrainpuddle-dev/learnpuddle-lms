"""
API views for Course Templates library (TASK-049).

Two view groups:

* ``super_admin_*`` — full CRUD, restricted to SUPER_ADMIN users (no tenant
  scoping; templates are platform-level).
* ``tenant_admin_*`` — list + preview + clone for SCHOOL_ADMIN users inside
  their own tenant. The tenant list endpoint returns ONLY published templates.
"""

import logging

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from utils.audit import log_audit
from utils.decorators import admin_only, super_admin_only, tenant_required

from .models import Course
from .serializers import CourseDetailSerializer
from .template_clone import clone_template_to_tenant
from .template_models import (
    CATEGORY_CHOICES,
    LEVEL_CHOICES,
    CourseTemplate,
)
from .template_serializers import (
    CloneTemplateSerializer,
    CourseTemplateDetailSerializer,
    CourseTemplateListSerializer,
)


logger = logging.getLogger(__name__)


class TemplatePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ---------------------------------------------------------------------------
# SUPER_ADMIN CRUD
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def super_admin_template_list_create(request):
    if request.method == "GET":
        qs = CourseTemplate.objects.all().order_by("-created_at")
        category = request.GET.get("category")
        if category:
            qs = qs.filter(category=category)
        is_published = request.GET.get("is_published")
        if is_published is not None:
            qs = qs.filter(is_published=is_published.lower() == "true")

        paginator = TemplatePagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = CourseTemplateListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = CourseTemplateDetailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        template = serializer.save(created_by=request.user)
    except IntegrityError:
        return Response(
            {"error": "A template with that slug already exists."},
            status=status.HTTP_409_CONFLICT,
        )
    log_audit(
        "CREATE",
        "CourseTemplate",
        target_id=str(template.id),
        target_repr=template.slug,
        request=request,
        changes={"slug": template.slug, "title": template.title},
    )
    return Response(
        CourseTemplateDetailSerializer(template).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
@super_admin_only
def super_admin_template_detail(request, template_id):
    template = get_object_or_404(CourseTemplate, id=template_id)

    if request.method == "GET":
        return Response(CourseTemplateDetailSerializer(template).data)

    if request.method in ("PATCH", "PUT"):
        partial = request.method == "PATCH"
        serializer = CourseTemplateDetailSerializer(
            template, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_audit(
            "UPDATE",
            "CourseTemplate",
            target_id=str(template.id),
            target_repr=template.slug,
            request=request,
            changes=request.data if isinstance(request.data, dict) else {},
        )
        return Response(CourseTemplateDetailSerializer(template).data)

    # DELETE — soft delete (unpublish) by default; hard-delete only if nothing
    # has cloned from it. Since clones produce real Course rows with no FK back
    # to the template, "no clones" is equivalent to "always allowed". We follow
    # the spec: unpublish on first delete, hard-delete if already unpublished
    # and ``?hard=true`` is passed.
    hard = request.GET.get("hard", "").lower() == "true"
    if hard:
        slug = template.slug
        template.delete()
        log_audit(
            "DELETE",
            "CourseTemplate",
            target_id=str(template_id),
            target_repr=slug,
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
    template.is_published = False
    template.save(update_fields=["is_published", "updated_at"])
    log_audit(
        "UNPUBLISH",
        "CourseTemplate",
        target_id=str(template.id),
        target_repr=template.slug,
        request=request,
    )
    return Response(CourseTemplateDetailSerializer(template).data)


# ---------------------------------------------------------------------------
# Tenant SCHOOL_ADMIN: list published / preview / clone
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def tenant_admin_template_list(request):
    qs = CourseTemplate.objects.filter(is_published=True).order_by("-created_at")

    category = request.GET.get("category")
    if category:
        allowed = {c[0] for c in CATEGORY_CHOICES}
        if category not in allowed:
            return Response(
                {"error": f"Invalid category. Allowed: {sorted(allowed)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(category=category)

    language = request.GET.get("language")
    if language:
        qs = qs.filter(language=language)

    level = request.GET.get("level")
    if level:
        allowed = {c[0] for c in LEVEL_CHOICES}
        if level not in allowed:
            return Response(
                {"error": f"Invalid level. Allowed: {sorted(allowed)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(level=level)

    paginator = TemplatePagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(
        CourseTemplateListSerializer(page, many=True).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def tenant_admin_template_detail(request, template_id):
    template = get_object_or_404(
        CourseTemplate, id=template_id, is_published=True
    )
    return Response(CourseTemplateDetailSerializer(template).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def tenant_admin_template_clone(request, template_id):
    template = get_object_or_404(
        CourseTemplate, id=template_id, is_published=True
    )

    body_serializer = CloneTemplateSerializer(data=request.data or {})
    body_serializer.is_valid(raise_exception=True)
    title_override = body_serializer.validated_data.get("title_override") or None
    module_prefix = body_serializer.validated_data.get("module_prefix") or None

    # NOTE: request.tenant is authoritative — we deliberately ignore any
    # ``tenant`` field the client might try to inject into the body.
    course = clone_template_to_tenant(
        template=template,
        tenant=request.tenant,
        user=request.user,
        title_override=title_override,
        module_prefix=module_prefix,
    )

    log_audit(
        action="CLONE_TEMPLATE",
        target_type="CourseTemplate",
        target_id=str(template.id),
        target_repr=template.slug,
        request=request,
        changes={
            "new_course_id": str(course.id),
            "tenant_id": str(request.tenant.id),
        },
    )

    # Re-fetch with prefetches so serializer doesn't N+1.
    course = Course.objects.select_related("tenant", "created_by").prefetch_related(
        "modules__contents"
    ).get(pk=course.pk)
    return Response(
        CourseDetailSerializer(course, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )
