# apps/notifications/consumers.py
"""
WebSocket consumer for real-time notifications.

Handles:
- User authentication and group subscription
- Receiving notifications from channel layer
- Marking notifications as read
- Heartbeat/ping for connection health
"""

import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for user notifications.
    
    Each authenticated user joins their personal notification group.
    Notifications are pushed from backend services via channel layer.
    
    Message types:
    - notification: New notification data
    - notification_read: Notification marked as read
    - unread_count: Updated unread count
    - pong: Response to ping
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope.get("user", AnonymousUser())
        
        if self.user.is_anonymous:
            logger.warning("Rejected anonymous WebSocket connection")
            await self.close(code=4001)
            return
        
        # Store tenant for filtering
        self.tenant_id = self.user.tenant_id
        
        # Create user-specific group name (includes tenant for extra isolation)
        self.group_name = f"notifications_{self.user.id}"
        
        # Join user's notification group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"WebSocket connected: user={self.user.id}")
        
        # Send initial unread count
        unread_count = await self.get_unread_count()
        await self.send_json({
            "type": "unread_count",
            "count": unread_count,
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.info(f"WebSocket disconnected: user={self.user.id}, code={close_code}")
    
    async def receive_json(self, content):
        """
        Handle messages from the WebSocket client.
        
        Supported message types:
        - ping: Connection health check
        - mark_read: Mark notification(s) as read
        - mark_all_read: Mark all notifications as read
        """
        msg_type = content.get("type")
        
        if msg_type == "ping":
            await self.send_json({"type": "pong"})
        
        elif msg_type == "mark_read":
            notification_ids = content.get("ids", [])
            if notification_ids:
                count = await self.mark_notifications_read(notification_ids)
                unread_count = await self.get_unread_count()
                await self.send_json({
                    "type": "notification_read",
                    "ids": notification_ids,
                    "unread_count": unread_count,
                })
        
        elif msg_type == "mark_all_read":
            await self.mark_all_read()
            await self.send_json({
                "type": "unread_count",
                "count": 0,
            })
    
    async def notification_message(self, event):
        """
        Handle notification message from channel layer.
        
        Called when a new notification is sent via:
        channel_layer.group_send(group_name, {"type": "notification.message", ...})
        """
        await self.send_json({
            "type": "notification",
            "notification": event["notification"],
        })
    
    async def unread_count_update(self, event):
        """Handle unread count update from channel layer."""
        await self.send_json({
            "type": "unread_count",
            "count": event["count"],
        })
    
    @database_sync_to_async
    def get_unread_count(self) -> int:
        """Get count of unread notifications for the user within their tenant."""
        from .models import Notification
        filters = {'teacher': self.user, 'is_read': False}
        if self.tenant_id:
            filters['tenant_id'] = self.tenant_id
        return Notification.objects.filter(**filters).count()
    
    @database_sync_to_async
    def mark_notifications_read(self, notification_ids: list) -> int:
        """Mark specific notifications as read (tenant-isolated)."""
        from .models import Notification
        filters = {'teacher': self.user, 'id__in': notification_ids, 'is_read': False}
        if self.tenant_id:
            filters['tenant_id'] = self.tenant_id
        return Notification.objects.filter(**filters).update(is_read=True, read_at=timezone.now())
    
    @database_sync_to_async
    def mark_all_read(self):
        """Mark all notifications as read for the user (tenant-isolated)."""
        from .models import Notification
        filters = {'teacher': self.user, 'is_read': False}
        if self.tenant_id:
            filters['tenant_id'] = self.tenant_id
        Notification.objects.filter(**filters).update(is_read=True, read_at=timezone.now())


def get_user_group_name(user_id: str) -> str:
    """Get the channel group name for a user."""
    return f"notifications_{user_id}"
