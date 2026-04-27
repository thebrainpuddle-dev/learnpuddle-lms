# apps/progress/rubric_models.py
#
# TASK-044 — Rubric-based grading models.
#
# A Rubric is a tenant-scoped grading template composed of Criteria
# (distinct dimensions being evaluated) × Levels (descriptors with points)
# per criterion.  An Assignment may have an optional Rubric attached; when
# an evaluator grades a submission they produce a RubricEvaluation which
# captures the level/points chosen for each criterion plus optional comments.

import uuid

from django.core.validators import MinValueValidator
from django.db import models

from utils.tenant_manager import TenantManager


class Rubric(models.Model):
    """
    A reusable grading rubric, tenant-scoped.

    `total_points` is derived from the sum of `RubricCriterion.max_points`
    and is recomputed whenever criteria are added/updated/deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='rubrics',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')

    # Cached sum of criterion max_points. Kept in sync by serializer / service code.
    total_points = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Sum of the max_points of every RubricCriterion.",
    )

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rubrics_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'rubrics'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['tenant', 'title']),
        ]

    def __str__(self):
        return f"{self.title} ({self.total_points} pts)"

    def recompute_total_points(self, save: bool = True):
        """Recompute total_points from the sum of child criteria."""
        agg = self.criteria.aggregate(total=models.Sum('max_points'))
        self.total_points = agg['total'] or 0
        if save:
            self.save(update_fields=['total_points', 'updated_at'])
        return self.total_points


class RubricCriterion(models.Model):
    """A single dimension being evaluated within a rubric."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rubric = models.ForeignKey(
        Rubric,
        on_delete=models.CASCADE,
        related_name='criteria',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    max_points = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rubric_criteria'
        ordering = ['rubric', 'order', 'created_at']
        indexes = [
            models.Index(fields=['rubric', 'order']),
        ]

    def __str__(self):
        return f"{self.title} ({self.max_points})"


class RubricLevel(models.Model):
    """A discrete level within a criterion (e.g. Exemplary / Proficient / …)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criterion = models.ForeignKey(
        RubricCriterion,
        on_delete=models.CASCADE,
        related_name='levels',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    points = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rubric_levels'
        ordering = ['criterion', 'order', '-points']
        indexes = [
            models.Index(fields=['criterion', 'order']),
        ]

    def __str__(self):
        return f"{self.title} ({self.points})"


class RubricEvaluation(models.Model):
    """An evaluator's scoring of a single AssignmentSubmission against a Rubric."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='rubric_evaluations',
    )
    submission = models.ForeignKey(
        'progress.AssignmentSubmission',
        on_delete=models.CASCADE,
        related_name='rubric_evaluations',
    )
    rubric = models.ForeignKey(
        Rubric,
        on_delete=models.PROTECT,
        related_name='evaluations',
        help_text="Snapshot: the rubric used at grading time.",
    )
    evaluator = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rubric_evaluations',
    )

    # scores: dict mapping {criterion_id: {"level_id": str, "points": number, "comment": str}}
    scores = models.JSONField(default=dict, blank=True)
    total_score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Server-computed: sum of per-criterion points in `scores`.",
    )
    feedback = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'rubric_evaluations'
        ordering = ['-created_at']
        # One evaluation per (submission, evaluator) — re-grading updates in place.
        unique_together = [('submission', 'evaluator')]
        indexes = [
            models.Index(fields=['tenant', 'submission']),
            models.Index(fields=['tenant', 'rubric']),
            models.Index(fields=['tenant', 'evaluator']),
        ]

    def __str__(self):
        return f"Evaluation({self.submission_id}, {self.total_score})"
