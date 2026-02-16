from django.db import models
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.users.models import User
from apps.courses.models import TeacherGroup
from utils.decorators import teacher_or_admin, admin_only, tenant_required
from utils.audit import log_audit
from .models import Notification
from .serializers import NotificationSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def notification_list(request):
    """
    List notifications for the current teacher.
    Query params:
      - unread_only: true/false (default false)
      - type: REMINDER|COURSE_ASSIGNED|ASSIGNMENT_DUE|ANNOUNCEMENT|SYSTEM (optional)
      - limit: number (default 20)
    """
    qs = Notification.objects.filter(teacher=request.user, tenant=request.tenant)
    
    unread_only = request.GET.get('unread_only', '').lower() == 'true'
    if unread_only:
        qs = qs.filter(is_read=False)
    
    notif_type = request.GET.get('type', '').upper()
    valid_types = {choice[0] for choice in Notification.NOTIFICATION_TYPES}
    if notif_type in valid_types:
        qs = qs.filter(notification_type=notif_type)
    
    try:
        limit = min(100, max(1, int(request.GET.get('limit', 20))))
    except (ValueError, TypeError):
        limit = 20
    qs = qs.order_by('-created_at')[:limit]
    
    return Response(NotificationSerializer(qs, many=True).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def notification_unread_count(request):
    """
    Get count of unread notifications for the current teacher.
    Query params:
      - type: REMINDER|COURSE_ASSIGNED|ASSIGNMENT_DUE|ANNOUNCEMENT|SYSTEM (optional)
    """
    qs = Notification.objects.filter(
        teacher=request.user,
        tenant=request.tenant,
        is_read=False
    )
    notif_type = request.GET.get('type', '').upper()
    valid_types = {choice[0] for choice in Notification.NOTIFICATION_TYPES}
    if notif_type in valid_types:
        qs = qs.filter(notification_type=notif_type)
    return Response({'count': qs.count()}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def notification_mark_read(request, notification_id):
    """
    Mark a single notification as read.
    """
    try:
        notification = Notification.objects.get(
            id=notification_id,
            teacher=request.user,
            tenant=request.tenant
        )
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at'])
        return Response(NotificationSerializer(notification).data, status=status.HTTP_200_OK)
    except Notification.DoesNotExist:
        return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def notification_bulk_mark_read(request):
    """
    Mark multiple notifications as read by IDs.
    POST body: {"ids": ["uuid", ...]}
    """
    ids = request.data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return Response({'error': 'ids must be a non-empty list'}, status=status.HTTP_400_BAD_REQUEST)
    
    now = timezone.now()
    updated = Notification.objects.filter(
        id__in=ids,
        teacher=request.user,
        tenant=request.tenant,
        is_read=False,
    ).update(is_read=True, read_at=now)
    
    return Response({'marked_read': updated}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def notification_mark_all_read(request):
    """
    Mark all notifications as read for the current teacher.
    """
    now = timezone.now()
    updated = Notification.objects.filter(
        teacher=request.user,
        tenant=request.tenant,
        is_read=False
    ).update(is_read=True, read_at=now)
    
    return Response({'marked_read': updated}, status=status.HTTP_200_OK)


# ============================================================================
# Announcement endpoints (Admin only)
# ============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def announcement_list_create(request):
    """
    GET: List announcements created by admins (most recent first).
    POST: Create a new announcement to all teachers or specific groups.
    
    POST body:
    {
        "title": "string",
        "message": "string",
        "target": "all" | "groups",
        "group_ids": ["uuid", ...] (required if target is "groups")
    }
    """
    tenant = request.tenant
    
    if request.method == 'GET':
        # List announcements - get unique announcements by title+message+created_at
        # (since one announcement creates multiple notifications)
        # Use Min on Cast(id -> CharField) since PostgreSQL doesn't support MIN(uuid)
        from django.db.models.functions import Cast
        announcements = (
            Notification.objects.filter(
                tenant=tenant,
                notification_type='ANNOUNCEMENT'
            )
            .values('title', 'message', 'created_at')
            .annotate(
                recipient_count=models.Count('id'),
                first_id=Cast(models.Min(Cast('id', models.CharField())), models.UUIDField())
            )
            .order_by('-created_at')[:50]
        )
        
        return Response({
            'announcements': [
                {
                    'id': str(a['first_id']),
                    'title': a['title'],
                    'message': a['message'],
                    'recipient_count': a['recipient_count'],
                    'created_at': a['created_at'].isoformat(),
                }
                for a in announcements
            ]
        }, status=status.HTTP_200_OK)
    
    # POST - Create announcement
    title = (request.data.get('title') or '').strip()
    message = (request.data.get('message') or '').strip()
    target = (request.data.get('target') or 'all').lower()
    group_ids = request.data.get('group_ids', [])
    
    if not title or not message:
        return Response(
            {'error': 'Title and message are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if len(title) > 255:
        return Response(
            {'error': 'Title must be 255 characters or less'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Determine target teachers
    if target == 'groups' and group_ids:
        # Get teachers in specified groups
        groups = TeacherGroup.objects.filter(
            id__in=group_ids,
            tenant=tenant
        )
        teachers = User.objects.filter(
            tenant=tenant,
            is_active=True,
            teacher_groups__in=groups
        ).distinct()
    else:
        # All active teachers in tenant
        teachers = User.objects.filter(
            tenant=tenant,
            is_active=True,
            role__in=['TEACHER', 'HOD', 'IB_COORDINATOR']
        )
    
    teacher_count = teachers.count()
    if teacher_count == 0:
        return Response(
            {'error': 'No teachers found to send announcement'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create notifications for each teacher
    notifications = []
    for teacher in teachers:
        notifications.append(Notification(
            tenant=tenant,
            teacher=teacher,
            notification_type='ANNOUNCEMENT',
            title=title,
            message=message,
        ))
    
    Notification.objects.bulk_create(notifications)
    
    log_audit(
        'CREATE',
        'Announcement',
        target_repr=f'"{title}" to {teacher_count} teachers',
        changes={'target': target, 'teacher_count': teacher_count},
        request=request
    )
    
    return Response({
        'message': f'Announcement sent to {teacher_count} teachers',
        'title': title,
        'recipient_count': teacher_count,
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def announcement_delete(request, announcement_id):
    """
    Delete all notifications associated with an announcement.
    """
    tenant = request.tenant
    
    # Find the notification to get title/message for matching
    try:
        notification = Notification.objects.get(
            id=announcement_id,
            tenant=tenant,
            notification_type='ANNOUNCEMENT'
        )
    except Notification.DoesNotExist:
        return Response(
            {'error': 'Announcement not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Delete all notifications with same title, message, and exact creation time
    # bulk_create sets the same auto_now_add timestamp for all notifications in a batch
    deleted_count, _ = Notification.objects.filter(
        tenant=tenant,
        notification_type='ANNOUNCEMENT',
        title=notification.title,
        message=notification.message,
        created_at=notification.created_at,
    ).delete()
    
    log_audit(
        'DELETE',
        'Announcement',
        target_repr=f'"{notification.title}"',
        changes={'deleted_notifications': deleted_count},
        request=request
    )
    
    return Response({
        'message': f'Announcement deleted ({deleted_count} notifications removed)'
    }, status=status.HTTP_200_OK)
