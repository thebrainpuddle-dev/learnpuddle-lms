# apps/courses/learning_path_views.py
"""
Learning Path API views.

Admin endpoints for managing learning paths.
Teacher endpoints for viewing and progressing through paths.
"""

import logging
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from utils.decorators import admin_only, tenant_required, teacher_or_admin

from .learning_path_models import LearningPath, LearningPathCourse, LearningPathProgress
from .models import Course

logger = logging.getLogger(__name__)


class LearningPathPagination(PageNumberPagination):
    page_size = 20


# ============================================================
# Admin Views
# ============================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def learning_path_list_create(request):
    """
    GET: List all learning paths for the tenant
    POST: Create a new learning path
    """
    if request.method == 'GET':
        paths = LearningPath.objects.filter(tenant=request.tenant, is_active=True)
        
        # Filters
        if request.GET.get('is_published'):
            is_published = request.GET.get('is_published') == 'true'
            paths = paths.filter(is_published=is_published)
        
        paginator = LearningPathPagination()
        page = paginator.paginate_queryset(paths, request)
        
        data = [{
            'id': str(p.id),
            'title': p.title,
            'description': p.description,
            'thumbnail': p.thumbnail.url if p.thumbnail else None,
            'is_published': p.is_published,
            'course_count': p.course_count,
            'estimated_hours': float(p.estimated_hours),
            'created_at': p.created_at.isoformat(),
        } for p in page]
        
        return paginator.get_paginated_response(data)
    
    elif request.method == 'POST':
        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        
        if not title:
            return Response({'error': 'title is required'}, status=400)
        
        path = LearningPath.objects.create(
            tenant=request.tenant,
            title=title,
            description=description,
            created_by=request.user,
        )
        
        return Response({
            'id': str(path.id),
            'title': path.title,
            'description': path.description,
            'is_published': path.is_published,
            'created_at': path.created_at.isoformat(),
        }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def learning_path_detail(request, path_id):
    """
    GET: Get learning path details with courses
    PUT: Update learning path
    DELETE: Soft delete learning path
    """
    path = get_object_or_404(LearningPath, id=path_id, tenant=request.tenant)
    
    if request.method == 'GET':
        # Get courses in order
        path_courses = path.path_courses.select_related('course').order_by('order')
        
        courses_data = [{
            'id': str(pc.id),
            'course_id': str(pc.course.id),
            'course_title': pc.course.title,
            'order': pc.order,
            'is_optional': pc.is_optional,
            'min_completion_percentage': pc.min_completion_percentage,
            'prerequisites': [str(p.id) for p in pc.prerequisites.all()],
            'estimated_hours': float(pc.course.estimated_hours),
        } for pc in path_courses]
        
        return Response({
            'id': str(path.id),
            'title': path.title,
            'description': path.description,
            'thumbnail': path.thumbnail.url if path.thumbnail else None,
            'is_published': path.is_published,
            'assigned_to_all': path.assigned_to_all,
            'course_count': path.course_count,
            'estimated_hours': float(path.estimated_hours),
            'courses': courses_data,
            'created_at': path.created_at.isoformat(),
            'updated_at': path.updated_at.isoformat(),
        })
    
    elif request.method == 'PUT':
        if 'title' in request.data:
            path.title = request.data['title'].strip()
        if 'description' in request.data:
            path.description = request.data['description'].strip()
        if 'is_published' in request.data:
            path.is_published = bool(request.data['is_published'])
        if 'assigned_to_all' in request.data:
            path.assigned_to_all = bool(request.data['assigned_to_all'])
        if 'estimated_hours' in request.data:
            path.estimated_hours = float(request.data['estimated_hours'])
        
        path.save()
        
        return Response({
            'id': str(path.id),
            'title': path.title,
            'is_published': path.is_published,
            'updated_at': path.updated_at.isoformat(),
        })
    
    elif request.method == 'DELETE':
        path.is_active = False
        path.save()
        return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def learning_path_add_course(request, path_id):
    """
    Add a course to a learning path.
    
    POST body:
    {
        "course_id": "uuid",
        "order": 1,  // Optional, defaults to end
        "is_optional": false,
        "prerequisites": ["path_course_id", ...]  // Optional
    }
    """
    path = get_object_or_404(LearningPath, id=path_id, tenant=request.tenant)
    
    course_id = request.data.get('course_id')
    if not course_id:
        return Response({'error': 'course_id is required'}, status=400)
    
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant)
    
    # Check if course already in path
    if path.path_courses.filter(course=course).exists():
        return Response({'error': 'Course already in this learning path'}, status=400)
    
    # Determine order
    order = request.data.get('order')
    if order is None:
        max_order = path.path_courses.order_by('-order').first()
        order = (max_order.order + 1) if max_order else 1
    
    path_course = LearningPathCourse.objects.create(
        learning_path=path,
        course=course,
        order=order,
        is_optional=request.data.get('is_optional', False),
        min_completion_percentage=request.data.get('min_completion_percentage', 100),
    )
    
    # Set prerequisites
    prerequisite_ids = request.data.get('prerequisites', [])
    if prerequisite_ids:
        prerequisites = LearningPathCourse.objects.filter(
            learning_path=path,
            id__in=prerequisite_ids
        )
        path_course.prerequisites.set(prerequisites)
    
    # Update path estimated hours
    path.estimated_hours = path.calculate_total_hours()
    path.save()
    
    return Response({
        'id': str(path_course.id),
        'course_id': str(course.id),
        'course_title': course.title,
        'order': path_course.order,
        'is_optional': path_course.is_optional,
    }, status=201)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def learning_path_course_detail(request, path_id, path_course_id):
    """
    PUT: Update a course in the learning path
    DELETE: Remove a course from the learning path
    """
    path = get_object_or_404(LearningPath, id=path_id, tenant=request.tenant)
    path_course = get_object_or_404(LearningPathCourse, id=path_course_id, learning_path=path)
    
    if request.method == 'PUT':
        if 'order' in request.data:
            path_course.order = int(request.data['order'])
        if 'is_optional' in request.data:
            path_course.is_optional = bool(request.data['is_optional'])
        if 'min_completion_percentage' in request.data:
            path_course.min_completion_percentage = int(request.data['min_completion_percentage'])
        if 'prerequisites' in request.data:
            prerequisites = LearningPathCourse.objects.filter(
                learning_path=path,
                id__in=request.data['prerequisites']
            )
            path_course.prerequisites.set(prerequisites)
        
        path_course.save()
        
        return Response({
            'id': str(path_course.id),
            'order': path_course.order,
            'is_optional': path_course.is_optional,
        })
    
    elif request.method == 'DELETE':
        path_course.delete()
        path.estimated_hours = path.calculate_total_hours()
        path.save()
        return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def learning_path_reorder(request, path_id):
    """
    Reorder courses in a learning path.
    
    POST body:
    {
        "course_order": [
            {"id": "path_course_id", "order": 1},
            {"id": "path_course_id", "order": 2},
            ...
        ]
    }
    """
    path = get_object_or_404(LearningPath, id=path_id, tenant=request.tenant)
    
    course_order = request.data.get('course_order', [])
    
    for item in course_order:
        LearningPathCourse.objects.filter(
            id=item['id'],
            learning_path=path
        ).update(order=item['order'])
    
    return Response({'success': True})


