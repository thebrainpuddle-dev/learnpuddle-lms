"""MAIC-501 (Phase 5, 2026-05-04) — Add Minimax TTS support to TenantAIConfig.

Per ADR-004a (2026-05-04), Phase 5 ships with cloud Minimax as the
primary TTS provider after the VoxCPM2 spike (MAIC-500) failed both
ADR-004 gates on Apple Silicon hardware.

Two changes:
  1. Add `tts_base_url` URLField — used by Minimax (custom proxy) and
     reserved for Phase 9 self-hosted VoxCPM2.
  2. Extend `tts_provider` choices to include "minimax".

Both are additive; no data migration required. Existing rows keep their
current `tts_provider` values; `tts_base_url` defaults to "" (empty
string falls back to provider default in apps.maic.tts.service).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0045_add_quiz_content_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantaiconfig",
            name="tts_base_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text=(
                    "Custom TTS endpoint (proxies, self-hosted "
                    "VoxCPM2 in Phase 9, etc.)"
                ),
                max_length=500,
            ),
        ),
        migrations.AlterField(
            model_name="tenantaiconfig",
            name="tts_provider",
            field=models.CharField(
                choices=[
                    ("openai", "OpenAI TTS"),
                    ("elevenlabs", "ElevenLabs"),
                    ("azure", "Azure TTS"),
                    ("minimax", "MiniMax TTS"),
                    ("edge", "Edge TTS (free)"),
                    ("disabled", "Disabled"),
                ],
                default="edge",
                max_length=20,
            ),
        ),
    ]
