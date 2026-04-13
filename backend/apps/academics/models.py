import uuid
from django.db import models
from utils.tenant_manager import TenantManager


class GradeBand(models.Model):
    """Groups grades into pedagogical stages (e.g. Early Years, Primary, High School)."""

    CURRICULUM_CHOICES = [
        ('REGGIO_EMILIA', 'Reggio Emilia'),
        ('CAMBRIDGE_PRIMARY', 'Cambridge Primary'),
        ('CAMBRIDGE_SECONDARY', 'Cambridge Secondary'),
        ('IGCSE', 'IGCSE'),
        ('KIPP', 'KIPP'),
        ('IB', 'International Baccalaureate'),
        ('CUSTOM', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='grade_bands',
    )
    name = models.CharField(max_length=100, help_text="e.g. Early Years, Primary, High School")
    short_code = models.CharField(max_length=10, help_text="e.g. KEY, PRI, MID, HS")
    order = models.PositiveIntegerField(default=0, help_text="Display order across grade bands")
    curriculum_framework = models.CharField(
        max_length=30, choices=CURRICULUM_CHOICES, default='CUSTOM',
    )
    theme_config = models.JSONField(
        null=True, blank=True, default=None,
        help_text='Optional per-band theming: {"accent_color": "#hex", "bg_image": "url", "welcome_msg": "text"}',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'grade_bands'
        unique_together = [('tenant', 'name')]
        ordering = ['order']
        indexes = [
            models.Index(fields=['tenant', 'order']),
        ]

    def __str__(self):
        return f"{self.name} ({self.short_code})"


class Grade(models.Model):
    """Individual grade/year level within a grade band (e.g. Grade 9, PP1, Nursery)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='grades',
    )
    grade_band = models.ForeignKey(
        GradeBand, on_delete=models.CASCADE, related_name='grades',
    )
    name = models.CharField(max_length=50, help_text="e.g. Nursery, PP1, Grade 9")
    short_code = models.CharField(max_length=10, help_text="e.g. NUR, PP1, G9")
    order = models.PositiveIntegerField(default=0, help_text="Global sort order across all grade bands")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'grades'
        unique_together = [('tenant', 'short_code')]
        ordering = ['order']
        indexes = [
            models.Index(fields=['tenant', 'order']),
            models.Index(fields=['tenant', 'grade_band']),
        ]

    def __str__(self):
        return f"{self.name} ({self.short_code})"


class Section(models.Model):
    """Division within a grade for a specific academic year (e.g. Grade 9-A, 2026-27)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='sections',
    )
    grade = models.ForeignKey(
        Grade, on_delete=models.CASCADE, related_name='sections',
    )
    name = models.CharField(max_length=20, help_text="e.g. A, B, C")
    academic_year = models.CharField(max_length=20, help_text="e.g. 2026-27")
    class_teacher = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='class_teacher_sections',
        help_text="Teacher assigned as class teacher for this section",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'sections'
        unique_together = [('tenant', 'grade', 'name', 'academic_year')]
        ordering = ['grade__order', 'name']
        indexes = [
            models.Index(fields=['tenant', 'academic_year']),
            models.Index(fields=['tenant', 'grade', 'academic_year']),
        ]

    def __str__(self):
        return f"{self.grade.name} - {self.name} ({self.academic_year})"


class Subject(models.Model):
    """Curriculum subject tied to applicable grades (e.g. Physics for G9-G12)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='subjects',
    )
    name = models.CharField(max_length=100, help_text="e.g. Physics, English Language")
    code = models.CharField(max_length=20, help_text="e.g. PHY, ENG")
    department = models.CharField(
        max_length=100, blank=True, default='',
        help_text="e.g. Science, Languages, Commerce",
    )
    applicable_grades = models.ManyToManyField(
        Grade, related_name='subjects', blank=True,
        help_text="Which grades this subject is taught in",
    )
    is_elective = models.BooleanField(default=False, help_text="Is this an elective subject?")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'subjects'
        unique_together = [('tenant', 'code')]
        ordering = ['department', 'name']
        indexes = [
            models.Index(fields=['tenant', 'department']),
            models.Index(fields=['tenant', 'is_elective']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class TeachingAssignment(models.Model):
    """Maps a teacher to the subjects and sections they teach in a given academic year."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='teaching_assignments',
    )
    teacher = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='teaching_assignments',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name='teaching_assignments',
    )
    sections = models.ManyToManyField(
        Section, related_name='teaching_assignments', blank=True,
        help_text="Sections this teacher teaches this subject in",
    )
    academic_year = models.CharField(max_length=20, help_text="e.g. 2026-27")
    is_class_teacher = models.BooleanField(
        default=False,
        help_text="Whether this teacher is the class teacher for assigned sections",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teaching_assignments'
        unique_together = [('tenant', 'teacher', 'subject', 'academic_year')]
        ordering = ['teacher__last_name', 'subject__name']
        indexes = [
            models.Index(fields=['tenant', 'academic_year']),
            models.Index(fields=['tenant', 'teacher', 'academic_year']),
        ]

    def __str__(self):
        return f"{self.teacher.get_full_name()} — {self.subject.name} ({self.academic_year})"
