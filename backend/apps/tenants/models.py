# apps/tenants/models.py

from django.db import models
from django.utils.text import slugify
import uuid


class Tenant(models.Model):
    """
    Represents a school/institution.
    Each tenant is completely isolated from others.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="School name")
    slug = models.SlugField(max_length=200, unique=True, help_text="URL-friendly identifier")
    subdomain = models.CharField(max_length=100, unique=True, help_text="e.g., schoolname.lms.com")
    
    # Contact Information
    email = models.EmailField(help_text="Primary contact email")
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # Branding
    logo = models.ImageField(upload_to='tenant_logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#1F4788', help_text="Hex color code")
    secondary_color = models.CharField(max_length=7, blank=True, default='', help_text="Optional hex color code")
    font_family = models.CharField(max_length=100, blank=True, default='Inter', help_text="CSS font-family name")
    
    # Status
    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=True)
    trial_end_date = models.DateField(null=True, blank=True)

    # Subscription plan
    PLAN_CHOICES = [
        ('FREE', 'Free'),
        ('STARTER', 'Starter'),
        ('PRO', 'Professional'),
        ('ENTERPRISE', 'Enterprise'),
    ]
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='FREE')
    plan_started_at = models.DateTimeField(null=True, blank=True)
    plan_expires_at = models.DateTimeField(null=True, blank=True)

    # Limits (configurable per school by super admin)
    max_teachers = models.PositiveIntegerField(default=10, help_text="Max teacher accounts")
    max_courses = models.PositiveIntegerField(default=5, help_text="Max courses")
    max_storage_mb = models.PositiveIntegerField(default=500, help_text="Max storage in MB")
    max_video_duration_minutes = models.PositiveIntegerField(default=60, help_text="Max single video duration (min)")

    # Feature flags (granular toggles, controlled by super admin)
    feature_video_upload = models.BooleanField(default=False)
    feature_auto_quiz = models.BooleanField(default=False)
    feature_transcripts = models.BooleanField(default=False)
    feature_reminders = models.BooleanField(default=True)
    feature_custom_branding = models.BooleanField(default=False)
    feature_reports_export = models.BooleanField(default=False)
    feature_groups = models.BooleanField(default=True)
    feature_certificates = models.BooleanField(default=False)

    # Super admin internal notes
    internal_notes = models.TextField(blank=True, default='')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants'
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['subdomain']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
