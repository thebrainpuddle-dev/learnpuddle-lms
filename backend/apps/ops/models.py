import uuid

from django.db import models
from django.utils import timezone


class OpsEvent(models.Model):
    STATUS_CHOICES = [
        ("FAIL", "Fail"),
        ("RECOVER", "Recover"),
        ("INFO", "Info"),
    ]

    SEVERITY_CHOICES = [
        ("P1", "P1"),
        ("P2", "P2"),
        ("INFO", "Info"),
    ]

    CONFIDENCE_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    SOURCE_CHOICES = [
        ("synthetic", "Synthetic"),
        ("internal", "Internal"),
        ("harness", "Harness"),
    ]

    CATEGORY_CHOICES = [
        ("availability_probe", "Availability Probe"),
        ("auth_probe", "Auth Probe"),
        ("background_jobs", "Background Jobs"),
        ("deliverability", "Deliverability"),
        ("webhook_delivery", "Webhook Delivery"),
        ("harness_external", "Harness External"),
        ("maintenance", "Maintenance"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ops_events",
        null=True,
        blank=True,
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="P2")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    event_ts = models.DateTimeField(db_index=True)
    ingest_ts = models.DateTimeField(default=timezone.now, db_index=True)
    event_key = models.CharField(max_length=255, unique=True)
    payload_json = models.JSONField(default=dict, blank=True)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default="high")

    class Meta:
        db_table = "ops_events"
        ordering = ["-event_ts"]
        indexes = [
            models.Index(fields=["tenant", "event_ts"]),
            models.Index(fields=["category", "event_ts"]),
            models.Index(fields=["status", "event_ts"]),
            models.Index(fields=["source", "event_ts"]),
        ]


class OpsHealthSnapshot(models.Model):
    STATUS_CHOICES = [
        ("HEALTHY", "Healthy"),
        ("DEGRADED", "Degraded"),
        ("DOWN", "Down"),
        ("MAINTENANCE", "Maintenance"),
    ]

    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="ops_health_snapshot"
    )
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="HEALTHY")
    status_changed_at = models.DateTimeField(default=timezone.now)

    consecutive_failures = models.PositiveIntegerField(default=0)
    theme_consecutive_failures = models.PositiveIntegerField(default=0)
    auth_consecutive_failures = models.PositiveIntegerField(default=0)

    theme_probe_ok = models.BooleanField(default=True)
    auth_probe_ok = models.BooleanField(default=True)

    last_probe_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    freshness_seconds = models.PositiveIntegerField(default=0)
    last_probe_error = models.TextField(blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ops_health_snapshots"
        indexes = [
            models.Index(fields=["current_status"]),
            models.Index(fields=["last_probe_at"]),
        ]


class OpsIncident(models.Model):
    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("ACKED", "Acknowledged"),
        ("RESOLVED", "Resolved"),
    ]

    SEVERITY_CHOICES = [
        ("P1", "P1"),
        ("P2", "P2"),
    ]

    SCOPE_CHOICES = [
        ("GLOBAL", "Global"),
        ("TENANT", "Tenant"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    severity = models.CharField(max_length=5, choices=SEVERITY_CHOICES)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ops_incidents",
        null=True,
        blank=True,
    )
    rule_id = models.CharField(max_length=64, db_index=True)
    dedupe_key = models.CharField(max_length=128, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="OPEN", db_index=True)

    owner = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_ops_incidents",
    )

    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    mttr_seconds = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ops_incidents"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["rule_id", "status"]),
        ]


class OpsCollectorCursor(models.Model):
    collector_name = models.CharField(max_length=64, unique=True)
    watermark_ts = models.DateTimeField(null=True, blank=True)
    watermark_id = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ops_collector_cursors"


class OpsDeadLetter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=64)
    reason = models.CharField(max_length=255)
    payload_json = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "ops_dead_letters"
        ordering = ["-received_at"]


class OpsActionLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ops_action_logs",
    )
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    reason = models.TextField(blank=True, default="")
    details_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "ops_action_logs"
        ordering = ["-created_at"]


class MaintenanceSchedule(models.Model):
    DAY_CHOICES = [
        ("MONDAY", "Monday"),
        ("TUESDAY", "Tuesday"),
        ("WEDNESDAY", "Wednesday"),
        ("THURSDAY", "Thursday"),
        ("FRIDAY", "Friday"),
        ("SATURDAY", "Saturday"),
        ("SUNDAY", "Sunday"),
    ]

    enabled = models.BooleanField(default=False)
    week_of_month = models.PositiveSmallIntegerField(default=1)
    day = models.CharField(max_length=16, choices=DAY_CHOICES, default="SUNDAY")
    start_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=180)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")

    created_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_maintenance_schedules"
    )
    updated_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_maintenance_schedules"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ops_maintenance_schedules"


class MaintenanceRun(models.Model):
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(
        MaintenanceSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="SCHEDULED", db_index=True)
    reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_maintenance_runs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ops_maintenance_runs"
        ordering = ["-starts_at"]
        indexes = [
            models.Index(fields=["status", "starts_at"]),
        ]
