# apps/discussions/views.py
"""
Discussion forum API views.

Student discussions scoped by section.
Teachers monitor and participate in their assigned sections' discussions.
"""

import logging
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from utils.decorators import tenant_required, teacher_or_admin, student_only

from django.utils.html import strip_tags
from utils.rich_text import sanitize_rich_text_html
from .models import DiscussionThread, DiscussionReply, DiscussionLike, DiscussionSubscription

logger = logging.getLogger(__name__)


class DiscussionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def serialize_author(user):
    """Serialize user for display in discussions."""
    if not user:
        return {'id': None, 'name': 'Deleted User', 'role': None, 'avatar': None}
    return {
        'id': str(user.id),
        'name': f"{user.first_name} {user.last_name}".strip() or user.email,
        'role': user.role,
        'avatar': user.avatar.url if hasattr(user, 'avatar') and user.avatar else None,
    }


def serialize_thread_summary(thread):
    """Serialize a thread for list views."""
    return {
        'id': str(thread.id),
        'title': thread.title,
        'body': thread.body[:200] + '...' if len(thread.body) > 200 else thread.body,
        'author': serialize_author(thread.author),
        'section_id': str(thread.section_id),
        'section_name': thread.section.name if hasattr(thread, '_section_cache') or thread.section_id else None,
        'grade_name': None,
        'course_id': str(thread.course_id) if thread.course_id else None,
        'course_title': thread.course.title if thread.course else None,
        'content_id': str(thread.content_id) if thread.content_id else None,
        'content_title': thread.content.title if thread.content else None,
        'status': thread.status,
        'is_pinned': thread.is_pinned,
        'is_announcement': thread.is_announcement,
        'reply_count': thread.reply_count,
        'view_count': thread.view_count,
        'last_reply_at': thread.last_reply_at.isoformat() if thread.last_reply_at else None,
        'last_reply_by': serialize_author(thread.last_reply_by) if thread.last_reply_by else None,
        'created_at': thread.created_at.isoformat(),
    }


def serialize_thread_detail(thread, user):
    """Serialize a thread with full replies for detail view."""
    replies = thread.replies.filter(is_hidden=False).select_related('author')

    # Build nested reply structure
    replies_data = []
    reply_map = {}
    liked_ids = set(
        DiscussionLike.objects.filter(
            reply__thread=thread, user=user
        ).values_list('reply_id', flat=True)
    )

    for reply in replies:
        reply_data = {
            'id': str(reply.id),
            'body': reply.body,
            'author': serialize_author(reply.author),
            'is_edited': reply.is_edited,
            'like_count': reply.like_count,
            'is_liked': reply.id in liked_ids,
            'parent_id': str(reply.parent_id) if reply.parent_id else None,
            'depth': reply.depth,
            'created_at': reply.created_at.isoformat(),
            'children': [],
        }
        reply_map[str(reply.id)] = reply_data

        if reply.parent_id:
            parent_data = reply_map.get(str(reply.parent_id))
            if parent_data:
                parent_data['children'].append(reply_data)
        else:
            replies_data.append(reply_data)

    is_subscribed = DiscussionSubscription.objects.filter(
        thread=thread, user=user
    ).exists()

    is_teacher = user.role in ('TEACHER', 'SCHOOL_ADMIN', 'SUPER_ADMIN', 'HOD', 'IB_COORDINATOR')

    return {
        'id': str(thread.id),
        'title': thread.title,
        'body': thread.body,
        'author': serialize_author(thread.author),
        'section_id': str(thread.section_id),
        'section_name': thread.section.name if thread.section else None,
        'grade_name': thread.section.grade.name if thread.section and thread.section.grade else None,
        'course_id': str(thread.course_id) if thread.course_id else None,
        'course_title': thread.course.title if thread.course else None,
        'content_id': str(thread.content_id) if thread.content_id else None,
        'content_title': thread.content.title if thread.content else None,
        'status': thread.status,
        'is_pinned': thread.is_pinned,
        'is_announcement': thread.is_announcement,
        'reply_count': thread.reply_count,
        'view_count': thread.view_count,
        'is_subscribed': is_subscribed,
        'can_edit': thread.author_id == user.id or is_teacher,
        'can_delete': is_teacher,
        'can_moderate': is_teacher,
        'replies': replies_data,
        'created_at': thread.created_at.isoformat(),
        'updated_at': thread.updated_at.isoformat(),
    }


