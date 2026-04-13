# apps/progress/skills_models.py

import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from utils.tenant_manager import TenantManager


class Skill(models.Model):
    """
    Represents a competency or skill that can be mapped to courses and teachers.
    Tenant-scoped for multi-tenant isolation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='skills',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    level_required = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Required proficiency level (1-5)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'skills'
        ordering = ['category', 'name']
        unique_together = [('tenant', 'name')]
        indexes = [
            models.Index(fields=['tenant', 'category']),
            models.Index(fields=['tenant', 'name']),
        ]

    def __str__(self):
        return f"{self.name} (L{self.level_required})"


class CourseSkill(models.Model):
    """
    Maps a skill to a course, indicating which skill the course teaches
    and to what proficiency level.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='course_skills',
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name='course_skills',
    )
    level_taught = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Proficiency level this course teaches (1-5)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'course_skills'
        unique_together = [('course', 'skill')]
        indexes = [
            models.Index(fields=['course', 'skill']),
            models.Index(fields=['skill', 'level_taught']),
        ]

    def __str__(self):
        return f"{self.course.title} -> {self.skill.name} (L{self.level_taught})"


class TeacherSkill(models.Model):
    """
    Tracks a teacher's current and target proficiency for a skill.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='teacher_skills',
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name='teacher_skills',
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='teacher_skills',
    )
    current_level = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Current proficiency level (0=not assessed, 1-5)",
    )
    target_level = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Target proficiency level (1-5)",
    )
    last_assessed = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teacher_skills'
        unique_together = [('teacher', 'skill')]
        ordering = ['skill__category', 'skill__name']
        indexes = [
            models.Index(fields=['tenant', 'teacher']),
            models.Index(fields=['tenant', 'skill']),
            models.Index(fields=['teacher', 'current_level']),
        ]

    def __str__(self):
        return f"{self.teacher.email} - {self.skill.name}: L{self.current_level}/L{self.target_level}"

    @property
    def has_gap(self):
        """True if the teacher's current level is below the target."""
        return self.current_level < self.target_level

    @property
    def gap_size(self):
        """Number of levels between current and target (0 if met/exceeded)."""
        return max(0, self.target_level - self.current_level)
