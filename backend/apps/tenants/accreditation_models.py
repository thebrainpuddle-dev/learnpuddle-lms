# apps/tenants/accreditation_models.py

from django.db import models
import uuid

from utils.tenant_manager import TenantManager


ACCREDITATION_TYPES = [
    ('IB_PYP', 'IB Primary Years Programme'),
    ('IB_MYP', 'IB Middle Years Programme'),
    ('IB_DP', 'IB Diploma Programme'),
    ('IB_CP', 'IB Career-related Programme'),
    ('CBSE', 'CBSE Affiliation'),
    ('ICSE', 'ICSE/ISC Affiliation'),
    ('CAMBRIDGE_IGCSE', 'Cambridge IGCSE'),
    ('CAMBRIDGE_AL', 'Cambridge AS/A Level'),
    ('NABET', 'NABET/QCI Accreditation'),
    ('CIS', 'CIS Accreditation'),
    ('ISO_9001', 'ISO 9001:2015'),
    ('ISO_21001', 'ISO 21001:2018'),
    ('GREEN_SCHOOL', 'IGBC Green School'),
    ('OTHER', 'Other'),
]

ACCREDITATION_STATUS_CHOICES = [
    ('AUTHORIZED', 'Authorized / Active'),
    ('CANDIDACY', 'Candidacy / In Progress'),
    ('CONSIDERATION', 'Under Consideration'),
    ('PENDING', 'Application Pending'),
    ('EXPIRED', 'Expired'),
    ('NOT_STARTED', 'Not Started'),
]

MILESTONE_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('IN_PROGRESS', 'In Progress'),
    ('COMPLETED', 'Completed'),
    ('OVERDUE', 'Overdue'),
]


