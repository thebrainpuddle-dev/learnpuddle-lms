from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import teacher_or_admin, tenant_required
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
      - limit: number (default 20)
    """
    qs = Notification.objects.filter(teacher=request.user, tenant=request.tenant)
    
    unread_only = request.GET.get('unread_only', '').lower() == 'true'
    if unread_only:
        qs = qs.filter(is_read=False)
    
    limit = int(request.GET.get('limit', 20))
    qs = qs.order_by('-created_at')[:limit]
    
    return Response(NotificationSerializer(qs, many=True).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def notification_unread_count(request):
    """
    Get count of unread notifications for the current teacher.
    """
    count = Notification.objects.filter(
        teacher=request.user,
        tenant=request.tenant,
        is_read=False
    ).count()
    return Response({'count': count}, status=status.HTTP_200_OK)


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
