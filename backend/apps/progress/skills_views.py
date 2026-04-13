# apps/progress/skills_views.py

import logging
from datetime import datetime, timezone

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import admin_only, teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class
from utils.responses import error_response

from .skills_models import CourseSkill, Skill, TeacherSkill
from .skills_serializers import (
    BulkTeacherSkillUpdateSerializer,
    CourseSkillCreateSerializer,
    CourseSkillSerializer,
    SkillCreateSerializer,
    SkillSerializer,
    TeacherSkillSerializer,
    TeacherSkillUpdateSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill CRUD (admin only)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def skill_list(request):
    """List all skills for the tenant. Supports ?category= and ?search= filters."""
    qs = Skill.objects.all().order_by('category', 'name')

    category = request.GET.get("category")
    if category:
        qs = qs.filter(category__iexact=category)

    search = request.GET.get("search")
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = SkillSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = SkillSerializer(qs, many=True)
    return Response({"results": serializer.data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def skill_create(request):
    """Create a new skill."""
    serializer = SkillCreateSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    skill = Skill(
        tenant=request.tenant,
        **serializer.validated_data,
    )
    skill.save()
    return Response(SkillSerializer(skill).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def skill_detail(request, skill_id):
    """Retrieve a single skill."""
    skill = get_object_or_404(Skill, id=skill_id, tenant=request.tenant)
    return Response(SkillSerializer(skill).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def skill_update(request, skill_id):
    """Update a skill."""
    skill = get_object_or_404(Skill, id=skill_id, tenant=request.tenant)
    serializer = SkillCreateSerializer(
        skill, data=request.data, partial=True, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)
    for attr, value in serializer.validated_data.items():
        setattr(skill, attr, value)
    skill.save()
    return Response(SkillSerializer(skill).data, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def skill_delete(request, skill_id):
    """Delete a skill and all related mappings."""
    skill = get_object_or_404(Skill, id=skill_id, tenant=request.tenant)
    skill.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Skill categories
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def skill_categories(request):
    """List distinct skill categories for the tenant."""
    categories = (
        Skill.objects.filter(category__gt='')
        .values_list('category', flat=True)
        .distinct()
        .order_by('category')
    )
    return Response({"categories": list(categories)}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# CourseSkill mapping (admin only)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_skill_list(request):
    """
    List course-skill mappings.
    Supports ?course_id= and ?skill_id= filters.
    """
    qs = CourseSkill.objects.select_related('course', 'skill').filter(
        course__tenant=request.tenant,
    )

    course_id = request.GET.get("course_id")
    if course_id:
        qs = qs.filter(course_id=course_id)

    skill_id = request.GET.get("skill_id")
    if skill_id:
        qs = qs.filter(skill_id=skill_id)

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = CourseSkillSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = CourseSkillSerializer(qs, many=True)
    return Response({"results": serializer.data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_skill_create(request):
    """Map a skill to a course."""
    serializer = CourseSkillCreateSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)

    # Validate that skill and course belong to this tenant
    skill = serializer.validated_data['skill']
    course = serializer.validated_data['course']
    if skill.tenant_id != request.tenant.id:
        return error_response("Skill does not belong to this tenant.", status_code=status.HTTP_400_BAD_REQUEST)
    if course.tenant_id != request.tenant.id:
        return error_response("Course does not belong to this tenant.", status_code=status.HTTP_400_BAD_REQUEST)

    mapping = CourseSkill.objects.create(**serializer.validated_data)
    return Response(
        CourseSkillSerializer(mapping).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_skill_delete(request, mapping_id):
    """Remove a course-skill mapping."""
    mapping = get_object_or_404(CourseSkill, id=mapping_id, course__tenant=request.tenant)
    mapping.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Teacher Skill Matrix
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_skill_matrix(request):
    """
    View teacher skill matrix.
    - Admins: see all teachers' skills. Supports ?teacher_id= filter.
    - Teachers: see only their own skills.
    """
    user = request.user
    is_admin = user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN')

    qs = TeacherSkill.objects.select_related('skill', 'teacher').all()

    if is_admin:
        teacher_id = request.GET.get("teacher_id")
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
    else:
        qs = qs.filter(teacher=user)

    # Optional filters
    category = request.GET.get("category")
    if category:
        qs = qs.filter(skill__category__iexact=category)

    gaps_only = request.GET.get("gaps_only")
    if gaps_only and gaps_only.lower() in ('true', '1', 'yes'):
        from django.db.models import F
        qs = qs.filter(current_level__lt=F('target_level'))

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = TeacherSkillSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = TeacherSkillSerializer(qs, many=True)
    return Response({"results": serializer.data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_skill_assign(request):
    """
    Assign a skill to a teacher (create a TeacherSkill record).
    Body: { teacher, skill, current_level?, target_level? }
    """
    teacher_id = request.data.get("teacher")
    skill_id = request.data.get("skill")

    if not teacher_id or not skill_id:
        return error_response("teacher and skill are required.", status_code=status.HTTP_400_BAD_REQUEST)

    from apps.users.models import User
    teacher = get_object_or_404(User, id=teacher_id, tenant=request.tenant, is_active=True)
    skill = get_object_or_404(Skill, id=skill_id, tenant=request.tenant)

    # Validate current_level and target_level
    current_level = request.data.get("current_level", 0)
    target_level = request.data.get("target_level", skill.level_required)
    try:
        current_level = int(current_level)
        target_level = int(target_level)
    except (ValueError, TypeError):
        return error_response(
            "current_level and target_level must be integers in range 0-5.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not (0 <= current_level <= 5) or not (0 <= target_level <= 5):
        return error_response(
            "current_level and target_level must be integers in range 0-5.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Check for duplicate
    if TeacherSkill.all_objects.filter(teacher=teacher, skill=skill).exists():
        return error_response("This skill is already assigned to this teacher.", status_code=status.HTTP_400_BAD_REQUEST)

    ts = TeacherSkill.objects.create(
        teacher=teacher,
        skill=skill,
        tenant=request.tenant,
        current_level=current_level,
        target_level=target_level,
    )
    return Response(TeacherSkillSerializer(ts).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_skill_update(request, teacher_skill_id):
    """Update a teacher's skill level (current_level and/or target_level)."""
    ts = get_object_or_404(TeacherSkill, id=teacher_skill_id, tenant=request.tenant)
    serializer = TeacherSkillUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if 'current_level' in serializer.validated_data:
        ts.current_level = serializer.validated_data['current_level']
        ts.last_assessed = datetime.now(timezone.utc)
    if 'target_level' in serializer.validated_data:
        ts.target_level = serializer.validated_data['target_level']

    ts.save()
    return Response(TeacherSkillSerializer(ts).data, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_skill_delete(request, teacher_skill_id):
    """Remove a skill assignment from a teacher."""
    ts = get_object_or_404(TeacherSkill, id=teacher_skill_id, tenant=request.tenant)
    ts.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_skill_bulk_update(request):
    """
    Bulk update teacher skill levels.

    Body:
    {
      "updates": [
        { "teacher_skill_id": "uuid", "current_level": 3, "target_level": 4 },
        ...
      ]
    }
    """
    serializer = BulkTeacherSkillUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    now = datetime.now(timezone.utc)
    updated_ids = []
    errors = []

    for item in serializer.validated_data['updates']:
        ts_id = item['teacher_skill_id']
        try:
            ts = TeacherSkill.objects.get(id=ts_id, tenant=request.tenant)
        except TeacherSkill.DoesNotExist:
            errors.append({"teacher_skill_id": str(ts_id), "error": "Not found"})
            continue

        if 'current_level' in item:
            ts.current_level = item['current_level']
            ts.last_assessed = now
        if 'target_level' in item:
            ts.target_level = item['target_level']
        ts.save()
        updated_ids.append(str(ts.id))

    return Response(
        {"updated": len(updated_ids), "errors": errors},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Gap Analysis
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def skill_gap_analysis(request):
    """
    Gap analysis: returns skills where teachers are below their target level,
    along with recommended courses that teach the needed skill.

    Query params:
      - teacher_id: filter to a specific teacher (optional)
      - category: filter by skill category (optional)
    """
    from django.db.models import F

    qs = TeacherSkill.objects.select_related('skill', 'teacher').filter(
        current_level__lt=F('target_level'),
    )

    teacher_id = request.GET.get("teacher_id")
    if teacher_id:
        qs = qs.filter(teacher_id=teacher_id)

    category = request.GET.get("category")
    if category:
        qs = qs.filter(skill__category__iexact=category)

    # Build gap analysis results
    results = []
    skill_ids = set()
    for ts in qs:
        skill_ids.add(ts.skill_id)

    # Prefetch course-skill mappings for relevant skills
    course_skill_map = {}
    if skill_ids:
        course_skills = (
            CourseSkill.objects.filter(
                skill_id__in=skill_ids,
                course__tenant=request.tenant,
                course__is_active=True,
            )
            .select_related('course', 'skill')
        )
        for cs in course_skills:
            course_skill_map.setdefault(cs.skill_id, []).append({
                "course_id": str(cs.course_id),
                "course_title": cs.course.title,
                "level_taught": cs.level_taught,
            })

    for ts in qs:
        recommended = course_skill_map.get(ts.skill_id, [])
        # Sort recommended courses by level_taught (prefer courses that
        # teach a level >= what the teacher needs to reach their target)
        recommended_sorted = sorted(
            recommended,
            key=lambda c: abs(c['level_taught'] - ts.target_level),
        )

        results.append({
            "teacher_id": str(ts.teacher_id),
            "teacher_name": ts.teacher.get_full_name() or ts.teacher.email,
            "teacher_email": ts.teacher.email,
            "skill_id": str(ts.skill_id),
            "skill_name": ts.skill.name,
            "skill_category": ts.skill.category,
            "current_level": ts.current_level,
            "target_level": ts.target_level,
            "gap_size": ts.gap_size,
            "recommended_courses": recommended_sorted,
        })

    # Sort results: largest gaps first, then by teacher name
    results.sort(key=lambda r: (-r['gap_size'], r['teacher_name']))

    return Response({"results": results, "total_gaps": len(results)}, status=status.HTTP_200_OK)
