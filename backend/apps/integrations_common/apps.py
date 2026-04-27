from django.apps import AppConfig


class IntegrationsCommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations_common"
    verbose_name = "Integrations Common (shared crypto)"
