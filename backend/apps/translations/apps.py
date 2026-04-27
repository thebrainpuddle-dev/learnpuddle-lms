"""App configuration for apps.translations (TASK-058)."""

from __future__ import annotations

from django.apps import AppConfig


class TranslationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.translations"
    verbose_name = "Auto-Translation Service"

    def ready(self) -> None:  # pragma: no cover - trivial
        # Connect post_save / post_delete signals on Course / Module / Content.
        from . import signals  # noqa: F401