def _get_teacher_section_ids(user, tenant):
    """Get section IDs for a teacher's assigned sections."""
    from apps.academics.models import TeachingAssignment
    return list(
        TeachingAssignment.objects.filter(
            tenant=tenant, teacher=user
        ).values_list('sections__id', flat=True).distinct()
    )


# ============================================================
# Student Views
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@student_only
@tenant_required
def student_thread_list(request):
    """
    List discussion threads for the student's section.

    Query params:
    - content_id: Filter by content
    - course_id: Filter by course
    - status: open/closed/archived (default: open)
    """
    section = request.user.section_fk
    if not section:
        return Response({'error': 'You are not assigned to a section'}, status=400)

    threads = DiscussionThread.objects.filter(
        tenant=request.tenant,
        section=section,
    ).select_related('author', 'last_reply_by', 'course', 'content', 'section', 'section__grade')

    content_id = request.GET.get('content_id')
    course_id = request.GET.get('course_id')
    status_filter = request.GET.get('status', 'open')

    if content_id:
        threads = threads.filter(content_id=content_id)
    if course_id:
        threads = threads.filter(course_id=course_id)
    if status_filter:
        threads = threads.filter(status=status_filter)

    paginator = DiscussionPagination()
    page = paginator.paginate_queryset(threads, request)
    data = [serialize_thread_summary(t) for t in page]
    return paginator.get_paginated_response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@student_only
