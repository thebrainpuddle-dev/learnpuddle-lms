from rest_framework import serializers

from .models import Tenant
from utils.s3_utils import sign_file_field


class TenantSettingsSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    # TASK-020 — computed, read-only merged label map.  Writes are made
    # via `mode` + `mode_label_overrides`, not this field.
    mode_labels = serializers.SerializerMethodField()

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
            # TASK-020 — Education vs Corporate mode
            "mode",
            "mode_label_overrides",
            "mode_labels",
        ]
        read_only_fields = ["id", "subdomain", "logo_url", "mode_labels"]

    def validate_notification_from_name(self, value: str) -> str:
        return (value or "").strip()

    def validate_notification_reply_to(self, value: str) -> str:
        return (value or "").strip().lower()

    def validate_email_bucket_prefix(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized and not normalized.replace("-", "").replace("_", "").isalnum():
            raise serializers.ValidationError("Use only letters, numbers, hyphens, or underscores.")
        return normalized

    def validate_mode_label_overrides(self, value) -> dict:
        """
        Overrides must be a JSON object mapping label keys to non-empty
        strings.  Drop any non-string values silently — we don't want a
        malformed payload to poison the label map, but we also don't want
        to 400 on frontend-sent extras.

        Contract: non-string values (e.g. ``{"course": 42}``) are silently
        dropped and the key is absent from the stored overrides.  The admin
        UI is expected to validate types client-side before calling this
        endpoint.  A 200 response with an empty or reduced override map is
        therefore valid and expected behaviour when the payload contains
        non-string values.
        """
        if value in (None, "", []):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be a JSON object.")
        cleaned = {}
        for key, raw in value.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if isinstance(raw, str) and raw.strip():
                cleaned[key.strip()] = raw.strip()
        return cleaned

    def get_mode_labels(self, obj: Tenant) -> dict:
        return obj.get_mode_labels()

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
