# apps/progress/gamification_serializers.py

from rest_framework import serializers

from .gamification_models import (
    BadgeDefinition,
    GamificationConfig,
    TeacherBadge,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)


class GamificationConfigSerializer(serializers.ModelSerializer):
    """Read/write serializer for GamificationConfig."""

    class Meta:
        model = GamificationConfig
        fields = [
            'id', 'xp_per_content_completion', 'xp_per_course_completion',
            'xp_per_assignment_submission', 'xp_per_quiz_submission',
            'xp_per_streak_day', 'streak_freeze_max', 'leaderboard_enabled',
            'leaderboard_anonymize', 'opt_out_allowed', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BadgeDefinitionSerializer(serializers.ModelSerializer):
    """Read serializer for BadgeDefinition."""

    class Meta:
        model = BadgeDefinition
        fields = [
            'id', 'name', 'description', 'icon', 'color', 'category',
            'criteria_type', 'criteria_value', 'is_active', 'sort_order',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BadgeDefinitionCreateSerializer(serializers.ModelSerializer):
    """Create/update serializer for BadgeDefinition."""

    class Meta:
        model = BadgeDefinition
        fields = [
            'name', 'description', 'icon', 'color', 'category',
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
