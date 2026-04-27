# apps/tenants/models.py

from django.db import models
from django.utils.text import slugify
from django.utils import timezone
import uuid

from utils.storage_paths import tenant_logo_upload_to


# ---------------------------------------------------------------------------
# TASK-020 — Education vs Corporate mode terminology map
# ---------------------------------------------------------------------------
#
# A tenant's `mode` field switches the default display terminology between
# an academic context ("Teachers", "Courses", "Badges", "League") and a
# corporate L&D context ("Employees", "Training Programs", "Achievements",
# "Tier").  The map is a pure display layer: backend data (XP rows, badges,
# leagues) is NOT re-keyed when the mode flips.  Frontend code is expected
# to read `Tenant.get_mode_labels()` (exposed via `/api/v1/tenants/me/`) and
# substitute strings on render.
#
# Tenants may layer per-instance overrides via `mode_label_overrides`
# (e.g., `{"course": "Masterclass"}`) to customise specific labels without
# touching the base map.

MODE_LABEL_DEFAULTS = {
    "education": {
        "learner":        "Teacher",
        "learner_plural": "Teachers",
        "course":         "Course",
        "course_plural":  "Courses",
        "module":         "Module",
        "lesson":         "Lesson",
        "assignment":     "Assignment",
        "badge":          "Badge",
        "league":         "League",
        "xp":             "XP",
        "streak":         "Streak",
        "dashboard":      "Dashboard",
    },
    "corporate": {
        "learner":        "Employee",
        "learner_plural": "Employees",
        "course":         "Training Program",
        "course_plural":  "Training Programs",
        "module":         "Module",
        "lesson":         "Task",
        "assignment":     "Task",
        "badge":          "Achievement",
        "league":         "Tier",
        "xp":             "Points",
        "streak":         "Streak",
        "dashboard":      "Workspace",
    },
}


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
    feature_saml = models.BooleanField(
        default=False,
        help_text="Enable SAML 2.0 SSO (per TASK-045). Distinct from OAuth-style feature_sso.",
    )
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

    # ─── Education vs Corporate Mode (TASK-020) ───────────────────────────
    MODE_CHOICES = [
        ('education', 'Education'),
        ('corporate', 'Corporate'),
    ]
    mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES,
        default='education',
        help_text=(
            "Display-terminology mode. 'education' uses Teacher/Course/Badge; "
            "'corporate' uses Employee/Training Program/Achievement. Purely "
            "a display switch — no stored gamification data is re-keyed."
        ),
    )
    mode_label_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-tenant overrides layered on top of MODE_LABEL_DEFAULTS for "
            "the active mode, e.g., {'course': 'Masterclass'}."
        ),
    )

    # ─── Default content language (TASK-058) ─────────────────────────────
    # Source language pinned per-tenant for the auto-translation service.
    # Always set (default "en"); never blank, never null. Used by the
    # translation provider to pick the ``from`` side.
    default_language = models.CharField(
        max_length=20,
        default='en',
        help_text=(
            "BCP-47 language code for this tenant's source content. "
            "Used by the auto-translation service (TASK-058) as the "
            "'from' language when translating Course / Module / Content."
        ),
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

    def get_mode_labels(self) -> dict:
        """
        Return the merged terminology map for this tenant.

        Starts from MODE_LABEL_DEFAULTS[self.mode] (falling back to
        'education' if the mode somehow does not match — defensive, since
        choices validate on save) and layers ``self.mode_label_overrides``
        on top so admin-supplied custom labels win.

        Callers should treat this as the authoritative label source for UI
        rendering; unknown keys should fall back to the canonical English
        terms client-side.
        """
        base = MODE_LABEL_DEFAULTS.get(self.mode, MODE_LABEL_DEFAULTS['education'])
        labels = dict(base)  # shallow copy — values are strings
        if isinstance(self.mode_label_overrides, dict) and self.mode_label_overrides:
            # Only layer overrides whose values are strings to avoid polluting
            # the map with garbage types.
            for key, value in self.mode_label_overrides.items():
                if isinstance(value, str) and value.strip():
                    labels[key] = value
        return labels

    @property
    def features(self) -> dict:
        """Read-only dict view over the tenant's feature_* BooleanFields.

        This lets callers use the spec-blessed form ``tenant.features.get('saml')``
        without requiring a separate JSONField.  Adding a new flag here requires
        updating the mapping.
        """
        return {
            "saml": self.feature_saml,
            "sso": self.feature_sso,
            "2fa": self.feature_2fa,
            "video_upload": self.feature_video_upload,
            "auto_quiz": self.feature_auto_quiz,
            "transcripts": self.feature_transcripts,
            "reminders": self.feature_reminders,
            "custom_branding": self.feature_custom_branding,
            "reports_export": self.feature_reports_export,
            "groups": self.feature_groups,
            "certificates": self.feature_certificates,
            "teacher_authoring": self.feature_teacher_authoring,
            "ai_studio": self.feature_ai_studio,
            "students": self.feature_students,
            "maic": self.feature_maic,
        }


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
        # TASK-053 additions
        ('RUN_REPORT', 'Run Report'),
        ('EXPORT_REPORT', 'Export Report'),
        # TASK-052 backfill (requested in TASK-053 spec)
        ('EXPORT_SCORM', 'Export SCORM'),
        ('IMPORT_SCORM', 'Import SCORM'),
        # TASK-055 — Chat integration audit actions
        ('CHAT_INTEGRATION_CREATED', 'Chat Integration Created'),
        ('CHAT_INTEGRATION_DELETED', 'Chat Integration Deleted'),
        ('CHAT_DELIVERY_FAILED', 'Chat Delivery Failed (DLQ)'),
        # TASK-054 — Calendar integration audit actions
        ('CONNECT_CALENDAR', 'Calendar Connected'),
        ('DISCONNECT_CALENDAR', 'Calendar Disconnected'),
        ('SYNC_CALENDAR_ERROR', 'Calendar Sync Error'),
        # TASK-058 — Auto-Translation Service audit actions
        ('TRANSLATION_STARTED', 'Translation Started'),
        ('TRANSLATION_FINISHED', 'Translation Finished'),
        ('TRANSLATION_FAILED', 'Translation Failed'),
        ('TRANSLATION_PURGED', 'Translation Purged'),
        # TASK-057 — Semantic-search reindex audit actions
        ('SEMANTIC_REINDEX_STARTED', 'Semantic Reindex Started'),
        ('SEMANTIC_REINDEX_FINISHED', 'Semantic Reindex Finished'),
        ('SEMANTIC_REINDEX_FAILED', 'Semantic Reindex Failed'),
        # TASK-060 — AI Course Generator audit actions
        ('COURSE_GENERATION_STARTED', 'Course Generation Started'),
        ('COURSE_GENERATION_SUCCEEDED', 'Course Generation Succeeded'),
        ('COURSE_GENERATION_FAILED', 'Course Generation Failed'),
        ('COURSE_MATERIALISED', 'Course Materialised'),
        ('COURSE_GENERATION_PURGED', 'Course Generation Purged'),
        # TASK-059 — AI Chatbot Tutor audit actions
        ('CHAT_QUERY_ASKED', 'Chat Query Asked'),
        ('CHAT_QUERY_PURGED', 'Chat Query Purged'),
        # TASK-064b — Translation per-field review audit actions
        ('TRANSLATION_FIELD_APPROVED', 'Translation Field Approved'),
        ('TRANSLATION_FIELD_REJECTED', 'Translation Field Rejected'),
        ('TRANSLATION_FIELD_EDITED', 'Translation Field Edited'),
        ('TRANSLATION_PUBLISHED', 'Translation Published'),
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
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
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

# SAML SSO + per-tenant password policy models.
from .saml_models import TenantSAMLConfig  # noqa: E402, F401
from .password_policy_models import TenantPasswordPolicy  # noqa: E402, F401
