# apps/progress/skills_serializers.py

import uuid as _uuid

from rest_framework import serializers

from .skills_models import CourseSkill, Skill, TeacherSkill


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = [
            'id', 'name', 'description', 'category',
            'level_required', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SkillCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ['name', 'description', 'category', 'level_required']

    def validate_name(self, value):
        tenant = self.context['request'].tenant
        qs = Skill.all_objects.filter(tenant=tenant, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A skill with this name already exists.")
        return value


class CourseSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill.name', read_only=True)
    skill_category = serializers.CharField(source='skill.category', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = CourseSkill
        fields = [
            'id', 'course', 'skill', 'level_taught',
            'skill_name', 'skill_category', 'course_title', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CourseSkillCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseSkill
        fields = ['course', 'skill', 'level_taught']

    def validate(self, data):
        course = data.get('course')
        skill = data.get('skill')
        qs = CourseSkill.objects.filter(course=course, skill=skill)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This skill is already mapped to this course.")
        return data


class TeacherSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill.name', read_only=True)
    skill_category = serializers.CharField(source='skill.category', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.EmailField(source='teacher.email', read_only=True)
    has_gap = serializers.BooleanField(read_only=True)
    gap_size = serializers.IntegerField(read_only=True)

    class Meta:
        model = TeacherSkill
        fields = [
            'id', 'teacher', 'skill', 'current_level', 'target_level',
            'last_assessed', 'skill_name', 'skill_category',
            'teacher_name', 'teacher_email', 'has_gap', 'gap_size',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_assessed']

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.email


class TeacherSkillUpdateSerializer(serializers.Serializer):
    current_level = serializers.IntegerField(min_value=0, max_value=5, required=False)
    target_level = serializers.IntegerField(min_value=1, max_value=5, required=False)


class BulkTeacherSkillUpdateSerializer(serializers.Serializer):
    """For bulk-updating teacher skill levels."""
    updates = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=200,
        help_text="List of {teacher_skill_id, current_level, target_level}",
    )

    def validate_updates(self, value):
        for item in value:
            if 'teacher_skill_id' not in item:
                raise serializers.ValidationError("Each update must include teacher_skill_id.")
            try:
                _uuid.UUID(str(item['teacher_skill_id']))
            except (ValueError, AttributeError):
                raise serializers.ValidationError(
                    f"Invalid UUID for teacher_skill_id: {item['teacher_skill_id']}"
                )
            if 'current_level' not in item and 'target_level' not in item:
                raise serializers.ValidationError(
                    "Each update must include at least current_level or target_level."
                )
            if 'current_level' in item:
                level = item['current_level']
                if not isinstance(level, int) or level < 0 or level > 5:
                    raise serializers.ValidationError("current_level must be 0-5.")
            if 'target_level' in item:
                level = item['target_level']
                if not isinstance(level, int) or level < 1 or level > 5:
                    raise serializers.ValidationError("target_level must be 1-5.")
        return value


class GapAnalysisItemSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    teacher_name = serializers.CharField()
    teacher_email = serializers.EmailField()
    skill_id = serializers.UUIDField()
    skill_name = serializers.CharField()
    skill_category = serializers.CharField()
    current_level = serializers.IntegerField()
    target_level = serializers.IntegerField()
    gap_size = serializers.IntegerField()
    recommended_courses = serializers.ListField(child=serializers.DictField())
