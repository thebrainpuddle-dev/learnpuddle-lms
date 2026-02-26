from rest_framework import serializers

from .models import Tenant
from utils.s3_utils import sign_file_field


class TenantSettingsSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "subdomain",
            "logo",
            "logo_url",
            "primary_color",
            "secondary_color",
            "font_family",
            "notification_from_name",
            "notification_reply_to",
            "email_bucket_prefix",
            "is_active",
            "is_trial",
            "trial_end_date",
        ]
        read_only_fields = ["id", "subdomain", "logo_url"]

    def validate_notification_from_name(self, value: str) -> str:
        return (value or "").strip()

    def validate_notification_reply_to(self, value: str) -> str:
        return (value or "").strip().lower()

    def validate_email_bucket_prefix(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized and not normalized.replace("-", "").replace("_", "").isalnum():
            raise serializers.ValidationError("Use only letters, numbers, hyphens, or underscores.")
        return normalized

    def get_logo_url(self, obj: Tenant):
        if not obj.logo:
            return None
        # Sign the URL for S3/DO Spaces (24-hour expiry)
        signed = sign_file_field(obj.logo, expires_in=86400)
        if signed:
            return signed
        # Fallback for local storage
        request = self.context.get("request")
        try:
            url = obj.logo.url
        except Exception:
            return None
        return request.build_absolute_uri(url) if request else url
