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
    ('challenge_reward', 'Challenge Reward'),
]


# TASK-018: Mastery Points — competence-based ledger separate from XP (effort).
# Reasons are analogous to XP but only awarded when demonstrated competence
# clears a configured threshold.
MASTERY_POINT_REASON_CHOICES = [
    ('quiz_mastery', 'Quiz Mastery'),
    ('assignment_mastery', 'Assignment Mastery'),
    ('course_mastery_bonus', 'Course Mastery Bonus'),
    ('admin_adjust', 'Admin Adjustment'),
]

BADGE_CATEGORY_CHOICES = [
    ('milestone', 'Milestone'),
    ('streak', 'Streak'),
    ('completion', 'Completion'),
    ('skill', 'Skill'),
    ('special', 'Special'),
    ('social_learning', 'Social Learning'),
]

# Six rarity tiers — ordered by ascending scarcity.
# Used to surface badge prestige in the teacher badge gallery and leaderboard.
BADGE_RARITY_CHOICES = [
    ('common', 'Common'),
    ('uncommon', 'Uncommon'),
    ('rare', 'Rare'),
    ('epic', 'Epic'),
    ('legendary', 'Legendary'),
    ('mythic', 'Mythic'),
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


# Streak freeze token sources (open-ended — new sources can be added without migration).
STREAK_FREEZE_SOURCE_CHOICES = [
    ('streak_milestone', 'Streak Milestone'),
    ('admin_grant', 'Admin Grant'),
    ('challenge_reward', 'Challenge Reward'),
    ('purchase', 'Purchase'),
]

STREAK_FREEZE_LEDGER_EVENT_CHOICES = [
    ('earned', 'Earned'),
    ('spent', 'Spent'),
    ('expired', 'Expired'),
    ('granted', 'Granted'),
    ('revoked', 'Revoked'),
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
        help_text="Max streak freezes per month (legacy monthly counter fallback)",
    )
    grace_period_hours = models.PositiveIntegerField(
        default=24,
        help_text="Hours after a missed day during which activity still counts for the streak.",
    )
    weekend_mode_available = models.BooleanField(
        default=True,
        help_text="Allow teachers to opt into weekend mode (Sat/Sun don't count).",
    )
    freeze_token_earn_every_n_days = models.PositiveIntegerField(
        default=7,
        help_text="Every N consecutive streak days, auto-grant 1 freeze token.",
    )
    freeze_token_expires_days = models.PositiveIntegerField(
        default=90,
        help_text="Token lifetime in days (0 = never expires).",
    )
    freeze_token_max_inventory = models.PositiveIntegerField(
        default=5,
        help_text="Cap on unspent freeze tokens per teacher.",
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
    # --- TASK-016: 10-tier league leaderboards -----------------------------
    leagues_enabled = models.BooleanField(
        default=True,
        help_text="Master switch for the league leaderboard feature.",
    )
    leagues_opt_in_required = models.BooleanField(
        default=False,
        help_text=(
            "If True, teachers must explicitly opt in to leagues (league_opted_out "
            "defaults to True). If False, all non-opted-out teachers are enrolled."
        ),
    )
    league_cohort_size = models.PositiveIntegerField(
        default=30,
        help_text="Target number of teachers per league cohort.",
    )
    league_promote_count = models.PositiveIntegerField(
        default=7,
        help_text="How many top finishers are promoted each week.",
    )
    league_demote_count = models.PositiveIntegerField(
        default=7,
        help_text="How many bottom finishers are demoted each week.",
    )
    # --- TASK-018: Mastery Points tunables ---------------------------------
    mp_quiz_threshold_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=80,
        help_text=(
            "Minimum quiz score percentage (0-100) required to award Mastery "
            "Points. Scores below this threshold award XP only."
        ),
    )
    mp_quiz_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1,
        help_text=(
            "Multiplier applied to quiz score percentage when awarding Mastery "
            "Points. MP = round(score_percent * weight)."
        ),
    )
    mp_assignment_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1,
        help_text=(
            "Multiplier applied to assignment grade (out of max_score) when "
            "awarding Mastery Points. MP = round(score * weight)."
        ),
    )
    mp_assignment_threshold_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=80,
        help_text=(
            "Minimum assignment score percentage (0-100) required to award "
            "Mastery Points on an assignment grade."
        ),
    )
    mp_course_bonus = models.PositiveIntegerField(
        default=50,
        help_text=(
            "Flat Mastery Point bonus awarded on course completion when the "
            "teacher's average quiz score in that course meets the quiz "
            "threshold."
        ),
    )
    # --- TASK-019: Puddle Coin tunables ------------------------------------
    coins_per_level_up = models.PositiveIntegerField(
        default=100,
        help_text="Puddle Coins granted when a teacher gains a level.",
    )
    coins_per_challenge = models.PositiveIntegerField(
        default=25,
        help_text=(
            "Puddle Coins granted on challenge completion (in addition to "
            "any challenge.reward_xp)."
        ),
    )
    coins_per_league_promote = models.PositiveIntegerField(
        default=50,
        help_text=(
            "Puddle Coins granted when a teacher is promoted at the weekly "
            "league close."
        ),
    )
    coins_per_streak_milestone = models.PositiveIntegerField(
        default=20,
        help_text=(
            "Puddle Coins granted every N-day streak milestone (same cadence "
            "as freeze-token grants)."
        ),
    )
    coin_price_streak_freeze = models.PositiveIntegerField(
        default=50,
        help_text="Puddle Coin price to purchase one streak-freeze token.",
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
    league_opted_out = models.BooleanField(
        default=False,
        help_text=(
            "Per-teacher opt-out for the league leaderboard specifically. "
            "Distinct from ``opted_out`` which disables all gamification."
        ),
    )

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
    rarity = models.CharField(
        max_length=20,
        choices=BADGE_RARITY_CHOICES,
        default='common',
        help_text="Prestige tier of this badge. Affects visual treatment in the badge gallery.",
    )
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
        return f"{self.name} [{self.category}/{self.rarity}]"


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
    weekend_mode_enabled = models.BooleanField(
        default=False,
        help_text="If true, Sat/Sun activity is not required to maintain the streak.",
    )
    grace_period_ends_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Streak is in grace state until this time; activity before this auto-recovers.",
    )

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

        Behaviour:
        - Same day: no-op.
        - Consecutive day (gap=1): increment.
        - Weekend-mode teacher with gap spanning only Sat/Sun: increment.
        - Gap of 2 days with active freeze window: preserve streak (use freeze).
        - Gap > 1 day (or no freeze available): reset to 1.

        After updating, if ``current_streak`` is a non-zero multiple of
        ``GamificationConfig.freeze_token_earn_every_n_days``, a streak-freeze
        token is auto-granted (capped by ``freeze_token_max_inventory``).
        """
        today = date or timezone.localdate()

        if self.last_activity_date == today:
            return  # already recorded today

        if self.last_activity_date is not None:
            gap = (today - self.last_activity_date).days
        else:
            gap = None  # first ever activity

        # Weekend mode: if the "missed" days are only weekend days (Sat/Sun),
        # treat the span as consecutive.
        if (
            self.weekend_mode_enabled
            and gap is not None
            and gap > 1
            and _gap_is_only_weekend(self.last_activity_date, today)
        ):
            gap = 1

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

        # Clear grace period when activity is recorded
        self.grace_period_ends_at = None
        self.last_activity_date = today
        self.save(update_fields=[
            'current_streak',
            'longest_streak',
            'last_activity_date',
            'freeze_used_today',
            'grace_period_ends_at',
            'updated_at',
        ])

        # Auto-grant freeze token on streak milestones
        self._maybe_grant_milestone_token()

    def _maybe_grant_milestone_token(self):
        """If current_streak hits a configured milestone, grant a freeze token."""
        if self.current_streak <= 0:
            return
        try:
            config = GamificationConfig.objects.get(tenant=self.tenant)
        except GamificationConfig.DoesNotExist:
            return
        n = config.freeze_token_earn_every_n_days
        if n <= 0 or self.current_streak % n != 0:
            return
        # Import here to avoid circular import at module load time
        from .gamification_engine import earn_streak_freeze_token

        earn_streak_freeze_token(
            self.teacher,
            source='streak_milestone',
            description=f'{self.current_streak}-day streak milestone',
        )

        # TASK-019: Puddle Coins for streak milestone. Granted independently
        # of the freeze token cap — streak discipline always earns coins.
        # Deterministic reference per (teacher, streak_days) via UUIDv5 so
        # re-running the milestone never double-grants.
        try:
            import uuid as _uuid

            from .coin_engine import earn_coins

            ref = _uuid.uuid5(
                _uuid.NAMESPACE_OID,
                f"coin-streak:{self.teacher_id}:{self.current_streak}",
            )
            earn_coins(
                teacher=self.teacher,
                reason='streak_milestone',
                reference_id=ref,
                reference_type='streak_day',
                description=f'{self.current_streak}-day streak milestone',
            )
        except Exception:  # noqa: BLE001
            import logging as _logging
            _logging.getLogger(__name__).exception(
                "earn_coins failed on streak milestone teacher=%s days=%s",
                self.teacher_id, self.current_streak,
            )


def _gap_is_only_weekend(last_date, today):
    """
    Return True if every day in the open interval (last_date, today) is a Sat/Sun.

    I.e. weekend-mode teachers treat Fri→Mon (gap=3) as a no-op gap because the
    intervening Sat + Sun are weekend days.
    """
    if last_date is None or today is None:
        return False
    from datetime import timedelta as _td
    day = last_date + _td(days=1)
    while day < today:
        if day.weekday() < 5:  # 0..4 = Mon..Fri
            return False
        day = day + _td(days=1)
    return True


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


# ---------------------------------------------------------------------------
# 8. StreakFreezeToken
# ---------------------------------------------------------------------------

class StreakFreezeToken(models.Model):
    """
    A single streak-freeze token owned by a teacher.

    Tokens are earnable (streak milestones, admin grants, challenge rewards,
    purchases) and spendable (consume one to cover a missed day and protect
    the streak).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='streak_freeze_tokens',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='streak_freeze_tokens',
    )
    source = models.CharField(
        max_length=30,
        choices=STREAK_FREEZE_SOURCE_CHOICES,
        default='streak_milestone',
    )
    earned_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_id = models.UUIDField(null=True, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'streak_freeze_tokens'
        ordering = ['earned_at']
        indexes = [
            models.Index(fields=['tenant', 'teacher', 'consumed_at']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        state = 'consumed' if self.consumed_at else 'available'
        return f"Token[{state}] teacher={self.teacher_id} source={self.source}"

    def is_expired(self, now=None):
        if self.expires_at is None:
            return False
        return (now or timezone.now()) >= self.expires_at


# ---------------------------------------------------------------------------
# 9. StreakFreezeLedger
# ---------------------------------------------------------------------------

class StreakFreezeLedger(models.Model):
    """
    Immutable audit trail of streak-freeze token events (earn / spend / expire /
    admin grant / admin revoke).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='streak_freeze_ledger',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='streak_freeze_ledger',
    )
    event_type = models.CharField(
        max_length=20,
        choices=STREAK_FREEZE_LEDGER_EVENT_CHOICES,
    )
    token = models.ForeignKey(
        StreakFreezeToken,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ledger_entries',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    balance_after = models.PositiveIntegerField(
        default=0,
        help_text="Cached inventory count of unconsumed, unexpired tokens after this event.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'streak_freeze_ledger'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'teacher', 'created_at']),
            models.Index(fields=['tenant', 'event_type']),
        ]

    def __str__(self):
        return (
            f"Ledger[{self.event_type}] teacher={self.teacher_id} "
            f"balance={self.balance_after}"
        )


# ---------------------------------------------------------------------------
# 10. MasteryPointTransaction (TASK-018)
# ---------------------------------------------------------------------------

class MasteryPointTransaction(models.Model):
    """
    Immutable ledger of Mastery Point awards. Mastery Points (MP) measure
    demonstrated competence (quiz score, assignment grade, course mastery),
    in contrast to XP which measures effort. Separate ledger so the two
    currencies stay independent and can evolve separately.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='mastery_point_transactions',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='mastery_point_transactions',
    )
    # Decimal precision because MP can be computed from decimal scores.
    # Negative amounts allowed for admin adjustments / corrections.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=50, choices=MASTERY_POINT_REASON_CHOICES)
    description = models.CharField(max_length=255, blank=True, default='')
    reference_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID of related object (submission, course, etc.)",
    )
    reference_type = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Type of related object",
    )
    # Future hook: tie a MP award to a skill/competency for granular mastery
    # reporting. Kept nullable so this migration stays additive.
    skill_code = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text=(
            "Optional skill/competency identifier for future per-skill "
            "mastery aggregation."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'mastery_point_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'teacher']),
            models.Index(fields=['tenant', 'teacher', 'reason']),
            models.Index(fields=['tenant', 'teacher', 'skill_code']),
            models.Index(fields=['created_at']),
        ]
        # Dedup: for a (reason, reference_type, reference_id) triple, allow
        # at most one transaction per teacher. This enforces idempotency at
        # the database level and lets the engine remain a simple create.
        constraints = [
            models.UniqueConstraint(
                fields=['teacher', 'reason', 'reference_type', 'reference_id'],
                condition=models.Q(reference_id__isnull=False),
                name='uniq_mp_txn_per_reference',
            ),
        ]

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.teacher_id} {sign}{self.amount}MP ({self.reason})"


