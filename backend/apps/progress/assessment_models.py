# apps/progress/assessment_models.py
#
# Question Bank + Advanced Quizzing models (TASK-043).
#
# Provides reusable question banks, randomized question selection, timed quizzes
# with multiple attempts, and the data-model for a centralized gradebook.

import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from utils.tenant_manager import TenantManager


# ---------------------------------------------------------------------------
# Choice tuples
# ---------------------------------------------------------------------------

QUESTION_TYPE_CHOICES = [
    ("MCQ", "Multiple Choice (single)"),
    ("MULTI", "Multiple Choice (multiple)"),
    ("SHORT", "Short Answer"),
    ("TRUE_FALSE", "True / False"),
    ("ESSAY", "Essay"),
]

DIFFICULTY_CHOICES = [
    ("EASY", "Easy"),
    ("MEDIUM", "Medium"),
    ("HARD", "Hard"),
]

# Quiz-attempt lifecycle
ATTEMPT_STATUS_CHOICES = [
    ("IN_PROGRESS", "In Progress"),
    ("SUBMITTED", "Submitted"),
    ("EXPIRED", "Expired (auto-submit on time-limit)"),
]


# ---------------------------------------------------------------------------
# QuestionBank
# ---------------------------------------------------------------------------

class QuestionBank(models.Model):
    """
    Reusable container of questions, tenant-scoped.

    A quiz can draw its questions either:
      - Directly from authored `QuizQuestion` rows (legacy), OR
      - By referencing one or more `QuestionBank` instances (see
        `QuizConfig.source_question_banks`) and optionally a
        `random_selection_count`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="question_banks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    tags = models.JSONField(
        blank=True, default=list,
        help_text="Freeform tags for filtering (list of strings).",
    )
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="authored_question_banks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "question_banks"
        ordering = ["title"]
        unique_together = [("tenant", "title")]
        indexes = [
            models.Index(fields=["tenant", "title"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self):
        return f"QuestionBank<{self.title}>"


class Question(models.Model):
    """
    A single question belonging to a `QuestionBank`.

    For MCQ / MULTI / TRUE_FALSE, the candidate answers live in
    `QuestionChoice`. For SHORT / ESSAY, `correct_answer` may hold an optional
    reference answer (free-text) used by reviewers.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="bank_questions",
    )
    bank = models.ForeignKey(
        QuestionBank,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    prompt = models.TextField(help_text="Rich-text / markdown prompt.")
    points = models.PositiveIntegerField(default=1)
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default="MEDIUM",
    )
    explanation = models.TextField(blank=True, default="")
    # Reference/canonical answer for SHORT / ESSAY, extra grader metadata, etc.
    metadata = models.JSONField(blank=True, default=dict)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "bank_questions"
        ordering = ["bank", "order", "created_at"]
        indexes = [
            models.Index(fields=["tenant", "bank"]),
            models.Index(fields=["tenant", "question_type"]),
            models.Index(fields=["bank", "order"]),
        ]

    def __str__(self):
        return f"Question<{self.question_type} bank={self.bank_id}>"


class QuestionChoice(models.Model):
    """
    A selectable choice for MCQ / MULTI / TRUE_FALSE questions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices",
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "bank_question_choices"
        ordering = ["question", "order"]
        indexes = [
            models.Index(fields=["question", "order"]),
        ]

    def __str__(self):
        return f"Choice<q={self.question_id} correct={self.is_correct}>"


# ---------------------------------------------------------------------------
# QuizConfig
# ---------------------------------------------------------------------------

class QuizConfig(models.Model):
    """
    Per-quiz configuration, attached to a single `Content` item.

    This is *the* place to configure timing, multiple attempts, shuffling, and
    random selection from question banks for a quiz delivered to a teacher.
    Legacy quizzes keyed off `Assignment` continue to work; this model is
    additive.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="quiz_configs",
    )
    content = models.OneToOneField(
        "courses.Content",
        on_delete=models.CASCADE,
        related_name="quiz_config",
    )

    time_limit_seconds = models.PositiveIntegerField(
        default=0,
        help_text="0 = unlimited. Otherwise, seconds the teacher has to submit.",
    )
    max_attempts = models.PositiveIntegerField(
        default=1,
        help_text="Maximum attempts per teacher. 0 = unlimited.",
    )
    pass_threshold_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=70,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    shuffle_questions = models.BooleanField(default=False)
    shuffle_choices = models.BooleanField(default=False)
    show_correct_answers_after = models.BooleanField(
        default=True,
        help_text="Reveal correct answers after the teacher submits.",
    )
    multi_partial_credit = models.BooleanField(
        default=False,
        help_text=(
            "For MULTI questions: if True, award a proportional fraction of "
            "points (correct_selected - incorrect_selected) / total_correct "
            "clamped to [0, 1]. If False (default), MULTI is all-or-nothing."
        ),
    )
    random_selection_count = models.PositiveIntegerField(
        null=True, blank=True,
        help_text=(
            "If set, randomly select this many questions from the linked "
            "question banks on each attempt. If unset, use all questions."
        ),
    )
    source_question_banks = models.ManyToManyField(
        QuestionBank,
        blank=True,
        related_name="used_by_quiz_configs",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "quiz_configs"
        indexes = [
            models.Index(fields=["tenant", "content"]),
        ]

    def __str__(self):
        return f"QuizConfig<content={self.content_id}>"


# ---------------------------------------------------------------------------
# QuizAttempt
# ---------------------------------------------------------------------------

class QuizAttempt(models.Model):
    """
    A single attempt by a teacher at a quiz (Content).

    - `questions_snapshot` stores the exact questions (and their choices) that
      were rendered for the attempt so that scoring is deterministic even if
      the bank is edited afterwards.
    - `answers` stores teacher responses keyed by question id.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    teacher = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="bank_quiz_attempts",
    )
    content = models.ForeignKey(
        "courses.Content",
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )

    attempt_number = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=ATTEMPT_STATUS_CHOICES, default="IN_PROGRESS",
    )

    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)

    # Snapshot of questions presented + answers given
    questions_snapshot = models.JSONField(blank=True, default=list)
    answers = models.JSONField(blank=True, default=dict)

    score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    max_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    passed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "quiz_attempts"
        ordering = ["-started_at"]
        unique_together = [("teacher", "content", "attempt_number")]
        indexes = [
            models.Index(fields=["tenant", "teacher", "content"]),
            models.Index(fields=["tenant", "content", "status"]),
            models.Index(fields=["tenant", "teacher", "status"]),
            models.Index(fields=["started_at"]),
        ]

    def __str__(self):
        return (
            f"QuizAttempt<teacher={self.teacher_id} content={self.content_id} "
            f"#{self.attempt_number} {self.status}>"
        )

    @property
    def score_percent(self):
        if not self.max_score:
            return 0
        try:
            return float(self.score) / float(self.max_score) * 100.0
        except (TypeError, ZeroDivisionError):
            return 0
