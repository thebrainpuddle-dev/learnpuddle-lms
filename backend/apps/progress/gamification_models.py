# apps/progress/gamification_models.py

import uuid

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from utils.tenant_manager import TenantManager

from .gamification import BADGE_LEVELS


# ---------------------------------------------------------------------------
# Choice tuples
# ---------------------------------------------------------------------------

XP_REASON_CHOICES = [
    ('content_completion', 'Content Completion'),
    ('course_completion', 'Course Completion'),
    ('assignment_submission', 'Assignment Submission'),
    ('quiz_submission', 'Quiz Submission'),
    ('lesson_reflection', 'Lesson Reflection'),
    ('streak_bonus', 'Streak Bonus'),
    ('badge_award', 'Badge Award'),
    ('admin_adjust', 'Admin Adjustment'),
    ('quest_reward', 'Quest Reward'),
]

BADGE_CATEGORY_CHOICES = [
    ('milestone', 'Milestone'),
    ('streak', 'Streak'),
    ('completion', 'Completion'),
    ('skill', 'Skill'),
    ('special', 'Special'),
]

BADGE_CRITERIA_CHOICES = [
    ('xp_threshold', 'XP Threshold'),
    ('courses_completed', 'Courses Completed'),
    ('streak_days', 'Streak Days'),
    ('content_completed', 'Content Completed'),
    ('manual', 'Manual'),
]

LEADERBOARD_PERIOD_CHOICES = [
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
    ('all_time', 'All Time'),
]


# ---------------------------------------------------------------------------
# 1. GamificationConfig
# ---------------------------------------------------------------------------

