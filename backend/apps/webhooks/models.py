# apps/webhooks/models.py
"""
Webhook models for event-driven integrations.

Allows tenants to:
- Register webhook endpoints
- Subscribe to specific events
- Receive HTTP callbacks on events
"""

import uuid
import secrets
from django.db import models
from django.utils import timezone


class WebhookEndpoint(models.Model):
    """
    Webhook endpoint configuration.
    
    Each tenant can have multiple webhook endpoints subscribed
    to different events.
    """
    
    EVENT_CHOICES = [
        # Course events
        ('course.created', 'Course Created'),
        ('course.published', 'Course Published'),
        ('course.unpublished', 'Course Unpublished'),
        ('course.deleted', 'Course Deleted'),
        
        # User events
        ('user.registered', 'User Registered'),
        ('user.activated', 'User Activated'),
        ('user.deactivated', 'User Deactivated'),
        
        # Progress events
        ('progress.started', 'Course Started'),
        ('progress.completed', 'Course Completed'),
        
        # Assignment events
        ('assignment.created', 'Assignment Created'),
        ('assignment.submitted', 'Assignment Submitted'),
        ('assignment.graded', 'Assignment Graded'),
        
        # Quiz events
        ('quiz.submitted', 'Quiz Submitted'),
        ('quiz.graded', 'Quiz Graded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='webhook_endpoints'
    )
    
    # Endpoint configuration
    name = models.CharField(max_length=200, help_text="Friendly name for this webhook")
    url = models.URLField(max_length=500, help_text="HTTPS URL to receive webhook payloads")
    secret = models.CharField(
        max_length=64,
        help_text="Secret for HMAC signature verification"
    )
    
    # Event subscriptions (stored as comma-separated string)
    events = models.JSONField(
        default=list,
        help_text="List of event types to subscribe to"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Statistics
    total_deliveries = models.PositiveIntegerField(default=0)
    successful_deliveries = models.PositiveIntegerField(default=0)
    failed_deliveries = models.PositiveIntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_failure_reason = models.TextField(blank=True, default='')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_webhooks'
    )
    
    class Meta:
        db_table = 'webhook_endpoints'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.url})"
    
    def save(self, *args, **kwargs):
        # Generate secret if not provided
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)
    
    @property
    def success_rate(self) -> float:
        if self.total_deliveries == 0:
            return 0.0
        return (self.successful_deliveries / self.total_deliveries) * 100


class WebhookDelivery(models.Model):
    """
    Individual webhook delivery attempt.
    
    Tracks each delivery attempt with status and response.
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name='deliveries'
    )
    
    # Event details
    event_type = models.CharField(max_length=50)
    event_id = models.UUIDField(default=uuid.uuid4)
    payload = models.JSONField()
    
    # Delivery status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    
    # Response details
    response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default='')
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'webhook_deliveries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['endpoint', 'status']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.event_type} -> {self.endpoint.url} ({self.status})"
