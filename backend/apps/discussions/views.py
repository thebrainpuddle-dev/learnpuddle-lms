# apps/discussions/views.py
"""
Discussion forum API views.
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

from .models import DiscussionThread, DiscussionReply, DiscussionLike, DiscussionSubscription

logger = logging.getLogger(__name__)


class DiscussionPagination(PageNumberPagination):
    page_size = 20


def serialize_author(user):
    """Serialize user for display in discussions."""
    if not user:
        return {'name': 'Deleted User', 'avatar': None}
    return {
        'id': str(user.id),
        'name': f"{user.first_name} {user.last_name}".strip() or user.email,
        'role': user.role,
        'avatar': user.avatar.url if hasattr(user, 'avatar') and user.avatar else None,
    }


# ============================================================
# Thread Views
# ============================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@tenant_required
def thread_list_create(request):
    """
    GET: List discussion threads
    POST: Create a new thread
    
    Query params:
    - course_id: Filter by course
    - content_id: Filter by content
    - status: Filter by status (open/closed/archived)
    """
    if request.method == 'GET':
        threads = DiscussionThread.objects.filter(tenant=request.tenant)
        
        # Filters
        course_id = request.GET.get('course_id')
        content_id = request.GET.get('content_id')
        status_filter = request.GET.get('status', 'open')
        
        if course_id:
            threads = threads.filter(course_id=course_id)
        if content_id:
            threads = threads.filter(content_id=content_id)
        if status_filter:
            threads = threads.filter(status=status_filter)
        
        # Order: pinned first, then by activity
        threads = threads.select_related('author', 'last_reply_by', 'course', 'content')
        
        paginator = DiscussionPagination()
        page = paginator.paginate_queryset(threads, request)
        
        data = [{
            'id': str(t.id),
            'title': t.title,
            'body': t.body[:200] + '...' if len(t.body) > 200 else t.body,
            'author': serialize_author(t.author),
            'course_id': str(t.course_id) if t.course_id else None,
            'course_title': t.course.title if t.course else None,
            'content_id': str(t.content_id) if t.content_id else None,
            'status': t.status,
            'is_pinned': t.is_pinned,
            'is_announcement': t.is_announcement,
            'reply_count': t.reply_count,
            'view_count': t.view_count,
            'last_reply_at': t.last_reply_at.isoformat() if t.last_reply_at else None,
            'last_reply_by': serialize_author(t.last_reply_by) if t.last_reply_by else None,
            'created_at': t.created_at.isoformat(),
        } for t in page]
        
        return paginator.get_paginated_response(data)
    
    elif request.method == 'POST':
        title = request.data.get('title', '').strip()
        body = request.data.get('body', '').strip()
        course_id = request.data.get('course_id')
        content_id = request.data.get('content_id')
        
        if not title:
            return Response({'error': 'title is required'}, status=400)
        if not body:
            return Response({'error': 'body is required'}, status=400)
        
        # Validate course/content
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
            course=course,
            content=content,
            title=title,
            body=body,
            author=request.user,
        )
        
        # Auto-subscribe author
        DiscussionSubscription.objects.create(
            thread=thread,
            user=request.user,
        )
        
        logger.info(f"Discussion thread created: {thread.title}")
        
        return Response({
            'id': str(thread.id),
            'title': thread.title,
            'created_at': thread.created_at.isoformat(),
        }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@tenant_required
def thread_detail(request, thread_id):
    """
    GET: Get thread with replies
    PUT: Update thread (author or admin only)
    DELETE: Delete thread (admin only)
    """
    thread = get_object_or_404(
        DiscussionThread.objects.select_related('author', 'course', 'content'),
        id=thread_id,
        tenant=request.tenant
    )
    
    if request.method == 'GET':
        # Increment view count
        thread.increment_view()
        
        # Get replies (nested structure)
        replies = thread.replies.filter(is_hidden=False).select_related('author')
        
        # Build nested reply structure
        replies_data = []
        reply_map = {}
        
        for reply in replies:
            reply_data = {
                'id': str(reply.id),
                'body': reply.body,
                'author': serialize_author(reply.author),
                'is_edited': reply.is_edited,
                'like_count': reply.like_count,
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
        
        # Check if user is subscribed
        is_subscribed = DiscussionSubscription.objects.filter(
            thread=thread,
            user=request.user
        ).exists()
        
        return Response({
            'id': str(thread.id),
            'title': thread.title,
            'body': thread.body,
            'author': serialize_author(thread.author),
            'course_id': str(thread.course_id) if thread.course_id else None,
            'course_title': thread.course.title if thread.course else None,
            'content_id': str(thread.content_id) if thread.content_id else None,
            'status': thread.status,
            'is_pinned': thread.is_pinned,
            'is_announcement': thread.is_announcement,
            'reply_count': thread.reply_count,
            'view_count': thread.view_count,
            'is_subscribed': is_subscribed,
            'can_edit': thread.author_id == request.user.id or request.user.role == 'SCHOOL_ADMIN',
            'can_delete': request.user.role == 'SCHOOL_ADMIN',
            'replies': replies_data,
            'created_at': thread.created_at.isoformat(),
            'updated_at': thread.updated_at.isoformat(),
        })
    
    elif request.method == 'PUT':
        # Only author or admin can edit
        if thread.author_id != request.user.id and request.user.role != 'SCHOOL_ADMIN':
            return Response({'error': 'Permission denied'}, status=403)
        
        if 'title' in request.data:
            thread.title = request.data['title'].strip()
        if 'body' in request.data:
            thread.body = request.data['body'].strip()
        
        # Admin-only fields
        if request.user.role == 'SCHOOL_ADMIN':
            if 'status' in request.data:
                thread.status = request.data['status']
            if 'is_pinned' in request.data:
                thread.is_pinned = bool(request.data['is_pinned'])
            if 'is_announcement' in request.data:
                thread.is_announcement = bool(request.data['is_announcement'])
        
        thread.save()
        
        return Response({
            'id': str(thread.id),
            'title': thread.title,
            'status': thread.status,
        })
    
    elif request.method == 'DELETE':
        # Only admin can delete
        if request.user.role != 'SCHOOL_ADMIN':
            return Response({'error': 'Permission denied'}, status=403)
        
        thread.delete()
        return Response(status=204)


# ============================================================
# Reply Views
# ============================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@tenant_required
def reply_create(request, thread_id):
    """
    Create a reply to a thread.
    
    POST body:
    {
        "body": "Reply text",
        "parent_id": "uuid"  // Optional for nested reply
    }
    """
    thread = get_object_or_404(
        DiscussionThread,
        id=thread_id,
        tenant=request.tenant
    )
    
    if thread.status != 'open':
        return Response({'error': 'Thread is closed'}, status=400)
    
    body = request.data.get('body', '').strip()
    parent_id = request.data.get('parent_id')
    
    if not body:
        return Response({'error': 'body is required'}, status=400)
    
    parent = None
    if parent_id:
        parent = get_object_or_404(DiscussionReply, id=parent_id, thread=thread)
        
        # Limit nesting depth
        if parent.depth >= 3:
            return Response({'error': 'Maximum reply depth reached'}, status=400)
    
    reply = DiscussionReply.objects.create(
        thread=thread,
        parent=parent,
        body=body,
        author=request.user,
    )
    
    # Update thread stats
    thread.update_reply_stats()
    
    # Notify subscribers
    _notify_subscribers(thread, reply)
    
    return Response({
        'id': str(reply.id),
        'body': reply.body,
        'author': serialize_author(reply.author),
        'created_at': reply.created_at.isoformat(),
    }, status=201)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@tenant_required
def reply_detail(request, thread_id, reply_id):
    """
    PUT: Edit a reply
    DELETE: Delete a reply
    """
    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant)
    reply = get_object_or_404(DiscussionReply, id=reply_id, thread=thread)
    
    if request.method == 'PUT':
        # Only author can edit
        if reply.author_id != request.user.id:
            return Response({'error': 'Permission denied'}, status=403)
        
        body = request.data.get('body', '').strip()
        if not body:
            return Response({'error': 'body is required'}, status=400)
        
        reply.body = body
        reply.is_edited = True
        reply.edited_at = timezone.now()
        reply.save()
        
        return Response({
            'id': str(reply.id),
            'body': reply.body,
            'is_edited': reply.is_edited,
        })
    
    elif request.method == 'DELETE':
        # Author or admin can delete
        if reply.author_id != request.user.id and request.user.role != 'SCHOOL_ADMIN':
            return Response({'error': 'Permission denied'}, status=403)
        
        reply.delete()
        thread.update_reply_stats()
        
        return Response(status=204)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@tenant_required
def reply_like(request, thread_id, reply_id):
    """
    POST: Like a reply
    DELETE: Unlike a reply
    """
    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant)
    reply = get_object_or_404(DiscussionReply, id=reply_id, thread=thread)
    
    if request.method == 'POST':
        like, created = DiscussionLike.objects.get_or_create(
            reply=reply,
            user=request.user
        )
        
        if created:
            reply.like_count += 1
            reply.save(update_fields=['like_count'])
        
        return Response({'liked': True, 'like_count': reply.like_count})
    
    elif request.method == 'DELETE':
        deleted, _ = DiscussionLike.objects.filter(
            reply=reply,
            user=request.user
        ).delete()
        
        if deleted:
            reply.like_count = max(0, reply.like_count - 1)
            reply.save(update_fields=['like_count'])
        
        return Response({'liked': False, 'like_count': reply.like_count})


# ============================================================
# Subscription Views
# ============================================================

@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@tenant_required
def thread_subscribe(request, thread_id):
    """
    POST: Subscribe to thread notifications
    DELETE: Unsubscribe
    """
    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant)
    
    if request.method == 'POST':
        sub, created = DiscussionSubscription.objects.get_or_create(
            thread=thread,
            user=request.user
        )
        return Response({'subscribed': True})
    
    elif request.method == 'DELETE':
        DiscussionSubscription.objects.filter(
            thread=thread,
            user=request.user
        ).delete()
        return Response({'subscribed': False})


# ============================================================
# Admin Views
# ============================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reply_moderate(request, thread_id, reply_id):
    """
    Moderate (hide) a reply.
    
    POST body:
    {
        "action": "hide" | "unhide",
        "reason": "Reason for hiding"
    }
    """
    thread = get_object_or_404(DiscussionThread, id=thread_id, tenant=request.tenant)
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
    
    return Response({'error': 'Invalid action'}, status=400)


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
