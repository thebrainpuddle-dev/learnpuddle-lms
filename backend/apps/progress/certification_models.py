# apps/progress/certification_models.py

import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from utils.tenant_manager import TenantManager


class CertificationType(models.Model):
    """
    Defines a type of certification that can be issued to teachers.
    Tenant-scoped. Optionally linked to required courses.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='certification_types',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    validity_months = models.IntegerField(
        default=12,
        validators=[MinValueValidator(1)],
        help_text="Number of months the certification is valid",
    )
    auto_renew = models.BooleanField(
        default=False,
        help_text="Automatically renew when expired (if all required courses are completed)",
    )
    required_courses = models.ManyToManyField(
        'courses.Course',
        blank=True,
        related_name='required_for_certifications',
        help_text="Courses that must be completed for this certification",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'certification_types'
        ordering = ['name']
        unique_together = [('tenant', 'name')]
        indexes = [
            models.Index(fields=['tenant', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.validity_months}mo)"


class TeacherCertification(models.Model):
    """
    Tracks a certification issued to a teacher with expiry and status management.
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked'),
        ('pending_renewal', 'Pending Renewal'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='teacher_certifications',
    )
    certification_type = models.ForeignKey(
        CertificationType,
        on_delete=models.CASCADE,
        related_name='issued_certifications',
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='teacher_certifications',
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
    )
    certificate_file = models.FileField(
        upload_to='certificates/',
        null=True,
        blank=True,
    )
    issued_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_certifications',
        help_text="Admin who issued this certification",
    )
    revoked_reason = models.TextField(blank=True, default='')
    renewal_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teacher_certifications'
        ordering = ['-issued_at']
        indexes = [
            models.Index(fields=['tenant', 'teacher', 'status']),
            models.Index(fields=['tenant', 'certification_type', 'status']),
            models.Index(fields=['expires_at', 'status']),
            models.Index(fields=['tenant', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.teacher.email} - {self.certification_type.name} ({self.status})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def days_until_expiry(self):
        delta = self.expires_at - timezone.now()
        return delta.days

    def check_and_update_status(self):
        """Update status based on expiry date. Returns True if status changed."""
        if self.status == 'revoked':
            return False
        if self.is_expired and self.status == 'active':
            self.status = 'expired'
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False
