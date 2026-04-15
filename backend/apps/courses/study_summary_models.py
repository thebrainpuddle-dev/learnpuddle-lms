"""
AI Study Summary models.

StudySummary — Per-student (or per-teacher), per-content AI-generated study
material including summaries, flashcards, key terms, quiz prep questions,
and mind maps.
"""

import uuid

from django.db import models

from utils.tenant_manager import TenantManager


class StudySummary(models.Model):
    """
    AI-generated study summary for a specific content item, owned by a
    student or teacher.

    The summary_data JSONField stores the full generated output:
    {
        "summary": "...",
        "flashcards": [{"front": "...", "back": "..."}],
        "key_terms": [{"term": "...", "definition": "..."}],
        "quiz_prep": [
            {
                "question": "...",
                "answer": "...",
                "type": "mcq|true_false|fill_blank|short_answer",
                "options": [...]
            }
        ],
        "mind_map": {
            "nodes": [{"id": "n1", "label": "...", "type": "core|concept|process|detail", "description": "..."}],
            "edges": [{"source": "n1", "target": "n2", "label": "..."}]
        }
    }
    """

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('GENERATING', 'Generating'),
        ('READY', 'Ready'),
        ('FAILED', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='study_summaries',
    )
    student = models.ForeignKey(
        'users.User',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='study_summaries',
    )
    generated_by = models.ForeignKey(
        'users.User',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='created_study_summaries',
        help_text='Teacher who generated this summary (null for student-generated)',
    )
    is_shared = models.BooleanField(
        default=False,
        help_text='When True, students in the course can see this summary',
    )
    content = models.ForeignKey(
        'courses.Content',
        on_delete=models.CASCADE,
        related_name='study_summaries',
    )

    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='PENDING',
    )
    summary_data = models.JSONField(default=dict, blank=True)
    source_text_hash = models.CharField(
        max_length=64, blank=True, default='',
        help_text='SHA-256 hash of the source text used for generation (cache invalidation)',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'study_summaries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'student']),
            models.Index(fields=['student', 'content']),
            models.Index(fields=['tenant', 'generated_by'],
                         name='study_summ_tenant_genby_idx'),
            models.Index(fields=['content', 'is_shared'],
                         name='study_summ_content_shared_idx'),
        ]

    def __str__(self):
        return f"StudySummary({self.id}) — {self.student} / {self.content}"