@tenant_required
def student_thread_create(request):
    """
    Create a discussion thread in the student's section.

    POST body:
    {
        "title": "...",
        "body": "...",
        "content_id": "uuid",  // optional
        "course_id": "uuid"    // optional
    }
    """
    section = request.user.section_fk
    if not section:
        return Response({'error': 'You are not assigned to a section'}, status=400)

    title = strip_tags(request.data.get('title', '')).strip()
    body = sanitize_rich_text_html(request.data.get('body', '').strip())
    content_id = request.data.get('content_id')
    course_id = request.data.get('course_id')

    if not title:
        return Response({'error': 'title is required'}, status=400)
    if not body:
        return Response({'error': 'body is required'}, status=400)

    course = None
    content = None

    if course_id:
        from apps.courses.models import Course
        course = get_object_or_404(Course, id=course_id, tenant=request.tenant)

    if content_id:
        from apps.courses.models import Content
        content = get_object_or_404(
            Content.all_objects,
            id=content_id,
            module__course__tenant=request.tenant
        )
        if not course:
            course = content.module.course

    thread = DiscussionThread.objects.create(
        tenant=request.tenant,
        section=section,
        course=course,
        content=content,
        title=title,
        body=body,
        author=request.user,
    )

    # Auto-subscribe author
    DiscussionSubscription.objects.create(thread=thread, user=request.user)

    return Response({
        'id': str(thread.id),
        'title': thread.title,
        'created_at': thread.created_at.isoformat(),
    }, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@student_only
@tenant_required
def student_thread_detail(request, thread_id):
    """Get thread detail — student must be in the thread's section."""
    section = request.user.section_fk
    if not section:
        return Response({'error': 'You are not assigned to a section'}, status=400)

    thread = get_object_or_404(
        DiscussionThread.objects.select_related(
            'author', 'course', 'content', 'section', 'section__grade'
        ),
        id=thread_id,
        tenant=request.tenant,
        section=section,
    )
    thread.increment_view()
    return Response(serialize_thread_detail(thread, request.user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@student_only
@tenant_required
def student_reply_create(request, thread_id):
    """Create a reply — student must be in the thread's section."""
    section = request.user.section_fk
    if not section:
        return Response({'error': 'You are not assigned to a section'}, status=400)

    thread = get_object_or_404(
        DiscussionThread,
        id=thread_id,
        tenant=request.tenant,
        section=section,
    )

    if thread.status != 'open':
        return Response({'error': 'Thread is closed'}, status=400)

    body = sanitize_rich_text_html(request.data.get('body', '').strip())
    parent_id = request.data.get('parent_id')

    if not body:
        return Response({'error': 'body is required'}, status=400)

    parent = None
    if parent_id:
        parent = get_object_or_404(DiscussionReply, id=parent_id, thread=thread)
        if parent.depth >= 3:
            return Response({'error': 'Maximum reply depth reached'}, status=400)

    reply = DiscussionReply.objects.create(
        thread=thread,
        parent=parent,
        body=body,
        author=request.user,
    )
    thread.update_reply_stats()
    _notify_subscribers(thread, reply)

    return Response({
        'id': str(reply.id),
        'body': reply.body,
        'author': serialize_author(reply.author),
        'created_at': reply.created_at.isoformat(),
    }, status=201)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@student_only
@tenant_required
def student_reply_detail(request, thread_id, reply_id):
    """Edit/delete own reply — student must be in the thread's section."""
    section = request.user.section_fk
    if not section:
        return Response({'error': 'You are not assigned to a section'}, status=400)

    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant, section=section)
    reply = get_object_or_404(DiscussionReply, id=reply_id, thread=thread)

    if reply.author_id != request.user.id:
        return Response({'error': 'Permission denied'}, status=403)

    if request.method == 'PUT':
        body = sanitize_rich_text_html(request.data.get('body', '').strip())
        if not body:
            return Response({'error': 'body is required'}, status=400)
        reply.body = body
        reply.is_edited = True
        reply.edited_at = timezone.now()
        reply.save()
        return Response({'id': str(reply.id), 'body': reply.body, 'is_edited': True})

    elif request.method == 'DELETE':
        reply.delete()
        thread.update_reply_stats()
        return Response(status=204)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@student_only
@tenant_required
def student_reply_like(request, thread_id, reply_id):
    """Like/unlike a reply — student must be in the thread's section."""
    section = request.user.section_fk
    if not section:
        return Response({'error': 'You are not assigned to a section'}, status=400)

    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant, section=section)
    reply = get_object_or_404(DiscussionReply, id=reply_id, thread=thread)

    if request.method == 'POST':
        _, created = DiscussionLike.objects.get_or_create(reply=reply, user=request.user)
        if created:
            reply.like_count += 1
            reply.save(update_fields=['like_count'])
        return Response({'liked': True, 'like_count': reply.like_count})

    elif request.method == 'DELETE':
        deleted, _ = DiscussionLike.objects.filter(reply=reply, user=request.user).delete()
        if deleted:
            reply.like_count = max(0, reply.like_count - 1)
            reply.save(update_fields=['like_count'])
        return Response({'liked': False, 'like_count': reply.like_count})


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@student_only
@tenant_required
def student_thread_subscribe(request, thread_id):
    """Subscribe/unsubscribe to thread notifications."""
    section = request.user.section_fk
    if not section:
        return Response({'error': 'You are not assigned to a section'}, status=400)

    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant, section=section)

    if request.method == 'POST':
        DiscussionSubscription.objects.get_or_create(thread=thread, user=request.user)
        return Response({'subscribed': True})
    elif request.method == 'DELETE':
        DiscussionSubscription.objects.filter(thread=thread, user=request.user).delete()
        return Response({'subscribed': False})


