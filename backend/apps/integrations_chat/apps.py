from django.apps import AppConfig


class IntegrationsChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations_chat"
    verbose_name = "Chat Integrations (Slack / Teams)"

    def ready(self):
        # Import signal handlers to connect them.
        from . import signals  # noqa: F401
