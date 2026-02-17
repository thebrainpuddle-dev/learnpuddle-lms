# apps/courses/views.py

import logging
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from utils.decorators import admin_only, tenant_required, teacher_or_admin
from utils.audit import log_audit
from .models import Course, Module, Content
from .serializers import (
    CourseListSerializer, CourseDetailSerializer,
    ModuleSerializer, CreateModuleSerializer,
    ContentSerializer, CreateContentSerializer
)

# region agent log
_debug_log = logging.getLogger('debug.course_views')
# endregion


class CoursePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


def _normalize_multipart_list_fields(data, list_fields=None):
    """
    Convert QueryDict to a plain dict suitable for DRF serializer validation.
    
    QueryDict stores all values as lists internally. dict(QueryDict) exposes those
    raw lists, breaking CharField/BooleanField/etc validation. QueryDict.dict()
    returns {key: last_value} which is what serializers expect for scalar fields.
    For list fields (assigned_groups, assigned_teachers), we use getlist() to
    preserve multiple values.
    """
    list_fields = list_fields or ('assigned_groups', 'assigned_teachers')
    if hasattr(data, 'dict'):
        result = data.dict()
        for key in list_fields:
            vals = data.getlist(key)
            if vals:
                result[key] = vals
        return result
    return data


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@admin_only
@tenant_required
def course_list_create(request):
    """
    GET: List all courses for current tenant
    POST: Create new course (supports multipart/form-data for thumbnail upload)
    """
    if request.method == 'GET':
        # Get query parameters
        is_published = request.GET.get('is_published')
        is_mandatory = request.GET.get('is_mandatory')
        search = request.GET.get('search')

        # region agent log
        from utils.tenant_middleware import get_current_tenant
        thread_tenant = get_current_tenant()
        _debug_log.warning(
            '[DBG-CV] GET courses: user=%s role=%s req_tenant=%s(%s) thread_tenant=%s(%s)',
            request.user.email, request.user.role,
            getattr(request, 'tenant', None), getattr(getattr(request, 'tenant', None), 'id', None),
            thread_tenant, getattr(thread_tenant, 'id', None),
        )
        # Check raw DB state
        from django.db import connection
        with connection.cursor() as cur:
            tenant_id = str(request.tenant.id)
            cur.execute("SELECT count(*) FROM courses WHERE tenant_id = %s", [tenant_id])
            total_in_db = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM courses WHERE tenant_id = %s AND is_deleted = false", [tenant_id])
            alive_in_db = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM courses WHERE tenant_id = %s AND is_deleted = false AND is_active = true", [tenant_id])
            active_alive_in_db = cur.fetchone()[0]
        _debug_log.warning(
            '[DBG-CV] raw DB: total=%d alive=%d active_alive=%d for tenant=%s',
            total_in_db, alive_in_db, active_alive_in_db, tenant_id,
        )
        # endregion
        
        # Base queryset with optimized related queries (defense-in-depth: explicitly tenant-filter)
        courses = Course.objects.filter(tenant=request.tenant).select_related(
            'tenant', 'created_by'
        ).prefetch_related(
            'modules',
            'assigned_teachers',
            'assigned_groups',
        )

        # region agent log
        _debug_log.warning('[DBG-CV] ORM queryset count=%d sql=%s', courses.count(), str(courses.query)[:500])
        # endregion
        
        # Additional filters
        if is_published is not None:
            courses = courses.filter(is_published=is_published == 'true')
        if is_mandatory is not None:
            courses = courses.filter(is_mandatory=is_mandatory == 'true')
        if search:
            courses = courses.filter(title__icontains=search)
        
        # Order by created date
        courses = courses.order_by('-created_at')
        
        # Paginate
        paginator = CoursePagination()
        page = paginator.paginate_queryset(courses, request)
        
        serializer = CourseListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)
    
    elif request.method == 'POST':
        data = _normalize_multipart_list_fields(request.data)
        # region agent log
        _debug_log.warning('[DBG-CV] POST course: content_type=%s data_type=%s data_keys=%s',
            request.content_type, type(request.data).__name__, list(request.data.keys()) if hasattr(request.data, 'keys') else 'N/A')
        _debug_log.warning('[DBG-CV] POST normalized_data=%s', {k: (type(v).__name__ if hasattr(v, 'read') else repr(v)[:200]) for k, v in (data.items() if hasattr(data, 'items') else [])})
        # endregion
        serializer = CourseDetailSerializer(
            data=data,
            context={'request': request}
        )
        if not serializer.is_valid():
            # region agent log
            _debug_log.warning('[DBG-CV] POST validation_errors=%s', serializer.errors)
            # endregion
        serializer.is_valid(raise_exception=True)
        course = serializer.save()

        log_audit('CREATE', 'Course', target_id=str(course.id), target_repr=str(course), request=request)

        return Response(
            CourseDetailSerializer(course, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@admin_only
@tenant_required
def course_detail(request, course_id):
    """
    GET: Retrieve course details
    PUT/PATCH: Update course
    DELETE: Delete course
    """
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant)
    
    if request.method == 'GET':
        serializer = CourseDetailSerializer(course, context={'request': request})
        return Response(serializer.data)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        data = _normalize_multipart_list_fields(request.data)
        serializer = CourseDetailSerializer(
            course,
            data=data,
            partial=partial,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
        log_audit('DELETE', 'Course', target_id=str(course.id), target_repr=str(course), request=request)
        course.delete()
        return Response(
            {'message': 'Course deleted successfully'},
            status=status.HTTP_204_NO_CONTENT
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_publish(request, course_id):
    """
    Publish or unpublish a course.
    """
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant)
    
    action = request.data.get('action')  # 'publish' or 'unpublish'
    
    if action == 'publish':
        course.is_published = True
        message = 'Course published successfully'
    elif action == 'unpublish':
        course.is_published = False
        message = 'Course unpublished successfully'
    else:
        return Response(
            {'error': 'Invalid action. Use "publish" or "unpublish"'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    course.save()

    audit_action = 'PUBLISH' if action == 'publish' else 'UNPUBLISH'
    log_audit(audit_action, 'Course', target_id=str(course.id), target_repr=str(course), request=request)

    return Response({
        'message': message,
        'is_published': course.is_published
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_duplicate(request, course_id):
    """
    Duplicate an existing course.
    """
    original_course = get_object_or_404(Course, id=course_id, tenant=request.tenant)
    
    # Create copy
    course_copy = Course.objects.create(
        tenant=original_course.tenant,
        title=f"{original_course.title} (Copy)",
        description=original_course.description,
        is_mandatory=original_course.is_mandatory,
        deadline=original_course.deadline,
        estimated_hours=original_course.estimated_hours,
        is_published=False,  # Unpublished by default
        created_by=request.user
    )
    
    # Copy modules and content
    for module in original_course.modules.all():
        module_copy = Module.objects.create(
            course=course_copy,
            title=module.title,
            description=module.description,
            order=module.order
        )
        
        for content in module.contents.all():
            Content.objects.create(
                module=module_copy,
                title=content.title,
                content_type=content.content_type,
                order=content.order,
                file_url=content.file_url,
                file_size=content.file_size,
                duration=content.duration,
                text_content=content.text_content,
                is_mandatory=content.is_mandatory
            )
    
    return Response(
        CourseDetailSerializer(course_copy, context={'request': request}).data,
        status=status.HTTP_201_CREATED
    )


# Module endpoints
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def module_list_create(request, course_id):
    """
    GET: List modules for a course
    POST: Create new module
    """
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant)
    
    if request.method == 'GET':
        modules = course.modules.all().order_by('order')
        serializer = ModuleSerializer(modules, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = CreateModuleSerializer(
            data=request.data,
            context={'course_id': course_id}
        )
        serializer.is_valid(raise_exception=True)
        module = serializer.save()
        
        return Response(
            ModuleSerializer(module).data,
            status=status.HTTP_201_CREATED
        )


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def module_detail(request, course_id, module_id):
    """
    GET/PUT/DELETE specific module
    """
    module = get_object_or_404(
        Module,
        id=module_id,
        course_id=course_id,
        course__tenant=request.tenant,
    )
    
    if request.method == 'GET':
        serializer = ModuleSerializer(module)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = ModuleSerializer(module, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
        module.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Content endpoints
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@admin_only
@tenant_required
def content_list_create(request, course_id, module_id):
    """
    GET: List content for a module
    POST: Create new content
    """
    module = get_object_or_404(
        Module,
        id=module_id,
        course_id=course_id,
        course__tenant=request.tenant,
    )
    
    if request.method == 'GET':
        contents = module.contents.all().order_by('order')
        serializer = ContentSerializer(contents, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = CreateContentSerializer(
            data=request.data,
            context={'module_id': module_id}
        )
        serializer.is_valid(raise_exception=True)
        content = serializer.save()
        
        return Response(
            ContentSerializer(content).data,
            status=status.HTTP_201_CREATED
        )


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def content_detail(request, course_id, module_id, content_id):
    """
    GET/PUT/DELETE specific content
    """
    content = get_object_or_404(
        Content,
        id=content_id,
        module_id=module_id,
        module__course_id=course_id,
        module__course__tenant=request.tenant,
    )
    
    if request.method == 'GET':
        serializer = ContentSerializer(content)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = ContentSerializer(content, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
        content.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def courses_bulk_action(request):
    """
    Perform bulk actions on courses.
    
    POST body:
    {
        "action": "publish" | "unpublish" | "delete",
        "course_ids": ["uuid", ...]
    }
    """
    action = (request.data.get('action') or '').lower()
    course_ids = request.data.get('course_ids', [])
    
    valid_actions = ['publish', 'unpublish', 'delete']
    if action not in valid_actions:
        return Response(
            {'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not course_ids or not isinstance(course_ids, list):
        return Response(
            {'error': 'course_ids must be a non-empty list'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    MAX_BULK_IDS = 100
    if len(course_ids) > MAX_BULK_IDS:
        return Response(
            {'error': f'Too many IDs. Maximum {MAX_BULK_IDS} per request.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get courses within tenant
    courses = Course.objects.filter(
        id__in=course_ids,
        tenant=request.tenant,
    )
    
    found_count = courses.count()
    if found_count == 0:
        return Response(
            {'error': 'No valid courses found with the provided IDs'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    affected_count = 0
    
    if action == 'publish':
        affected_count = courses.filter(is_published=False).update(is_published=True)
        action_display = 'published'
    elif action == 'unpublish':
        affected_count = courses.filter(is_published=True).update(is_published=False)
        action_display = 'unpublished'
    elif action == 'delete':
        # Proper soft delete - mark as deleted with timestamp
        from django.utils import timezone
        affected_count = courses.filter(is_deleted=False).update(
            is_deleted=True,
            deleted_at=timezone.now(),
            is_active=False,
        )
        action_display = 'deleted'
    
    log_audit(
        'BULK_ACTION',
        'Course',
        target_repr=f"Bulk {action}: {affected_count} courses",
        changes={'action': action, 'course_ids': course_ids, 'affected': affected_count},
        request=request
    )
    
    return Response({
        'message': f'Successfully {action_display} {affected_count} course(s)',
        'affected_count': affected_count,
        'requested_count': len(course_ids),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def global_search(request):
    """
    Global search across courses and content.
    
    Query params:
        q: Search query (required, min 2 chars)
        limit: Max results per category (default 10)
    
    Uses PostgreSQL full-text search with SearchVector/SearchRank for relevance ordering.
    Falls back to icontains for short queries or when search_vector is not populated.
    """
    query = (request.GET.get('q') or '').strip()
    
    if len(query) < 2:
        return Response({
            'courses': [],
            'content': [],
            'query': query,
        })
    
    try:
        limit = min(20, max(1, int(request.GET.get('limit', 10))))
    except (ValueError, TypeError):
        limit = 10
    
    tenant = request.tenant
    user = request.user
    
    # Determine which courses the user can access
    if user.role in ['SCHOOL_ADMIN', 'SUPER_ADMIN']:
        # Admins can see all courses
        course_base_qs = Course.objects.filter(tenant=tenant, is_active=True)
    else:
        # Teachers can only see published courses they're assigned to
        course_base_qs = Course.objects.filter(
            tenant=tenant,
            is_active=True,
            is_published=True,
        ).filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=user)
            | Q(assigned_groups__in=user.teacher_groups.all())
        ).distinct()
    
    # Try full-text search first
    search_query = SearchQuery(query)
    
    # Search courses using SearchVector if available
    courses_with_vector = course_base_qs.filter(search_vector__isnull=False)
    if courses_with_vector.exists():
        # Use full-text search with ranking
        courses_result = courses_with_vector.annotate(
            rank=SearchRank('search_vector', search_query)
        ).filter(
            search_vector=search_query
        ).order_by('-rank')[:limit]
        
        # Fall back to icontains if no results
        if not courses_result.exists():
            courses_result = course_base_qs.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )[:limit]
    else:
        # No search vectors populated, use icontains
        courses_result = course_base_qs.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )[:limit]
    
    # Search content (titles only for performance)
    content_result = Content.objects.filter(
        module__course__in=course_base_qs,
        is_active=True,
    ).filter(
        Q(title__icontains=query) | Q(content_type__icontains=query)
    ).select_related('module', 'module__course')[:limit]
    
    return Response({
        'query': query,
        'courses': [
            {
                'id': str(c.id),
                'title': c.title,
                'description': c.description[:200] + '...' if len(c.description) > 200 else c.description,
                'type': 'course',
                'is_published': c.is_published,
            }
            for c in courses_result
        ],
        'content': [
            {
                'id': str(c.id),
                'title': c.title,
                'content_type': c.content_type,
                'course_id': str(c.module.course_id),
                'course_title': c.module.course.title,
                'module_title': c.module.title,
                'type': 'content',
            }
            for c in content_result
        ],
    })
