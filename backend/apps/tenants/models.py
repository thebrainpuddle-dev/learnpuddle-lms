# apps/tenants/models.py

from django.db import models
from django.utils.text import slugify
from django.utils import timezone
import uuid

from utils.storage_paths import tenant_logo_upload_to


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
    logo = models.ImageField(upload_to=tenant_logo_upload_to, blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#1F4788', help_text="Hex color code")
    secondary_color = models.CharField(max_length=7, blank=True, default='', help_text="Optional hex color code")
    font_family = models.CharField(max_length=100, blank=True, default='Inter', help_text="CSS font-family name")
    
    # Status
    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=True)
    trial_end_date = models.DateField(null=True, blank=True)
    maintenance_mode_enabled = models.BooleanField(default=False)
    maintenance_mode_reason = models.TextField(blank=True, default="")
    maintenance_mode_ends_at = models.DateTimeField(null=True, blank=True)

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
    stripe_customer_id = models.CharField(max_length=255, blank=True, default='', db_index=True)

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
    feature_teacher_authoring = models.BooleanField(default=False)
    feature_ai_studio = models.BooleanField(default=False, help_text="AI lesson builder & interactive slides")
    feature_sso = models.BooleanField(default=False)
    feature_2fa = models.BooleanField(default=False)
    feature_students = models.BooleanField(default=False, help_text="Enable student portal")
    feature_maic = models.BooleanField(default=False, help_text="Enable OpenMAIC AI Classroom feature")

    # Student limits
    max_students = models.PositiveIntegerField(default=50, help_text="Max student accounts")

    # SSO Configuration
    sso_domains = models.TextField(
        blank=True, default='',
        help_text="Comma-separated list of allowed SSO domains (e.g., school.edu,district.edu)"
    )
    allow_sso_registration = models.BooleanField(
        default=True,
        help_text="Allow new users to register via SSO"
    )
    require_sso = models.BooleanField(
        default=False,
        help_text="Require SSO for all users (disable password login)"
    )
    require_2fa = models.BooleanField(
        default=False,
        help_text="Require 2FA for all users"
    )

    # Custom domain support
    custom_domain = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Custom domain (e.g., lms.school.edu)"
    )
    custom_domain_verified = models.BooleanField(default=False)
    custom_domain_ssl_expires = models.DateTimeField(null=True, blank=True)

    # Notification sender profile (school-branded display + routing bucket)
    notification_from_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text="Optional display sender name for school notifications",
    )
    notification_reply_to = models.EmailField(
        blank=True,
        default='',
        help_text="Reply-to email for school notifications",
    )
    email_bucket_prefix = models.CharField(
        max_length=120,
        blank=True,
        default='',
        help_text="Optional bucket prefix for outbound email analytics",
    )

    # Super admin internal notes
    internal_notes = models.TextField(blank=True, default='')

    # ─── Academic Structure ───────────────────────────────────────────────
    current_academic_year = models.CharField(
        max_length=20, blank=True, default='',
        help_text="Current academic year, e.g. 2026-27",
    )
    academic_year_start_date = models.DateField(
        null=True, blank=True,
        help_text="Start date of the current academic year",
    )
    academic_year_end_date = models.DateField(
        null=True, blank=True,
        help_text="End date of the current academic year",
    )

    # ─── Auto-Generated User IDs ─────────────────────────────────────────
    id_prefix = models.CharField(
        max_length=10, blank=True, default='',
        help_text="Prefix for auto-generated user IDs, e.g. KIS",
    )
    student_id_counter = models.PositiveIntegerField(
        default=1,
        help_text="Next sequence number for student ID generation (atomic)",
    )
    teacher_id_counter = models.PositiveIntegerField(
        default=1,
        help_text="Next sequence number for teacher ID generation (atomic)",
    )

    # ─── White-Label Branding ─────────────────────────────────────────────
    white_label = models.BooleanField(
        default=False,
        help_text="When enabled, hides all LearnPuddle branding",
    )
    login_bg_image = models.URLField(
        max_length=500, blank=True, default='',
        help_text="Background image URL for the login page",
    )
    welcome_message = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Dashboard greeting message, e.g. 'Welcome to Keystone Learning'",
    )
    school_motto = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Footer/about text, e.g. 'Powered by the Idea-Loom Model'",
    )

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
            models.Index(fields=['maintenance_mode_enabled']),
            models.Index(fields=['custom_domain']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """Tracks admin actions for security and compliance."""

    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('PUBLISH', 'Publish'),
        ('UNPUBLISH', 'Unpublish'),
        ('DEACTIVATE', 'Deactivate'),
        ('ACTIVATE', 'Activate'),
        ('PASSWORD_RESET', 'Password Reset'),
        ('SETTINGS_CHANGE', 'Settings Change'),
        ('IMPORT', 'Bulk Import'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='audit_logs', null=True, blank=True,
    )
    actor = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_actions',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=100, help_text="e.g. 'User', 'Course'")
    target_id = models.CharField(max_length=255, blank=True)
    target_repr = models.CharField(max_length=500, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    request_id = models.CharField(max_length=64, blank=True, default='')
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['tenant', 'timestamp']),
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['target_type', 'target_id']),
        ]

    def __str__(self):
        return f"{self.actor} {self.action} {self.target_type}:{self.target_id}"


class DemoBooking(models.Model):
    """Tracks demo call bookings from the marketing site or manual super admin entry."""

    SOURCE_CHOICES = [
        ('cal_webhook', 'Cal.com Webhook'),
        ('manual', 'Manual Entry'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    email = models.EmailField()
    company = models.CharField(max_length=200, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    cal_event_id = models.CharField(max_length=200, blank=True, default='')
    scheduled_at = models.DateTimeField()
    notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    followup_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_demo_bookings',
    )

    class Meta:
        db_table = 'demo_bookings'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['email']),
            models.Index(fields=['scheduled_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.email}) - {self.scheduled_at}"


# Import accreditation models so Django discovers them via this module
from .accreditation_models import SchoolAccreditation, AccreditationMilestone, RankingEntry, ComplianceItem, StaffCertification  # noqa: E402, F401
