"""Serializers for academic structure models."""

from rest_framework import serializers
from .models import GradeBand, Grade, Section, Subject, TeachingAssignment


class GradeBandSerializer(serializers.ModelSerializer):
    """GradeBand with grade count annotation."""

    grade_count = serializers.SerializerMethodField()

    class Meta:
        model = GradeBand
        fields = [
            'id', 'name', 'short_code', 'order', 'curriculum_framework',
            'theme_config', 'grade_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_grade_count(self, obj):
        if hasattr(obj, '_grade_count'):
            return obj._grade_count
        return obj.grades.count()

    def validate_name(self, value):
        request = self.context.get('request')
        if request and hasattr(request, 'tenant') and request.tenant:
            qs = GradeBand.all_objects.filter(tenant=request.tenant, name=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    f"A grade band named '{value}' already exists."
                )
        return value


class GradeSerializer(serializers.ModelSerializer):
    """Grade with band name, student/section counts."""

    grade_band_name = serializers.CharField(source='grade_band.name', read_only=True)
    grade_band_short_code = serializers.CharField(source='grade_band.short_code', read_only=True)
    student_count = serializers.SerializerMethodField()
    section_count = serializers.SerializerMethodField()

    class Meta:
        model = Grade
        fields = [
            'id', 'grade_band', 'grade_band_name', 'grade_band_short_code',
            'name', 'short_code', 'order',
            'student_count', 'section_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_student_count(self, obj):
        if hasattr(obj, '_student_count'):
            return obj._student_count
        return obj.students.filter(is_deleted=False, is_active=True).count()

    def get_section_count(self, obj):
        if hasattr(obj, '_section_count'):
            return obj._section_count
        return obj.sections.count()


class GradeMinimalSerializer(serializers.ModelSerializer):
    """Lightweight grade serializer for nested usage."""

    class Meta:
        model = Grade
        fields = ['id', 'name', 'short_code', 'order']
        read_only_fields = ['id']


class SectionSerializer(serializers.ModelSerializer):
    """Section with grade name, class teacher name, student count."""

    grade_name = serializers.CharField(source='grade.name', read_only=True)
    grade_short_code = serializers.CharField(source='grade.short_code', read_only=True)
    class_teacher_name = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = [
            'id', 'grade', 'grade_name', 'grade_short_code',
            'name', 'academic_year',
            'class_teacher', 'class_teacher_name',
            'student_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_class_teacher_name(self, obj):
        if obj.class_teacher_id:
            return obj.class_teacher.get_full_name()
        return None

    def validate_class_teacher(self, value):
        if value is None:
            return value
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None) if request else None
        if tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError(
                "Class teacher must belong to the same school."
            )
        if value.role not in ('TEACHER', 'HOD', 'IB_COORDINATOR', 'SCHOOL_ADMIN'):
            raise serializers.ValidationError(
                "Class teacher must be a staff member."
            )
        return value

    def get_student_count(self, obj):
        if hasattr(obj, '_student_count'):
            return obj._student_count
        return obj.students.filter(is_deleted=False, is_active=True).count()

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None) if request else None
        if tenant:
            grade = data.get('grade', getattr(self.instance, 'grade', None))
            name = data.get('name', getattr(self.instance, 'name', None))
            academic_year = data.get('academic_year', getattr(self.instance, 'academic_year', None))
            qs = Section.all_objects.filter(
                tenant=tenant, grade=grade, name=name, academic_year=academic_year,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    f"Section '{name}' already exists for this grade and academic year."
                )
        return data


class SubjectSerializer(serializers.ModelSerializer):
    """Subject with applicable grade IDs (writable M2M)."""

    applicable_grade_ids = serializers.PrimaryKeyRelatedField(
        source='applicable_grades',
        queryset=Grade.objects.none(),  # Overridden in __init__
        many=True,
        required=False,
    )
    applicable_grade_names = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            'id', 'name', 'code', 'department',
            'applicable_grade_ids', 'applicable_grade_names',
            'is_elective',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'tenant') and request.tenant:
            self.fields['applicable_grade_ids'].child_relation.queryset = (
                Grade.all_objects.filter(tenant=request.tenant)
            )

    def validate_code(self, value):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None) if request else None
        if tenant:
            qs = Subject.all_objects.filter(tenant=tenant, code=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    f"A subject with code '{value}' already exists."
                )
        return value

    def get_applicable_grade_names(self, obj):
        return [
            {'id': str(g.id), 'name': g.name, 'short_code': g.short_code}
            for g in obj.applicable_grades.order_by('order')
        ]


class SubjectMinimalSerializer(serializers.ModelSerializer):
    """Lightweight subject serializer for nested usage."""

    class Meta:
        model = Subject
        fields = ['id', 'name', 'code', 'department', 'is_elective']
        read_only_fields = ['id']


class TeachingAssignmentSerializer(serializers.ModelSerializer):
    """TeachingAssignment with teacher/subject names and writable section IDs."""

    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.EmailField(source='teacher.email', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    section_ids = serializers.PrimaryKeyRelatedField(
        source='sections',
        queryset=Section.objects.none(),  # Overridden in __init__
        many=True,
        required=False,
    )
    section_details = serializers.SerializerMethodField()

    class Meta:
        model = TeachingAssignment
        fields = [
            'id', 'teacher', 'teacher_name', 'teacher_email',
            'subject', 'subject_name', 'subject_code',
            'section_ids', 'section_details',
            'academic_year', 'is_class_teacher',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'tenant') and request.tenant:
            self.fields['section_ids'].child_relation.queryset = (
                Section.all_objects.filter(tenant=request.tenant)
            )

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name()

    def get_section_details(self, obj):
        return [
            {
                'id': str(s.id),
                'name': s.name,
                'grade_name': s.grade.name,
                'grade_short_code': s.grade.short_code,
                'academic_year': s.academic_year,
            }
            for s in obj.sections.select_related('grade').order_by('grade__order', 'name')
        ]


class TeachingAssignmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating teaching assignments with validation."""

    section_ids = serializers.PrimaryKeyRelatedField(
        source='sections',
        queryset=Section.objects.none(),
        many=True,
        required=False,
    )

    class Meta:
        model = TeachingAssignment
        fields = [
            'teacher', 'subject', 'section_ids',
            'academic_year', 'is_class_teacher',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'tenant') and request.tenant:
            from apps.users.models import User
            self.fields['teacher'].queryset = User.objects.filter(
                tenant=request.tenant,
                role__in=['TEACHER', 'HOD', 'IB_COORDINATOR'],
                is_deleted=False,
            )
            self.fields['subject'].queryset = Subject.all_objects.filter(
                tenant=request.tenant,
            )
            self.fields['section_ids'].child_relation.queryset = (
                Section.all_objects.filter(tenant=request.tenant)
            )

    def validate(self, data):
        """Ensure teacher+subject+year uniqueness at serializer level."""
        tenant = self.context['request'].tenant
        teacher = data.get('teacher')
        subject = data.get('subject')
        academic_year = data.get('academic_year', '')

        qs = TeachingAssignment.all_objects.filter(
            tenant=tenant, teacher=teacher, subject=subject,
            academic_year=academic_year,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"{teacher.get_full_name()} already has a teaching assignment "
                f"for {subject.name} in {academic_year}."
            )
        return data
