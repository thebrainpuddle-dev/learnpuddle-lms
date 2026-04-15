# apps/academics/attendance_models.py
"""
Attendance tracking — pre-recorded data imported from external systems.
Read-only for teachers/students/parents; admin manages imports.
"""

import uuid
from django.db import models
from utils.tenant_manager import TenantManager


class Attendance(models.Model):
    """Daily attendance record for a student in a section."""

    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
        ('EXCUSED', 'Excused'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='attendance_records',
    )
    section = models.ForeignKey(
        'academics.Section', on_delete=models.CASCADE, related_name='attendance_records',
    )
    student = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='attendance_records',
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PRESENT')
    remarks = models.CharField(max_length=255, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'attendance'
        unique_together = [('tenant', 'section', 'student', 'date')]
        ordering = ['-date', 'student__last_name']
        indexes = [
            models.Index(fields=['tenant', 'section', 'date']),
            models.Index(fields=['tenant', 'student', 'date']),
            models.Index(fields=['tenant', 'date']),
        ]

    def __str__(self):
        return f"{self.student.get_full_name()} — {self.date} — {self.status}"
