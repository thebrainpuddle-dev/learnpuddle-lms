# apps/progress/challenge_models.py
#
# TASK-017 — Daily / Weekly Challenges.
#
# Tenant-scoped, admin-authored, time-bounded goal-based activities.
# On completion the teacher earns XP (always) + an optional badge
# (reuses the existing XP/badge engines — no parallel reward path).

import uuid

from django.db import models
from django.utils import timezone

from utils.tenant_manager import TenantManager


CHALLENGE_TYPE_CHOICES = [
    ("DAILY", "Daily"),
    ("WEEKLY", "Weekly"),
]

CHALLENGE_GOAL_CHOICES = [
    ("complete_lessons", "Complete N Lessons"),
    ("earn_xp", "Earn N XP"),
    ("finish_course", "Finish a Specific Course"),
    ("maintain_streak", "Maintain N-Day Streak"),
    ("submit_assignments", "Submit N Assignments"),
]


class Challenge(models.Model):
    """
    An admin-authored challenge that teachers in a tenant can complete.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="challenges",
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")

    challenge_type = models.CharField(
        max_length=10,
        choices=CHALLENGE_TYPE_CHOICES,
        default="DAILY",
    )
    goal_type = models.CharField(
        max_length=30,
        choices=CHALLENGE_GOAL_CHOICES,
    )
    goal_target = models.PositiveIntegerField(
        default=1,
        help_text="Target value the teacher must hit to complete this challenge.",
    )
    goal_reference_id = models.UUIDField(
        null=True, blank=True,
        help_text=(
            "Optional reference target — e.g. the Course id for "
            "goal_type=finish_course."
        ),
    )

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    reward_xp = models.PositiveIntegerField(default=0)
    reward_badge = models.ForeignKey(
        "progress.BadgeDefinition",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="challenge_rewards",
    )

    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_challenges",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "progress_challenges"
        ordering = ["-start_at"]
        indexes = [
            models.Index(fields=["tenant", "is_active", "end_at"]),
            models.Index(fields=["tenant", "challenge_type"]),
        ]

    def __str__(self):
        return f"Challenge[{self.challenge_type}:{self.goal_type}] {self.title}"

    def is_active_now(self, now=None) -> bool:
        """True if the challenge is currently within its active window."""
        now = now or timezone.now()
        return (
            self.is_active
            and self.start_at <= now <= self.end_at
        )


class ChallengeParticipation(models.Model):
    """
    A teacher's progress on a single challenge.

    One row per (challenge, teacher). Progress is advanced by
    ``challenge_engine.record_event`` with an idempotent dedup key.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="challenge_participations",
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    teacher = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="challenge_participations",
    )
    progress_value = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    reward_issued = models.BooleanField(default=False)

    last_reference_key = models.CharField(
        max_length=120,
        blank=True, default="",
        help_text="Last reference_type:reference_id key used for increment.",
    )
    increments_log = models.JSONField(
        default=list, blank=True,
        help_text="Bounded list of recent {ref_key, value, ts} increments.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "progress_challenge_participations"
        constraints = [
            models.UniqueConstraint(
                fields=["challenge", "teacher"],
                name="uniq_challenge_participation_per_teacher",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "teacher", "completed_at"]),
            models.Index(fields=["tenant", "challenge"]),
        ]

    def __str__(self):
        return (
            f"Participation teacher={self.teacher_id} "
            f"challenge={self.challenge_id} "
            f"progress={self.progress_value}/{self.challenge.goal_target}"
        )

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
