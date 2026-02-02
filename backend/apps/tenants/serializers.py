from rest_framework import serializers

from .models import Tenant


class TenantThemeSerializer(serializers.ModelSerializer):
    """
    Public tenant theme payload for UI bootstrapping.
    Tenant is inferred from request host (subdomain) by middleware/util.
    """

    logo_url = serializers.SerializerMethodField()

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
        ]

    def get_logo_url(self, obj: Tenant):
        request = self.context.get("request")
        if not obj.logo:
            return None
        try:
            url = obj.logo.url
        except Exception:
            return None
        if request is not None:
            return request.build_absolute_uri(url)
        return url

