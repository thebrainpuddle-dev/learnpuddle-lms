from django.apps import AppConfig


class MaicConfig(AppConfig):
    """AI Classroom v2 (MAIC).

    Replaces the legacy apps.courses.maic_* modules incrementally per the
    plan in docs/AI_CLASSROOM_BLUEPRINT.md. Routes/consumers are gated
    behind settings.MAIC_V2_ENABLED (added in MAIC-007); the app stays
    INSTALLED in both flag states so migrations remain coherent.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maic"
    verbose_name = "AI Classroom (MAIC v2)"
