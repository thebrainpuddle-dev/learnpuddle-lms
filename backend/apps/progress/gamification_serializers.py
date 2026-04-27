# apps/progress/gamification_serializers.py

from rest_framework import serializers

from .gamification_models import (
    BadgeDefinition,
    CoinTransaction,
    GamificationConfig,
    MasteryPointTransaction,
    StreakFreezeLedger,
    StreakFreezeToken,
    TeacherBadge,
    TeacherCoinBalance,
    TeacherMasterySummary,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)


class GamificationConfigSerializer(serializers.ModelSerializer):
    """Read/write serializer for GamificationConfig.

    Exposes all tunable fields so the Admin Gamification page can configure
    XP rates, streak freeze behaviour, mastery points weights, and coin
    prices without shell access.
    """

    class Meta:
        model = GamificationConfig
        fields = [
            'id',
            # XP per action
            'xp_per_content_completion', 'xp_per_course_completion',
            'xp_per_assignment_submission', 'xp_per_quiz_submission',
            'xp_per_lesson_reflection', 'xp_per_streak_day',
            # Streak freeze (TASK-015)
            'streak_freeze_max', 'grace_period_hours', 'weekend_mode_available',
            'freeze_token_earn_every_n_days', 'freeze_token_expires_days',
            'freeze_token_max_inventory',
            # Leaderboard
            'leaderboard_enabled', 'leaderboard_anonymize', 'opt_out_allowed',
            # Leagues (TASK-016)
            'leagues_enabled', 'leagues_opt_in_required', 'league_cohort_size',
            'league_promote_count', 'league_demote_count',
            # Mastery Points tunables (TASK-018)
            'mp_quiz_threshold_percent', 'mp_quiz_weight',
            'mp_assignment_threshold_percent', 'mp_assignment_weight',
            'mp_course_bonus',
            # Puddle Coin tunables (TASK-019)
            'coins_per_level_up', 'coins_per_challenge', 'coins_per_league_promote',
            'coins_per_streak_milestone', 'coin_price_streak_freeze',
            # Meta
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BadgeDefinitionSerializer(serializers.ModelSerializer):
    """Read serializer for BadgeDefinition."""

    class Meta:
        model = BadgeDefinition
        fields = [
            'id', 'name', 'description', 'icon', 'color', 'category', 'rarity',
            'criteria_type', 'criteria_value', 'is_active', 'sort_order',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BadgeDefinitionCreateSerializer(serializers.ModelSerializer):
    """Create/update serializer for BadgeDefinition."""

    class Meta:
        model = BadgeDefinition
        fields = [
            'name', 'description', 'icon', 'color', 'category', 'rarity',
            'criteria_type', 'criteria_value', 'is_active', 'sort_order',
        ]


class XPTransactionSerializer(serializers.ModelSerializer):
    """Read serializer for XPTransaction."""

    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.SerializerMethodField()

    class Meta:
        model = XPTransaction
        fields = [
            'id', 'teacher', 'teacher_name', 'teacher_email', 'xp_amount',
            'reason', 'description', 'reference_id', 'reference_type', 'created_at',
        ]

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.email

    def get_teacher_email(self, obj):
        return obj.teacher.email


class XPAdjustSerializer(serializers.Serializer):
    """Serializer for admin XP adjustment."""

    teacher_id = serializers.UUIDField()
    xp_amount = serializers.IntegerField()
    reason = serializers.CharField(max_length=255, required=False, default='Admin adjustment')


class LeaderboardEntrySerializer(serializers.Serializer):
    """Serializer for leaderboard entries (computed, not model-backed)."""

    rank = serializers.IntegerField()
    teacher_id = serializers.UUIDField()
    teacher_name = serializers.CharField()
    teacher_email = serializers.CharField()
    total_xp = serializers.IntegerField()
    xp_period = serializers.IntegerField()
    level = serializers.IntegerField()
    level_name = serializers.CharField()
    badge_count = serializers.IntegerField()
    current_streak = serializers.IntegerField()


class TeacherBadgeSerializer(serializers.ModelSerializer):
    """Read serializer for TeacherBadge with nested badge definition."""

    badge = BadgeDefinitionSerializer(read_only=True)

    class Meta:
        model = TeacherBadge
        fields = ['id', 'badge', 'awarded_at', 'awarded_reason']


class TeacherXPSummarySerializer(serializers.ModelSerializer):
    """Read serializer for TeacherXPSummary with computed fields."""

    badges = serializers.SerializerMethodField()
    current_streak = serializers.SerializerMethodField()
    longest_streak = serializers.SerializerMethodField()
    next_level_xp = serializers.SerializerMethodField()
    xp_to_next_level = serializers.SerializerMethodField()

    class Meta:
        model = TeacherXPSummary
        fields = [
            'total_xp', 'level', 'level_name', 'xp_this_month', 'xp_this_week',
            'current_streak', 'longest_streak', 'last_xp_at', 'opted_out',
            'badges', 'next_level_xp', 'xp_to_next_level',
        ]

    def get_badges(self, obj):
        teacher_badges = TeacherBadge.all_objects.filter(
            teacher=obj.teacher,
        ).select_related('badge')
        return TeacherBadgeSerializer(teacher_badges, many=True).data

    def get_current_streak(self, obj):
        try:
            return obj.teacher.streak.current_streak
        except TeacherStreak.DoesNotExist:
            return 0

    def get_longest_streak(self, obj):
        try:
            return obj.teacher.streak.longest_streak
        except TeacherStreak.DoesNotExist:
            return 0

    def get_next_level_xp(self, obj):
        from .gamification import BADGE_LEVELS

        for badge in BADGE_LEVELS:
            if badge['min_points'] > obj.total_xp:
                return badge['min_points']
        return None  # Already at max level

    def get_xp_to_next_level(self, obj):
        next_xp = self.get_next_level_xp(obj)
        if next_xp is None:
            return 0
        return max(0, next_xp - obj.total_xp)


# ---------------------------------------------------------------------------
# Streak-freeze token serializers
# ---------------------------------------------------------------------------


class StreakFreezeTokenSerializer(serializers.ModelSerializer):
    """Read serializer for StreakFreezeToken."""

    class Meta:
        model = StreakFreezeToken
        fields = [
            'id', 'source', 'earned_at', 'consumed_at', 'expires_at',
            'reference_type', 'reference_id',
        ]
        read_only_fields = fields


class StreakFreezeLedgerSerializer(serializers.ModelSerializer):
    """Read serializer for StreakFreezeLedger entries."""

    class Meta:
        model = StreakFreezeLedger
        fields = [
            'id', 'event_type', 'token', 'description', 'balance_after',
            'created_at',
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Mastery Point serializers (TASK-018)
# ---------------------------------------------------------------------------


class MasteryPointTransactionSerializer(serializers.ModelSerializer):
    """Read serializer for MasteryPointTransaction."""

    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.SerializerMethodField()

    class Meta:
        model = MasteryPointTransaction
        fields = [
            'id', 'teacher', 'teacher_name', 'teacher_email', 'amount',
            'reason', 'description', 'reference_id', 'reference_type',
            'skill_code', 'created_at',
        ]

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.email

    def get_teacher_email(self, obj):
        return obj.teacher.email


class TeacherMasterySummarySerializer(serializers.ModelSerializer):
    """Read serializer for TeacherMasterySummary."""

    teacher_id = serializers.UUIDField(source='teacher.id', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.CharField(source='teacher.email', read_only=True)

    class Meta:
        model = TeacherMasterySummary
        fields = [
            'teacher_id', 'teacher_name', 'teacher_email',
            'total_mastery_points', 'mp_this_month', 'mp_this_week',
            'last_mp_at',
        ]
        read_only_fields = fields

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.email


class MasteryLeaderboardEntrySerializer(serializers.Serializer):
    """Serializer for admin mastery leaderboard entries."""

    rank = serializers.IntegerField()
    teacher_id = serializers.UUIDField()
    teacher_name = serializers.CharField()
    teacher_email = serializers.CharField()
    total_mastery_points = serializers.DecimalField(max_digits=12, decimal_places=2)
    mp_this_week = serializers.DecimalField(max_digits=12, decimal_places=2)
    mp_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)


# ---------------------------------------------------------------------------
# Puddle Coin serializers (TASK-019)
# ---------------------------------------------------------------------------


class CoinTransactionSerializer(serializers.ModelSerializer):
    """Read serializer for CoinTransaction (earn + spend rows)."""

    class Meta:
        model = CoinTransaction
        fields = [
            'id', 'teacher', 'amount', 'reason', 'description',
            'reference_id', 'reference_type', 'created_at',
        ]
        read_only_fields = fields


class TeacherCoinBalanceSerializer(serializers.ModelSerializer):
    """Read serializer for TeacherCoinBalance.

    Includes ``price_streak_freeze`` so the frontend Shop card can display the
    live server-configured price instead of a hard-coded constant.  The value
    comes from ``GamificationConfig.coin_price_streak_freeze`` and updates
    automatically whenever an admin changes the config — no frontend release
    needed.
    """

    teacher_id = serializers.UUIDField(source='teacher.id', read_only=True)
    price_streak_freeze = serializers.SerializerMethodField()

    class Meta:
        model = TeacherCoinBalance
        fields = [
            'teacher_id', 'balance', 'lifetime_earned', 'lifetime_spent',
            'last_txn_at', 'updated_at', 'price_streak_freeze',
        ]
        read_only_fields = fields

    def get_price_streak_freeze(self, obj) -> int:
        """Return the current Puddle Coin price for one streak-freeze token."""
        from .gamification_engine import get_or_create_config
        config = get_or_create_config(obj.tenant)
        return int(config.coin_price_streak_freeze)