# ---------------------------------------------------------------------------
# 11. TeacherMasterySummary (TASK-018)
# ---------------------------------------------------------------------------

class TeacherMasterySummary(models.Model):
    """
    Denormalized cache of a teacher's total Mastery Points.
    Updated by the mastery engine after each transaction.

    Kept as a separate summary (rather than extending TeacherXPSummary)
    because (a) MP has its own aggregation semantics distinct from XP/level,
    (b) per-skill aggregation is a near-term extension, and (c) this keeps
    the XP summary focused on effort/level mechanics.

    Opt-out respects the parent TeacherXPSummary.opted_out flag so teachers
    don't have two separate opt-outs for the same gamification stack.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='teacher_mastery_summaries',
    )
    teacher = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='mastery_summary',
    )
    total_mastery_points = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    mp_this_month = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    mp_this_week = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    last_mp_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teacher_mastery_summaries'
        indexes = [
            models.Index(fields=['tenant', 'total_mastery_points']),
        ]

    def __str__(self):
        return f"{self.teacher_id} MP={self.total_mastery_points}"

    def refresh_from_transactions(self):
        """Recalculate totals from the MasteryPointTransaction ledger."""
        from datetime import timedelta as _td
        from decimal import Decimal

        now = timezone.now()

        agg = MasteryPointTransaction.all_objects.filter(
            teacher=self.teacher,
        ).aggregate(total=Sum('amount'))
        raw_total = agg['total'] or Decimal('0')
        # Clamp to zero floor — negative adjustments can't push the summary
        # below zero display-wise even though individual entries keep the
        # true ledger signed.
        self.total_mastery_points = max(Decimal('0'), raw_total)

        week_ago = now - _td(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        week_agg = MasteryPointTransaction.all_objects.filter(
            teacher=self.teacher, created_at__gte=week_ago,
        ).aggregate(total=Sum('amount'))
        self.mp_this_week = max(Decimal('0'), week_agg['total'] or Decimal('0'))

        month_agg = MasteryPointTransaction.all_objects.filter(
            teacher=self.teacher, created_at__gte=month_start,
        ).aggregate(total=Sum('amount'))
        self.mp_this_month = max(Decimal('0'), month_agg['total'] or Decimal('0'))

        self.save(update_fields=[
            'total_mastery_points', 'mp_this_week', 'mp_this_month',
            'updated_at',
        ])


# ---------------------------------------------------------------------------
# 12. CoinTransaction (TASK-019 — Puddle Coins)
# ---------------------------------------------------------------------------

COIN_REASON_CHOICES = [
    ('level_up', 'Level Up'),
    ('challenge_reward', 'Challenge Reward'),
    ('league_promote', 'League Promotion'),
    ('streak_milestone', 'Streak Milestone'),
    ('admin_adjust', 'Admin Adjustment'),
    ('purchase_streak_freeze', 'Purchase Streak Freeze'),
    ('purchase_other', 'Purchase Other'),
]


class CoinTransaction(models.Model):
    """
    Immutable ledger of Puddle Coin earns and spends. Positive ``amount``
    means the teacher earned coins; negative ``amount`` means they spent.

    Earn rows are idempotent at the DB level via a unique partial constraint
    on ``(teacher, reason, reference_type, reference_id)`` when
    ``amount > 0``. Spends share no such constraint and may repeat (e.g.
    multiple freeze-token purchases against the same tenant config row).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='coin_transactions',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='coin_transactions',
    )
    amount = models.IntegerField()  # Signed: + earn, - spend.
    reason = models.CharField(max_length=50, choices=COIN_REASON_CHOICES)
    description = models.CharField(max_length=255, blank=True, default='')
    reference_id = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "ID of the related object (challenge, league, token, etc.)."
        ),
    )
    reference_type = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Type of related object.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'coin_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'teacher']),
            models.Index(fields=['tenant', 'teacher', 'reason']),
            models.Index(fields=['created_at']),
        ]
        # EARN idempotency: only positive amounts with a reference_id are
        # deduplicated. Spends (amount<0) may repeat freely.
        constraints = [
            models.UniqueConstraint(
                fields=['teacher', 'reason', 'reference_type', 'reference_id'],
                condition=models.Q(amount__gt=0, reference_id__isnull=False),
                name='uniq_coin_earn_per_reference',
            ),
        ]

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.teacher_id} {sign}{self.amount} coins ({self.reason})"


