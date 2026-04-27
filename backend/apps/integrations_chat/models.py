"""
Models for the integrations_chat app.

ChatIntegration  — one webhook hookup per channel (Slack or Teams).
ChatRoutingRule  — which notification types flow to which integration.
ChatDelivery     — per-notification delivery audit + retry state.
"""

import uuid

from django.db import models
from django.utils import timezone

from utils.tenant_manager import TenantManager


class ChatIntegration(models.Model):
    """
    A configured incoming-webhook connection to Slack or Microsoft Teams.

    The webhook URL is stored encrypted (via integrations_common.crypto).
    API responses return only a masked form (last-4 chars visible).
    """

    PROVIDER_SLACK = "slack"
    PROVIDER_TEAMS = "teams"
    PROVIDER_CHOICES = [
        (PROVIDER_SLACK, "Slack"),
        (PROVIDER_TEAMS, "Microsoft Teams"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="chat_integrations",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    display_name = models.CharField(max_length=255)

    # Webhook URL — stored as Fernet-encrypted ciphertext; NEVER log the plaintext.
    webhook_url_encrypted = models.TextField(
        help_text="Fernet-encrypted webhook URL. Never log or return in full."
    )

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_chat_integrations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft-delete flag (keeps delivery history for 30 days).
    is_active = models.BooleanField(default=True, db_index=True)

    # Last delivery tracking (updated on successful / failed delivery).
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    last_delivery_status = models.CharField(max_length=20, blank=True, default="")
    error = models.TextField(blank=True, default="")

    objects = TenantManager()

    class Meta:
        db_table = "integrations_chat_integration"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="chat_int_tenant_active_idx"),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} — {self.display_name} ({self.tenant})"


class ChatRoutingRule(models.Model):
    """
    Determines which notification types (and optionally which user roles)
    are forwarded to a given ChatIntegration.
    """

    NOTIFICATION_TYPE_CHOICES = [
        ("COURSE_ASSIGNED", "Course Assigned"),
        ("ASSIGNMENT_DUE", "Assignment Due"),
        ("QUIZ_SUBMISSION", "Quiz Submission"),
        ("CERTIFICATION_EXPIRING", "Certification Expiring"),
        ("REPORT_GENERATED", "Report Generated"),
        ("REMINDER", "Reminder"),
        ("ANNOUNCEMENT", "Announcement"),
        ("SYSTEM", "System"),
    ]

    ROLE_CHOICES = [
        ("TEACHER", "Teacher"),
        ("HOD", "Head of Department"),
        ("IB_COORDINATOR", "IB Coordinator"),
        ("SCHOOL_ADMIN", "School Admin"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration = models.ForeignKey(
        ChatIntegration,
        on_delete=models.CASCADE,
        related_name="routing_rules",
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES,
    )
    # Optional role filter — if set, only notifications for users with this role
    # are forwarded.
    role_filter = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        null=True,
        blank=True,
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "integrations_chat_routing_rule"
        unique_together = [("integration", "notification_type", "role_filter")]
        ordering = ["notification_type"]

    def __str__(self):
        role = f" [{self.role_filter}]" if self.role_filter else ""
        return f"{self.notification_type}{role} → {self.integration.display_name}"


class ChatDelivery(models.Model):
    """
    One row per (notification, integration) pair.

    Provides idempotency (unique on integration + notification_id), retry
    tracking, and an audit trail.  The payload body is NOT stored here to
    avoid PII leakage; only notification_type and timestamps are kept.
    """

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_DLQ = "dlq"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed (retrying)"),
        (STATUS_DLQ, "Dead Letter Queue"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration = models.ForeignKey(
        ChatIntegration,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    # Idempotency: the notification UUID that triggered this delivery.
    notification_id = models.UUIDField(db_index=True)
    notification_type = models.CharField(max_length=30, blank=True, default="")

    # Payload stored for retry purposes only; cleared after successful send.
    payload_json = models.JSONField(default=dict)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    # Store only short error snippets — no full webhook body which may contain PII.
    last_error = models.CharField(max_length=500, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "integrations_chat_delivery"
        # Idempotency constraint: one delivery per (notification, integration).
        unique_together = [("integration", "notification_id")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["integration", "status"],
                name="chat_del_int_status_idx",
            ),
            models.Index(
                fields=["created_at", "status"],
                name="chat_del_created_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"ChatDelivery({self.notification_id}) "
            f"→ {self.integration.display_name} [{self.status}]"
        )
