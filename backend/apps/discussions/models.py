# apps/discussions/models.py
"""
Discussion forum models.

Provides threaded discussions for courses and content items.
Supports nested replies, moderation, and notifications.
"""

import uuid
from django.db import models
from utils.tenant_manager import TenantManager


class DiscussionThread(models.Model):
    """
    A discussion thread attached to a course or content item.
    """
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='discussion_threads'
    )
    
    # Thread can be attached to course or specific content
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='discussion_threads',
        null=True,
        blank=True
    )
    content = models.ForeignKey(
        'courses.Content',
        on_delete=models.CASCADE,
        related_name='discussion_threads',
        null=True,
        blank=True
    )
    
    # Thread info
    title = models.CharField(max_length=300)
    body = models.TextField()
    
    # Author
    author = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='started_threads'
    )
    
    # Status & moderation
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    is_pinned = models.BooleanField(default=False)
    is_announcement = models.BooleanField(default=False)
    
    # Statistics
    reply_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    last_reply_at = models.DateTimeField(null=True, blank=True)
    last_reply_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = TenantManager()
    
    class Meta:
        db_table = 'discussion_threads'
        ordering = ['-is_pinned', '-last_reply_at', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'course', 'status']),
            models.Index(fields=['tenant', 'content', 'status']),
            models.Index(fields=['author', 'created_at']),
        ]
    
    def __str__(self):
        return self.title
    
    def increment_view(self):
        """Increment view count."""
        self.view_count += 1
        self.save(update_fields=['view_count'])
    
    def update_reply_stats(self):
        """Update reply count and last reply info."""
        last_reply = self.replies.order_by('-created_at').first()
        self.reply_count = self.replies.count()
        if last_reply:
            self.last_reply_at = last_reply.created_at
            self.last_reply_by = last_reply.author
        else:
            self.last_reply_at = None
            self.last_reply_by = None
        self.save(update_fields=['reply_count', 'last_reply_at', 'last_reply_by'])


class DiscussionReply(models.Model):
    """
    A reply in a discussion thread.
    
    Supports nested replies via parent reference.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        DiscussionThread,
        on_delete=models.CASCADE,
        related_name='replies'
    )
    
    # Parent for nested replies (null = top-level reply)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    
    # Content
    body = models.TextField()
    
    # Author
    author = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='discussion_replies'
    )
    
    # Moderation
    is_hidden = models.BooleanField(default=False)
    hidden_reason = models.CharField(max_length=200, blank=True)
    hidden_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hidden_replies'
    )
    
    # Edited
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    like_count = models.PositiveIntegerField(default=0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'discussion_replies'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['thread', 'created_at']),
            models.Index(fields=['author', 'created_at']),
            models.Index(fields=['parent']),
        ]
    
    def __str__(self):
        return f"Reply by {self.author} on {self.thread.title}"
    
    @property
    def depth(self) -> int:
        """Calculate nesting depth (0 for top-level)."""
        depth = 0
        parent = self.parent
        while parent:
            depth += 1
            parent = parent.parent
        return depth


class DiscussionLike(models.Model):
    """
    Like on a reply.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reply = models.ForeignKey(
        DiscussionReply,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='discussion_likes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'discussion_likes'
        unique_together = [('reply', 'user')]


class DiscussionSubscription(models.Model):
    """
    Thread subscription for notifications.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        DiscussionThread,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='thread_subscriptions'
    )
    
    # Notification preferences
    notify_on_reply = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'discussion_subscriptions'
        unique_together = [('thread', 'user')]