# ---------------------------------------------------------------------------
# 13. TeacherCoinBalance (TASK-019)
# ---------------------------------------------------------------------------

class TeacherCoinBalance(models.Model):
    """
    Denormalized cache of a teacher's Puddle Coin balance so reads don't
    re-sum the ledger. Authoritative write path is
    ``apps.progress.coin_engine.spend_coins`` /
    ``apps.progress.coin_engine.earn_coins`` (both update this row), with a
    post_save safety-net on ``CoinTransaction`` for direct ORM writes (admin,
    imports).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='teacher_coin_balances',
    )
    teacher = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='coin_balance',
    )
    balance = models.PositiveIntegerField(default=0)
    lifetime_earned = models.PositiveIntegerField(default=0)
    lifetime_spent = models.PositiveIntegerField(default=0)
    last_txn_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teacher_coin_balances'
        indexes = [
            models.Index(fields=['tenant', 'balance']),
        ]

    def __str__(self):
        return f"{self.teacher_id} balance={self.balance}"

    def recompute_from_transactions(self):
        """Rebuild the cached counters from the ledger (idempotent)."""
        agg = CoinTransaction.all_objects.filter(
            teacher=self.teacher,
        ).aggregate(total=Sum('amount'))
        raw = agg['total'] or 0

        earned_agg = CoinTransaction.all_objects.filter(
            teacher=self.teacher, amount__gt=0,
        ).aggregate(total=Sum('amount'))
        spent_agg = CoinTransaction.all_objects.filter(
            teacher=self.teacher, amount__lt=0,
        ).aggregate(total=Sum('amount'))

        self.balance = max(0, raw)
        self.lifetime_earned = earned_agg['total'] or 0
        # spent aggregate is <= 0; store absolute value.
        self.lifetime_spent = -(spent_agg['total'] or 0)
        self.save(update_fields=[
            'balance', 'lifetime_earned', 'lifetime_spent', 'updated_at',
        ])
