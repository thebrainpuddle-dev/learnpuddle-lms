# apps/progress/certification_serializers.py

from rest_framework import serializers

from .certification_models import CertificationType, TeacherCertification


class CertificationTypeSerializer(serializers.ModelSerializer):
    required_course_ids = serializers.SerializerMethodField()

    class Meta:
        model = CertificationType
        fields = [
            'id', 'name', 'description', 'validity_months', 'auto_renew',
            'required_course_ids', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_required_course_ids(self, obj):
        return [str(c.id) for c in obj.required_courses.all()]


class CertificationTypeCreateSerializer(serializers.ModelSerializer):
    required_course_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )

    class Meta:
        model = CertificationType
        fields = ['name', 'description', 'validity_months', 'auto_renew', 'required_course_ids']

    def validate_name(self, value):
        tenant = self.context['request'].tenant
        qs = CertificationType.all_objects.filter(tenant=tenant, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A certification type with this name already exists.")
        return value


class TeacherCertificationSerializer(serializers.ModelSerializer):
    certification_name = serializers.CharField(
        source='certification_type.name', read_only=True
    )
    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.EmailField(source='teacher.email', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_until_expiry = serializers.IntegerField(read_only=True)
    issued_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TeacherCertification
        fields = [
            'id', 'teacher', 'certification_type', 'certification_name',
            'teacher_name', 'teacher_email', 'issued_at', 'expires_at',
            'status', 'certificate_file', 'is_expired', 'days_until_expiry',
            'issued_by', 'issued_by_name', 'revoked_reason', 'renewal_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'issued_at', 'created_at', 'updated_at',
            'renewal_count',
        ]

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.email

    def get_issued_by_name(self, obj):
        if obj.issued_by:
            return obj.issued_by.get_full_name() or obj.issued_by.email
        return None


class IssueCertificationSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    certification_type_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class CertificationExpirySerializer(serializers.Serializer):
    """Response shape for expiry-check endpoint."""
    expiring_soon = serializers.ListField(child=serializers.DictField())
    already_expired = serializers.ListField(child=serializers.DictField())
