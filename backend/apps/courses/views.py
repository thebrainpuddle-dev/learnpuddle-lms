# apps/courses/views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from utils.decorators import admin_only, tenant_required
from .models import Course, Module, Content
from .serializers import (
    CourseListSerializer, CourseDetailSerializer,
    ModuleSerializer, CreateModuleSerializer,
    ContentSerializer, CreateContentSerializer
)


class CoursePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_list_create(request):
    """
    GET: List all courses for current tenant
    POST: Create new course
    """
    if request.method == 'GET':
        # Get query parameters
        is_published = request.GET.get('is_published')
        is_mandatory = request.GET.get('is_mandatory')
        search = request.GET.get('search')
        
        # Base queryset (defense-in-depth: explicitly tenant-filter)
        courses = Course.objects.filter(tenant=request.tenant)
        
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
        serializer = CourseDetailSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        
        return Response(
            CourseDetailSerializer(course).data,
            status=status.HTTP_201_CREATED
        )


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
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
        serializer = CourseDetailSerializer(course)
        return Response(serializer.data)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        serializer = CourseDetailSerializer(
            course,
            data=request.data,
            partial=partial,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
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
        CourseDetailSerializer(course_copy).data,
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
