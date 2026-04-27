"""
apps/reports_builder/models.py
--------------------------------
Models for the Custom Report Builder (TASK-053).

Three main models:
  * ReportDefinition  — saved builder state (data source + filters + group-by + aggregates).
  * ReportSchedule    — recurring delivery schedule (cadence + recipients).
  * ReportRun         — audit record + artifact registry for each execution.

All three use TenantManager for automatic tenant isolation.
ReportRun has an explicit tenant FK (belt-and-braces — reviewer requirement).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from utils.tenant_manager import TenantManager


class ReportDefinition(models.Model):
    """Saved report definition composed in the report builder UI."""

    DATA_SOURCE_CHOICES = [
        ("courses", "Courses"),
        ("teacher_progress", "Teacher Progress"),
        ("assignments", "Assignments"),
        ("quiz_attempts", "Quiz Attempts"),
        ("gamification", "XP / Gamification"),
        ("certifications", "Certifications"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="report_definitions",
    )
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    data_source = models.CharField(max_length=50, choices=DATA_SOURCE_CHOICES)

    # Validated JSON fields (schema enforced at serializer layer)
    filters_json = models.JSONField(default=list, blank=True)
    group_by_json = models.JSONField(default=list, blank=True)
    aggregates_json = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_soft_deleted = models.BooleanField(default=False, db_index=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "report_definitions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "is_soft_deleted"]),
            models.Index(fields=["tenant", "data_source"]),
            models.Index(fields=["created_by"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.data_source}]"

    def soft_delete(self) -> None:
        self.is_soft_deleted = True
        self.save(update_fields=["is_soft_deleted", "updated_at"])


class ReportSchedule(models.Model):
    """Recurring delivery schedule attached to a ReportDefinition."""

    CADENCE_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]
    STATUS_CHOICES = [
        ("ok", "OK"),
        ("error", "Error"),
        ("never_run", "Never Run"),
        ("delivery_failed", "Delivery Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(
        ReportDefinition,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    # Tenant FK mirrors definition.tenant for fast queries.
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="report_schedules",
    )
    cadence = models.CharField(max_length=10, choices=CADENCE_CHOICES)
    run_at_hour = models.PositiveSmallIntegerField(
        default=6, help_text="UTC hour (0–23) to run"
    )
    # For weekly
    run_at_day_of_week = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="0=Mon … 6=Sun"
    )
    # For monthly
    run_at_day_of_month = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="1–28"
    )
    recipients_json = models.JSONField(
        default=list, help_text="Array of tenant user email strings"
    )
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="never_run"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "report_schedules"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "enabled"]),
            models.Index(fields=["definition"]),
        ]

    def __str__(self) -> str:
        return f"{self.definition.name} / {self.cadence}"


class ReportRun(models.Model):
    """Audit record + artifact registry for a single report execution."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Belt-and-braces tenant FK (spec requirement — do NOT rely on definition only).
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="report_runs",
    )
    definition = models.ForeignKey(
        ReportDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    run_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_runs",
    )
    # Snapshot of params used for this run (definition may change later).
    params_snapshot_json = models.JSONField(default=dict)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    row_count = models.IntegerField(default=0)
    # Storage key for the generated CSV (local path or S3 key).
    artifact_path = models.TextField(blank=True, default="")
    artifact_sha256 = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error = models.TextField(blank=True, default="")

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "report_runs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "definition", "started_at"]),
            models.Index(fields=["run_by"]),
        ]

    def __str__(self) -> str:
        return f"Run {self.id} [{self.status}]"
