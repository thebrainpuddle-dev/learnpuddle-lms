from rest_framework import serializers

from .models import Tenant


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
            "is_active",
            "is_trial",
            "trial_end_date",
        ]
        read_only_fields = ["id", "subdomain", "logo_url"]

    def get_logo_url(self, obj: Tenant):
        request = self.context.get("request")
        if not obj.logo:
            return None
        try:
            url = obj.logo.url
        except Exception:
            return None
        return request.build_absolute_uri(url) if request else url

