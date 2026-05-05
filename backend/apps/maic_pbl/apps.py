"""Django app config for the MAIC v2 PBL subsystem.

Phase 7 (started 2026-05-05). Routes/consumers gate behind
settings.MAIC_V2_ENABLED — same posture as apps.maic — so the app
stays INSTALLED in both flag states for migration coherence.
"""
from django.apps import AppConfig


class MaicPblConfig(AppConfig):
    """MAIC v2 PBL — Project-Based Learning subsystem."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maic_pbl"
    verbose_name = "AI Classroom PBL (MAIC v2)"
