import uuid

from django.db import models
from django.db.models import Q

from utils.tenant_manager import TenantManager


class ReminderCampaign(models.Model):
    REMINDER_TYPE_CHOICES = [
        ("COURSE_DEADLINE", "Course deadline"),
        ("ASSIGNMENT_DUE", "Assignment due"),
        ("CUSTOM", "Custom"),
    ]
    SOURCE_CHOICES = [
        ("MANUAL", "Manual"),
        ("AUTOMATED", "Automated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="reminder_campaigns")
    created_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_reminder_campaigns"
    )

    reminder_type = models.CharField(max_length=30, choices=REMINDER_TYPE_CHOICES)
    course = models.ForeignKey("courses.Course", on_delete=models.SET_NULL, null=True, blank=True)
    assignment = models.ForeignKey("progress.Assignment", on_delete=models.SET_NULL, null=True, blank=True)

    subject = models.CharField(max_length=255, default="", blank=True)
    message = models.TextField(default="", blank=True)
    deadline_override = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="MANUAL")
    automation_key = models.CharField(max_length=120, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    # TenantManager auto-filters by current tenant (set via TenantMiddleware).
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "reminder_campaigns"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "source", "created_at"]),
            models.Index(fields=["tenant", "reminder_type", "source"]),
            models.Index(fields=["automation_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "automation_key"],
                condition=Q(source="AUTOMATED") & ~Q(automation_key=""),
                name="uniq_auto_reminder_campaign_per_tenant_key",
            )
        ]


class ReminderDelivery(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(ReminderCampaign, on_delete=models.CASCADE, related_name="deliveries")
    teacher = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="reminder_deliveries")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    error = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reminder_deliveries"
        unique_together = [("campaign", "teacher")]
        ordering = ["-created_at"]
        indexes = [
            # For filtering deliveries within a campaign by status
            models.Index(fields=["campaign", "status"], name="rem_del_camp_status_idx"),
            # For looking up a teacher's reminder delivery history
            models.Index(fields=["teacher", "status"], name="rem_del_tch_status_idx"),
            # For batch processing pending/failed deliveries by age
            models.Index(fields=["status", "created_at"], name="rem_del_stat_created_idx"),
        ]