class SchoolAccreditation(models.Model):
    """
    Tracks accreditations and affiliations held by a school/tenant.
    Examples: IB authorization, CBSE affiliation, ISO certification.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='accreditations',
    )
    accreditation_type = models.CharField(
        max_length=30, choices=ACCREDITATION_TYPES,
        help_text="Type of accreditation or affiliation",
    )
    custom_name = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Custom name if type is OTHER",
    )
    status = models.CharField(
        max_length=20, choices=ACCREDITATION_STATUS_CHOICES, default='NOT_STARTED',
    )
    affiliation_number = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Official affiliation or registration number",
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    issuing_body = models.CharField(
        max_length=200,
        help_text="Name of the issuing/certifying body",
    )
    external_portal_url = models.URLField(
        max_length=500, blank=True, default='',
        help_text="URL to the external accreditation portal",
    )
    notes = models.TextField(blank=True, default='')
    renewal_cycle_months = models.IntegerField(
        null=True, blank=True,
        help_text="Renewal cycle in months (e.g., 60 for 5-year cycle)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'school_accreditations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'accreditation_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        label = self.custom_name if self.accreditation_type == 'OTHER' else self.get_accreditation_type_display()
        return f"{label} ({self.get_status_display()})"


class AccreditationMilestone(models.Model):
    """
    Tracks milestones/tasks within an accreditation journey.
    E.g., "Submit self-study report", "Host evaluation visit".
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    accreditation = models.ForeignKey(
        SchoolAccreditation, on_delete=models.CASCADE,
        related_name='milestones',
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=MILESTONE_STATUS_CHOICES, default='PENDING',
    )
    order = models.IntegerField(default=0, help_text="Display order within accreditation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accreditation_milestones'
        ordering = ['order', 'due_date']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class RankingEntry(models.Model):
    """
    Tracks the school's position in external rankings/surveys.
    E.g., "Education World 2025 — Rank #3 in City, Score 92.5".
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='rankings',
    )
    platform = models.CharField(
        max_length=50,
        help_text="Ranking platform name, e.g. Education World, HT Top Schools",
    )
    year = models.IntegerField(help_text="Ranking year")
    rank = models.IntegerField(null=True, blank=True, help_text="Rank position (lower is better)")
    category = models.CharField(
        max_length=100,
        help_text="Ranking category, e.g. City, State, National, STEM, etc.",
    )
    score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Survey/assessment score if available",
    )
    survey_url = models.URLField(max_length=500, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'ranking_entries'
        ordering = ['-year', 'platform']
        unique_together = [('tenant', 'platform', 'year', 'category')]
        indexes = [
            models.Index(fields=['tenant', 'year']),
            models.Index(fields=['platform', 'year']),
        ]

    def __str__(self):
        rank_str = f"#{self.rank}" if self.rank else "Unranked"
        return f"{self.platform} {self.year} — {rank_str} ({self.category})"


# ── Compliance Tracker ──────────────────────────────────────────────────────

COMPLIANCE_CATEGORY_CHOICES = [
    ('SAFETY', 'Safety & Infrastructure'),
    ('BOARD', 'Board & Government'),
    ('NEP', 'NEP 2020 Alignment'),
    ('FINANCIAL', 'Financial & Fee Regulation'),
    ('DATA', 'Data & Privacy'),
    ('IB', 'IB Programme Requirements'),
    ('OTHER', 'Other'),
]

COMPLIANCE_STATUS_CHOICES = [
    ('COMPLIANT', 'Compliant'),
    ('IN_PROGRESS', 'In Progress'),
    ('NON_COMPLIANT', 'Non-Compliant'),
    ('NOT_APPLICABLE', 'Not Applicable'),
    ('PENDING', 'Pending Review'),
]

COMPLIANCE_RECURRENCE_CHOICES = [
    ('ONE_TIME', 'One-time'),
    ('ANNUAL', 'Annual'),
    ('QUARTERLY', 'Quarterly'),
    ('MONTHLY', 'Monthly'),
]


class ComplianceItem(models.Model):
    """
    Tracks regulatory compliance items for a school/tenant.
    Examples: Fire Safety NOC, UDISE+ submission, RTE quota compliance.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='compliance_items',
    )
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=20, choices=COMPLIANCE_CATEGORY_CHOICES)
    status = models.CharField(
        max_length=20, choices=COMPLIANCE_STATUS_CHOICES, default='PENDING',
    )
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    responsible_person = models.CharField(max_length=200, blank=True, default='')
    recurrence = models.CharField(
        max_length=20, choices=COMPLIANCE_RECURRENCE_CHOICES, default='ANNUAL',
    )
    notes = models.TextField(blank=True, default='')
    document_url = models.URLField(max_length=500, blank=True, default='')
    reminder_days = models.IntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'compliance_items'
        ordering = ['category', 'due_date']
        unique_together = [('tenant', 'name', 'category')]
        indexes = [
            models.Index(fields=['tenant', 'category']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


# ── Staff Professional Development Tracker ────────────────────────────────

CERT_TYPE_CHOICES = [
    # IB Training
    ('IB_CAT1', 'IB Category 1 Workshop'),
    ('IB_CAT2', 'IB Category 2 Workshop'),
    ('IB_CAT3', 'IB Category 3 Workshop'),
    ('IB_LEADER', 'IB Leadership Workshop'),
    # Safety & Compliance
    ('FIRST_AID', 'First Aid Certification'),
    ('POCSO', 'POCSO Awareness Training'),
    ('POSH', 'POSH (Sexual Harassment Prevention)'),
    ('FIRE_SAFETY', 'Fire Safety Training'),
    ('CHILD_SAFEGUARDING', 'Child Safeguarding'),
    ('CWSN', 'Children with Special Needs Training'),
    ('CPR', 'CPR Certification'),
    ('MENTAL_HEALTH', 'Mental Health First Aid'),
    ('ANTI_BULLYING', 'Anti-Bullying Training'),
    # Professional
    ('BACKGROUND_CHECK', 'Background / Police Verification'),
    ('TEACHING_LICENSE', 'Teaching License'),
    ('SUBJECT_CERT', 'Subject Specialization Certificate'),
    ('DIGITAL_LITERACY', 'Digital Literacy / EdTech Training'),
    ('GOOGLE_CERT', 'Google Certified Educator'),
    ('NEP_TRAINING', 'NEP 2020 Training'),
    ('OTHER', 'Other'),
]

STAFF_CERT_STATUS_CHOICES = [
    ('VALID', 'Valid'),
    ('EXPIRING', 'Expiring Soon'),
    ('EXPIRED', 'Expired'),
    ('NOT_STARTED', 'Not Started'),
]


class StaffCertification(models.Model):
    """
    Tracks individual staff certifications and professional development completions.
    E.g., IB training workshops, first aid, POCSO, teaching licences.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='staff_certifications',
    )
    teacher = models.ForeignKey(
        'users.User', on_delete=models.CASCADE,
        related_name='staff_certifications',
    )
    certification_type = models.CharField(
        max_length=30, choices=CERT_TYPE_CHOICES,
    )
    custom_name = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Custom name if certification_type is OTHER",
    )
    status = models.CharField(
        max_length=20, choices=STAFF_CERT_STATUS_CHOICES, default='NOT_STARTED',
    )
    completed_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    certificate_url = models.URLField(
        blank=True, default='',
        help_text="Link to uploaded certificate file",
    )
    provider = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Training provider or issuing organization",
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'staff_certifications'
        ordering = ['teacher__first_name', 'certification_type']
        unique_together = [('tenant', 'teacher', 'certification_type')]
        indexes = [
            models.Index(fields=['tenant', 'certification_type']),
            models.Index(fields=['tenant', 'teacher']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        label = self.custom_name if self.certification_type == 'OTHER' else self.get_certification_type_display()
        return f"{self.teacher} — {label} ({self.get_status_display()})"
