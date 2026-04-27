from django.apps import AppConfig


class IntegrationsCalendarConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations_calendar"
    verbose_name = "Calendar Integrations (Google / Outlook / iCal)"

    def ready(self):
        # Import signal handlers to wire them up.
        from . import signals  # noqa: F401
