# apps/tenants/superadmin_serializers.py

from rest_framework import serializers
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course


class TenantListSerializer(serializers.ModelSerializer):
    teacher_count = serializers.SerializerMethodField()
    admin_count = serializers.SerializerMethodField()
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id", "name", "slug", "subdomain", "email",
            "is_active", "is_trial", "trial_end_date",
            "plan", "plan_started_at", "plan_expires_at",
            "max_teachers", "max_courses", "max_storage_mb",
            "primary_color", "logo",
            "teacher_count", "admin_count", "course_count",
            "created_at", "updated_at",
        ]

    def get_teacher_count(self, obj):
        return User.objects.filter(tenant=obj, role="TEACHER", is_active=True).count()

    def get_admin_count(self, obj):
        return User.objects.filter(tenant=obj, role="SCHOOL_ADMIN", is_active=True).count()

    def get_course_count(self, obj):
        return Course.objects.filter(tenant=obj).count()


class TenantDetailSerializer(TenantListSerializer):
    published_course_count = serializers.SerializerMethodField()
    admin_email = serializers.SerializerMethodField()
    admin_name = serializers.SerializerMethodField()

    class Meta(TenantListSerializer.Meta):
        fields = TenantListSerializer.Meta.fields + [
            "phone", "address", "secondary_color", "font_family",
            "max_video_duration_minutes",
            "feature_video_upload", "feature_auto_quiz", "feature_transcripts",
            "feature_reminders", "feature_custom_branding", "feature_reports_export",
            "feature_groups", "feature_certificates", "feature_teacher_authoring",
            "internal_notes",
            "published_course_count", "admin_email", "admin_name",
        ]

    def get_published_course_count(self, obj):
        return Course.objects.filter(tenant=obj, is_published=True).count()

    def get_admin_email(self, obj):
        admin = User.objects.filter(tenant=obj, role="SCHOOL_ADMIN", is_active=True).first()
        return admin.email if admin else None

    def get_admin_name(self, obj):
        admin = User.objects.filter(tenant=obj, role="SCHOOL_ADMIN", is_active=True).first()
        return admin.get_full_name() if admin else None


class OnboardTenantSerializer(serializers.Serializer):
    """Serializer for the onboard-school endpoint."""
    school_name = serializers.CharField(max_length=200)
    admin_email = serializers.EmailField()
    admin_first_name = serializers.CharField(max_length=100)
    admin_last_name = serializers.CharField(max_length=100)
    admin_password = serializers.CharField(max_length=128, write_only=True)
    subdomain = serializers.SlugField(max_length=100, required=False, allow_blank=True)

    def validate_admin_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_subdomain(self, value):
        if value and Tenant.objects.filter(subdomain=value).exists():
            raise serializers.ValidationError("This subdomain is already taken.")
        return value


class TenantUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            "name", "email", "phone", "address",
            "is_active", "is_trial", "trial_end_date",
            "plan", "plan_started_at", "plan_expires_at",
            "max_teachers", "max_courses", "max_storage_mb", "max_video_duration_minutes",
            "feature_video_upload", "feature_auto_quiz", "feature_transcripts",
            "feature_reminders", "feature_custom_branding", "feature_reports_export",
            "feature_groups", "feature_certificates", "feature_teacher_authoring",
            "internal_notes",
            "primary_color", "secondary_color", "font_family",
        ]
        extra_kwargs = {f: {"required": False} for f in fields}