# ============================================================
# Teacher Views
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_thread_list(request):
    """
    List discussion threads across teacher's assigned sections.

    Query params:
    - section_id: Filter by specific section
    - course_id: Filter by course
    - content_id: Filter by content
    - status: open/closed/archived (default: all)
    - student_id: Filter by student author
    """
    section_ids = _get_teacher_section_ids(request.user, request.tenant)

    # Admin can see all sections
    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        from apps.academics.models import Section
        section_ids = list(Section.objects.filter(tenant=request.tenant).values_list('id', flat=True))

    if not section_ids:
        return Response({'results': [], 'count': 0, 'next': None, 'previous': None})

    threads = DiscussionThread.objects.filter(
        tenant=request.tenant,
        section_id__in=section_ids,
    ).select_related('author', 'last_reply_by', 'course', 'content', 'section', 'section__grade')

    # Filters
    section_id = request.GET.get('section_id')
    course_id = request.GET.get('course_id')
    content_id = request.GET.get('content_id')
    status_filter = request.GET.get('status')
    student_id = request.GET.get('student_id')

    if section_id:
        threads = threads.filter(section_id=section_id)
    if course_id:
        threads = threads.filter(course_id=course_id)
    if content_id:
        threads = threads.filter(content_id=content_id)
    if status_filter:
        threads = threads.filter(status=status_filter)
    if student_id:
        threads = threads.filter(author_id=student_id)

    # Enrich with section/grade info for serialization
    data_list = []
    paginator = DiscussionPagination()
    page = paginator.paginate_queryset(threads, request)

    for t in page:
        item = serialize_thread_summary(t)
        # Enrich section/grade from select_related
        item['section_name'] = t.section.name if t.section else None
        item['grade_name'] = t.section.grade.name if t.section and t.section.grade else None
        data_list.append(item)

    return paginator.get_paginated_response(data_list)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_thread_detail(request, thread_id):
    """Get thread detail — teacher must be assigned to the thread's section."""
    section_ids = _get_teacher_section_ids(request.user, request.tenant)

    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        from apps.academics.models import Section
        section_ids = list(Section.objects.filter(tenant=request.tenant).values_list('id', flat=True))

    thread = get_object_or_404(
        DiscussionThread.objects.select_related(
            'author', 'course', 'content', 'section', 'section__grade'
        ),
        id=thread_id,
        tenant=request.tenant,
        section_id__in=section_ids,
    )
    thread.increment_view()
    return Response(serialize_thread_detail(thread, request.user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_reply_create(request, thread_id):
    """Teacher replies to a thread in their assigned section."""
    section_ids = _get_teacher_section_ids(request.user, request.tenant)
    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        from apps.academics.models import Section
        section_ids = list(Section.objects.filter(tenant=request.tenant).values_list('id', flat=True))

    thread = get_object_or_404(
        DiscussionThread,
        id=thread_id,
        tenant=request.tenant,
        section_id__in=section_ids,
    )

    if thread.status != 'open':
        return Response({'error': 'Thread is closed'}, status=400)

    body = sanitize_rich_text_html(request.data.get('body', '').strip())
    parent_id = request.data.get('parent_id')

    if not body:
        return Response({'error': 'body is required'}, status=400)

    parent = None
    if parent_id:
        parent = get_object_or_404(DiscussionReply, id=parent_id, thread=thread)
        if parent.depth >= 3:
            return Response({'error': 'Maximum reply depth reached'}, status=400)

    reply = DiscussionReply.objects.create(
        thread=thread,
        parent=parent,
        body=body,
        author=request.user,
    )
    thread.update_reply_stats()
    _notify_subscribers(thread, reply)

    return Response({
        'id': str(reply.id),
        'body': reply.body,
        'author': serialize_author(reply.author),
        'created_at': reply.created_at.isoformat(),
    }, status=201)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_thread_moderate(request, thread_id):
    """
    Moderate a thread — close, pin, announce.

    PATCH body:
    {
        "status": "open" | "closed" | "archived",
        "is_pinned": true/false,
        "is_announcement": true/false
    }
    """
    section_ids = _get_teacher_section_ids(request.user, request.tenant)
    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        from apps.academics.models import Section
        section_ids = list(Section.objects.filter(tenant=request.tenant).values_list('id', flat=True))

    thread = get_object_or_404(
        DiscussionThread,
        id=thread_id,
        tenant=request.tenant,
        section_id__in=section_ids,
    )

    if 'status' in request.data:
        thread.status = request.data['status']
    if 'is_pinned' in request.data:
        thread.is_pinned = bool(request.data['is_pinned'])
    if 'is_announcement' in request.data:
        thread.is_announcement = bool(request.data['is_announcement'])

    thread.save()

    return Response({
        'id': str(thread.id),
        'status': thread.status,
        'is_pinned': thread.is_pinned,
        'is_announcement': thread.is_announcement,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_reply_moderate(request, thread_id, reply_id):
    """
    Hide/unhide a reply.

    POST body: { "action": "hide" | "unhide", "reason": "..." }
    """
    section_ids = _get_teacher_section_ids(request.user, request.tenant)
    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        from apps.academics.models import Section
        section_ids = list(Section.objects.filter(tenant=request.tenant).values_list('id', flat=True))

    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant, section_id__in=section_ids)
    reply = get_object_or_404(DiscussionReply, id=reply_id, thread=thread)

    action = request.data.get('action')

    if action == 'hide':
        reply.is_hidden = True
        reply.hidden_reason = request.data.get('reason', '')
        reply.hidden_by = request.user
        reply.save()
        return Response({'hidden': True})
    elif action == 'unhide':
        reply.is_hidden = False
        reply.hidden_reason = ''
        reply.hidden_by = None
        reply.save()
        return Response({'hidden': False})

    return Response({'error': 'Invalid action. Use "hide" or "unhide".'}, status=400)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_reply_like(request, thread_id, reply_id):
    """Teacher like/unlike a reply."""
    section_ids = _get_teacher_section_ids(request.user, request.tenant)
    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        from apps.academics.models import Section
        section_ids = list(Section.objects.filter(tenant=request.tenant).values_list('id', flat=True))

    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant, section_id__in=section_ids)
    reply = get_object_or_404(DiscussionReply, id=reply_id, thread=thread)

    if request.method == 'POST':
        _, created = DiscussionLike.objects.get_or_create(reply=reply, user=request.user)
        if created:
            reply.like_count += 1
            reply.save(update_fields=['like_count'])
        return Response({'liked': True, 'like_count': reply.like_count})
    elif request.method == 'DELETE':
        deleted, _ = DiscussionLike.objects.filter(reply=reply, user=request.user).delete()
        if deleted:
            reply.like_count = max(0, reply.like_count - 1)
            reply.save(update_fields=['like_count'])
        return Response({'liked': False, 'like_count': reply.like_count})


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_thread_subscribe(request, thread_id):
    """Teacher subscribe/unsubscribe to a thread."""
    section_ids = _get_teacher_section_ids(request.user, request.tenant)
    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        from apps.academics.models import Section
        section_ids = list(Section.objects.filter(tenant=request.tenant).values_list('id', flat=True))

    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant, section_id__in=section_ids)

    if request.method == 'POST':
        DiscussionSubscription.objects.get_or_create(thread=thread, user=request.user)
        return Response({'subscribed': True})
    elif request.method == 'DELETE':
        DiscussionSubscription.objects.filter(thread=thread, user=request.user).delete()
        return Response({'subscribed': False})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_sections_list(request):
    """List the teacher's assigned sections (for filter dropdowns)."""
    from apps.academics.models import Section, TeachingAssignment

    if request.user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        sections = Section.objects.filter(tenant=request.tenant).select_related('grade')
    else:
        section_ids = TeachingAssignment.objects.filter(
            tenant=request.tenant, teacher=request.user
        ).values_list('sections__id', flat=True).distinct()
        sections = Section.objects.filter(id__in=section_ids).select_related('grade')

    data = [{
        'id': str(s.id),
        'name': s.name,
        'grade_name': s.grade.name if s.grade else None,
        'display_name': f"{s.grade.name} - {s.name}" if s.grade else s.name,
    } for s in sections]

    return Response(data)


# ============================================================
# Helper Functions
# ============================================================

def _notify_subscribers(thread: DiscussionThread, reply: DiscussionReply):
    """Send notifications to thread subscribers."""
    from apps.notifications.services import create_notification

    subscribers = DiscussionSubscription.objects.filter(
        thread=thread,
        notify_on_reply=True
    ).exclude(user=reply.author).select_related('user')

    for sub in subscribers:
        try:
            create_notification(
                tenant=thread.tenant,
                teacher=sub.user,
                notification_type='DISCUSSION_REPLY',
                title=f"New reply in: {thread.title}",
                message=f"{reply.author.first_name} replied to a discussion you're following.",
                course=thread.course,
            )
        except Exception as e:
            logger.warning(f"Failed to notify subscriber: {e}")