class GamificationConfig(models.Model):
    """
    Tenant-level configuration for the XP / gamification system.
    One row per tenant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='gamification_config',
    )
    xp_per_content_completion = models.PositiveIntegerField(default=10)
    xp_per_course_completion = models.PositiveIntegerField(default=50)
    xp_per_assignment_submission = models.PositiveIntegerField(default=15)
    xp_per_quiz_submission = models.PositiveIntegerField(default=15)
    xp_per_lesson_reflection = models.PositiveIntegerField(default=5)
    xp_per_streak_day = models.PositiveIntegerField(default=2)
    streak_freeze_max = models.PositiveIntegerField(
        default=2,
        help_text="Max streak freezes per month",
    )
    leaderboard_enabled = models.BooleanField(default=True)
    leaderboard_anonymize = models.BooleanField(
        default=False,
        help_text="Show initials instead of names",
    )
    opt_out_allowed = models.BooleanField(
        default=True,
        help_text="Allow teachers to opt out of gamification",
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gamification_config'

    def __str__(self):
        return f"GamificationConfig ({self.tenant_id})"


# ---------------------------------------------------------------------------
# 2. XPTransaction
# ---------------------------------------------------------------------------

class XPTransaction(models.Model):
    """
    Immutable ledger of all XP awards and deductions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='xp_transactions',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='xp_transactions',
    )
    xp_amount = models.IntegerField()  # Can be negative for deductions
    reason = models.CharField(max_length=50, choices=XP_REASON_CHOICES)
    description = models.CharField(max_length=255, blank=True, default='')
    reference_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID of related object (content, course, etc.)",
    )
    reference_type = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Type of related object",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'xp_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'teacher']),
            models.Index(fields=['tenant', 'teacher', 'reason']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        sign = '+' if self.xp_amount >= 0 else ''
        return f"{self.teacher_id} {sign}{self.xp_amount}XP ({self.reason})"


# ---------------------------------------------------------------------------
# 3. TeacherXPSummary
# ---------------------------------------------------------------------------

class TeacherXPSummary(models.Model):
    """
    Denormalized cache of a teacher's total XP, level, and period totals.
    Updated by signals / periodic tasks.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='teacher_xp_summaries',
    )
    teacher = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='xp_summary',
    )
    total_xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    level_name = models.CharField(max_length=100, default='Associate Educator')
    xp_this_month = models.PositiveIntegerField(default=0)
    xp_this_week = models.PositiveIntegerField(default=0)
    last_xp_at = models.DateTimeField(null=True, blank=True)
    opted_out = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teacher_xp_summaries'
        indexes = [
            models.Index(fields=['tenant', 'total_xp']),
            models.Index(fields=['tenant', 'level']),
        ]

    def __str__(self):
        return f"{self.teacher_id} L{self.level} ({self.total_xp}XP)"

    def refresh_from_transactions(self):
        """Recalculate total_xp, period totals, and level from the XPTransaction ledger."""
        from datetime import timedelta as _td

        now = timezone.now()

        agg = XPTransaction.all_objects.filter(
            teacher=self.teacher,
        ).aggregate(total=Sum('xp_amount'))
        raw_total = agg['total'] or 0
        self.total_xp = max(0, raw_total)

        # Period XP: this week (last 7 days) and this month (calendar month)
        week_ago = now - _td(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        week_agg = XPTransaction.all_objects.filter(
            teacher=self.teacher, created_at__gte=week_ago,
        ).aggregate(total=Sum('xp_amount'))
        self.xp_this_week = max(0, week_agg['total'] or 0)

        month_agg = XPTransaction.all_objects.filter(
            teacher=self.teacher, created_at__gte=month_start,
        ).aggregate(total=Sum('xp_amount'))
        self.xp_this_month = max(0, month_agg['total'] or 0)

        # Derive level / level_name from BADGE_LEVELS
        current = BADGE_LEVELS[0]
        for badge in BADGE_LEVELS:
            max_pts = badge['max_points']
            if max_pts is None and self.total_xp >= badge['min_points']:
                current = badge
            elif max_pts is not None and badge['min_points'] <= self.total_xp <= max_pts:
                current = badge
        self.level = current['level']
        self.level_name = current['name']
        self.save(update_fields=[
            'total_xp', 'xp_this_week', 'xp_this_month',
            'level', 'level_name', 'updated_at',
        ])


# ---------------------------------------------------------------------------
# 4. BadgeDefinition
# ---------------------------------------------------------------------------

class BadgeDefinition(models.Model):
    """
    Admin-defined badges (achievements) that can be awarded to teachers.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='badge_definitions',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    icon = models.CharField(
        max_length=50,
        default='star',
        help_text="Icon identifier for the frontend",
    )
    color = models.CharField(
        max_length=7,
        default='#6C63FF',
        help_text="Hex color",
    )
    category = models.CharField(max_length=50, choices=BADGE_CATEGORY_CHOICES)
    criteria_type = models.CharField(max_length=50, choices=BADGE_CRITERIA_CHOICES)
    criteria_value = models.PositiveIntegerField(
        default=0,
        help_text="Threshold value for auto-award",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'badge_definitions'
        ordering = ['sort_order', 'name']
        unique_together = [('tenant', 'name')]

    def __str__(self):
        return f"{self.name} [{self.category}]"


# ---------------------------------------------------------------------------
# 5. TeacherBadge
# ---------------------------------------------------------------------------

class TeacherBadge(models.Model):
    """
    M2M through-model linking teachers to earned badges.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='teacher_badges',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='badges',
    )
    badge = models.ForeignKey(
        BadgeDefinition,
        on_delete=models.CASCADE,
        related_name='awards',
    )
    awarded_at = models.DateTimeField(auto_now_add=True)
    awarded_reason = models.CharField(max_length=255, blank=True, default='')

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teacher_badges'
        unique_together = [('teacher', 'badge')]
        ordering = ['-awarded_at']

    def __str__(self):
        return f"{self.teacher_id} -> {self.badge.name}"


# ---------------------------------------------------------------------------
# 6. TeacherStreak
# ---------------------------------------------------------------------------

class TeacherStreak(models.Model):
    """
    Tracks daily streak state per teacher.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='teacher_streaks',
    )
    teacher = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='streak',
    )
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)
    freeze_count_this_month = models.PositiveIntegerField(default=0)
    freeze_used_today = models.BooleanField(default=False)
    streak_frozen_until = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teacher_streaks'
        indexes = [
            models.Index(fields=['tenant', 'current_streak']),
        ]

    def __str__(self):
        return f"{self.teacher_id} streak={self.current_streak}"

    def record_activity(self, date=None):
        """
        Update streak based on incoming activity date.

        - Same day: no-op.
        - Consecutive day: increment.
        - Gap of 1 day with active freeze: preserve streak (use freeze).
        - Gap > 1 day (or no freeze available): reset to 1.
        """
        today = date or timezone.localdate()

        if self.last_activity_date == today:
            return  # already recorded today

        if self.last_activity_date is not None:
            gap = (today - self.last_activity_date).days
        else:
            gap = None  # first ever activity

        if gap == 1:
            # Consecutive day
            self.current_streak += 1
        elif gap == 2 and self.streak_frozen_until and self.streak_frozen_until >= today:
            # One missed day covered by an active freeze
            self.current_streak += 1
            self.freeze_used_today = True
        elif gap is None:
            # First activity ever
            self.current_streak = 1
        else:
            # Gap too large or no freeze -- reset
            self.current_streak = 1

        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak

        self.last_activity_date = today
        self.save(update_fields=[
            'current_streak',
            'longest_streak',
            'last_activity_date',
            'freeze_used_today',
            'updated_at',
        ])


# ---------------------------------------------------------------------------
# 7. LeaderboardSnapshot
# ---------------------------------------------------------------------------

class LeaderboardSnapshot(models.Model):
    """
    Periodic snapshots for leaderboard display.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='leaderboard_snapshots',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='leaderboard_entries',
    )
    period = models.CharField(max_length=10, choices=LEADERBOARD_PERIOD_CHOICES)
    rank = models.PositiveIntegerField()
    xp_total = models.PositiveIntegerField(default=0)
    xp_period = models.PositiveIntegerField(
        default=0,
        help_text="XP earned in this period",
    )
    snapshot_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'leaderboard_snapshots'
        ordering = ['-snapshot_date', 'rank']
        unique_together = [('tenant', 'teacher', 'period', 'snapshot_date')]
        indexes = [
            models.Index(fields=['tenant', 'period', 'snapshot_date', 'rank']),
        ]

    def __str__(self):
        return f"#{self.rank} {self.teacher_id} ({self.period} {self.snapshot_date})"
