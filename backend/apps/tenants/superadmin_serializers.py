# apps/tenants/superadmin_serializers.py

from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from rest_framework import serializers

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course
from utils.s3_utils import sign_file_field


class TenantListSerializer(serializers.ModelSerializer):
    # These fields are populated via annotate() on the queryset — no per-row queries.
    teacher_count = serializers.IntegerField(read_only=True, default=0)
    admin_count = serializers.IntegerField(read_only=True, default=0)
    course_count = serializers.IntegerField(read_only=True, default=0)
    logo = serializers.SerializerMethodField()

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

    def get_logo(self, obj):
        if not obj.logo:
            return None
        signed = sign_file_field(obj.logo, expires_in=86400)
        if signed:
            return signed
        try:
            return obj.logo.url
        except Exception:
            # Storage/backing CDN outages should not break super-admin tenant list.
            return None

    @staticmethod
    def annotate_counts(qs):
        """Annotate a Tenant queryset with teacher/admin/course counts in 1 query."""
        return qs.annotate(
            teacher_count=Count(
                "users", filter=Q(users__role="TEACHER", users__is_active=True), distinct=True
            ),
            admin_count=Count(
                "users", filter=Q(users__role="SCHOOL_ADMIN", users__is_active=True), distinct=True
            ),
            course_count=Count("courses", distinct=True),
        )


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

    def _get_admin(self, obj):
        """Cache the admin user lookup to avoid duplicate queries."""
        cache_attr = "_cached_admin"
        if not hasattr(obj, cache_attr):
            setattr(
                obj,
                cache_attr,
                User.objects.filter(tenant=obj, role="SCHOOL_ADMIN", is_active=True).first(),
            )
        return getattr(obj, cache_attr)

    def get_admin_email(self, obj):
        admin = self._get_admin(obj)
        return admin.email if admin else None

    def get_admin_name(self, obj):
        admin = self._get_admin(obj)
        return admin.get_full_name() if admin else None


class OnboardTenantSerializer(serializers.Serializer):
    """Serializer for the onboard-school endpoint."""
    school_name = serializers.CharField(max_length=200)
    admin_email = serializers.EmailField()
    admin_first_name = serializers.CharField(max_length=100)
    admin_last_name = serializers.CharField(max_length=100)
    admin_password = serializers.CharField(max_length=128, min_length=8, write_only=True)
    subdomain = serializers.SlugField(max_length=100, required=False, allow_blank=True)

    def _strip_html(self, value):
        """Strip HTML tags from text inputs as defense-in-depth."""
        import re
        cleaned = re.sub(r'<[^>]+>', '', value).strip()
        if not cleaned:
            raise serializers.ValidationError("This field cannot be empty or contain only HTML tags.")
        return cleaned

    def validate_school_name(self, value):
        return self._strip_html(value)

    def validate_admin_first_name(self, value):
        return self._strip_html(value)

    def validate_admin_last_name(self, value):
        return self._strip_html(value)

    def validate_admin_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_subdomain(self, value):
        if value and Tenant.objects.filter(subdomain=value).exists():
            raise serializers.ValidationError("This subdomain is already taken.")
        return value

    def validate_admin_password(self, value):
        try:
            django_validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
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

    def validate_name(self, value):
        import re
        return re.sub(r'<[^>]+>', '', value).strip() or value
