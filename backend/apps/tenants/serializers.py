from rest_framework import serializers

from .models import Tenant
from utils.s3_utils import sign_file_field


class TenantThemeSerializer(serializers.ModelSerializer):
    """
    Public tenant theme payload for UI bootstrapping.
    Tenant is inferred from request host (subdomain) by middleware/util.
    """

    logo_url = serializers.SerializerMethodField()
    mode_labels = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "name",
            "subdomain",
            "logo_url",
            "primary_color",
            "secondary_color",
            "font_family",
            "is_active",
            "is_trial",
            "trial_end_date",
            "white_label",
            "login_bg_image",
            "welcome_message",
            "school_motto",
            # TASK-020 — Education vs Corporate mode
            "mode",
            "mode_labels",
            # TASK-058 — Auto-translation service source language pin
            "default_language",
        ]

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
        if request is not None:
            return request.build_absolute_uri(url)
        return url