# ============================================================
# Teacher Views
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_learning_paths(request):
    """
    Get learning paths assigned to the current teacher.
    """
    user = request.user
    
    # Get assigned paths
    paths = LearningPath.objects.filter(
        tenant=request.tenant,
        is_active=True,
        is_published=True,
    ).filter(
        Q(assigned_to_all=True) |
        Q(assigned_teachers=user) |
        Q(assigned_groups__in=user.teacher_groups.all())
    ).distinct()
    
    # Get progress for each path
    data = []
    for path in paths:
        progress = LearningPathProgress.objects.filter(
            teacher=user,
            learning_path=path
        ).first()
        
        data.append({
            'id': str(path.id),
            'title': path.title,
            'description': path.description,
            'thumbnail': path.thumbnail.url if path.thumbnail else None,
            'course_count': path.course_count,
            'estimated_hours': float(path.estimated_hours),
            'progress': {
                'status': progress.status if progress else 'NOT_STARTED',
                'progress_percentage': float(progress.progress_percentage) if progress else 0,
                'courses_completed': progress.courses_completed if progress else 0,
            } if progress else None,
        })
    
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_learning_path_detail(request, path_id):
    """
    Get detailed view of a learning path with progress.
    """
    user = request.user
    
    path = get_object_or_404(
        LearningPath,
        id=path_id,
        tenant=request.tenant,
        is_active=True,
        is_published=True,
    )
    
    # Get or create progress record
    progress, _ = LearningPathProgress.objects.get_or_create(
        teacher=user,
        learning_path=path,
    )
    
    # Get course progress
    from apps.progress.models import TeacherProgress
    
    path_courses = path.path_courses.select_related('course').order_by('order')
    courses_data = []
    
    for pc in path_courses:
        # Get teacher's progress for this course
        course_progress = TeacherProgress.objects.filter(
            teacher=user,
            course=pc.course,
            content__isnull=True,
        ).first()
        
        # Check if prerequisites are met
        prerequisites_met = True
        if pc.prerequisites.exists():
            for prereq in pc.prerequisites.all():
                prereq_progress = TeacherProgress.objects.filter(
                    teacher=user,
                    course=prereq.course,
                    content__isnull=True,
                    status='COMPLETED',
                ).exists()
                if not prereq_progress:
                    prerequisites_met = False
                    break
        
        courses_data.append({
            'id': str(pc.id),
            'course_id': str(pc.course.id),
            'course_title': pc.course.title,
            'order': pc.order,
            'is_optional': pc.is_optional,
            'estimated_hours': float(pc.course.estimated_hours),
            'is_locked': not prerequisites_met,
            'prerequisites_met': prerequisites_met,
            'progress': {
                'status': course_progress.status if course_progress else 'NOT_STARTED',
                'progress_percentage': float(course_progress.progress_percentage) if course_progress else 0,
            },
        })
    
    # Recalculate overall progress
    progress.calculate_progress()
    progress.save()
    
    return Response({
        'id': str(path.id),
        'title': path.title,
        'description': path.description,
        'thumbnail': path.thumbnail.url if path.thumbnail else None,
        'course_count': path.course_count,
        'estimated_hours': float(path.estimated_hours),
        'courses': courses_data,
        'progress': {
            'status': progress.status,
            'progress_percentage': float(progress.progress_percentage),
            'courses_completed': progress.courses_completed,
            'started_at': progress.started_at.isoformat() if progress.started_at else None,
            'completed_at': progress.completed_at.isoformat() if progress.completed_at else None,
        },
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_start_learning_path(request, path_id):
    """
    Start a learning path (marks it as started and sets current course).
    """
    user = request.user
    
    path = get_object_or_404(
        LearningPath,
        id=path_id,
        tenant=request.tenant,
        is_active=True,
        is_published=True,
    )
    
    progress, created = LearningPathProgress.objects.get_or_create(
        teacher=user,
        learning_path=path,
    )
    
    if progress.status == 'NOT_STARTED':
        progress.status = 'IN_PROGRESS'
        progress.started_at = timezone.now()
        
        # Set first course as current
        first_course = path.path_courses.order_by('order').first()
        if first_course:
            progress.current_course = first_course
        
        progress.save()
    
    return Response({
        'success': True,
        'status': progress.status,
        'current_course_id': str(progress.current_course.course_id) if progress.current_course else None,
    })
