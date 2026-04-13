import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0013_initial_academic_structure"),
        ("courses", "0020_add_grade_section_fks"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantAIConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("llm_provider", models.CharField(choices=[("openai", "OpenAI"), ("anthropic", "Anthropic"), ("google", "Google AI"), ("openrouter", "OpenRouter"), ("azure", "Azure OpenAI")], default="openai", max_length=20)),
                ("llm_model", models.CharField(default="gpt-4o-mini", help_text="Model identifier, e.g. gpt-4o, claude-sonnet-4-20250514", max_length=100)),
                ("llm_api_key_encrypted", models.TextField(blank=True, default="", help_text="Fernet-encrypted API key")),
                ("llm_base_url", models.URLField(blank=True, default="", help_text="Custom base URL (for Azure, proxies, etc.)", max_length=500)),
                ("tts_provider", models.CharField(choices=[("openai", "OpenAI TTS"), ("elevenlabs", "ElevenLabs"), ("azure", "Azure TTS"), ("edge", "Edge TTS (free)"), ("disabled", "Disabled")], default="edge", max_length=20)),
                ("tts_api_key_encrypted", models.TextField(blank=True, default="")),
                ("tts_voice_id", models.CharField(blank=True, default="", help_text="Voice identifier for the chosen TTS provider", max_length=100)),
                ("image_provider", models.CharField(choices=[("openai", "DALL-E"), ("stability", "Stability AI"), ("disabled", "Disabled")], default="disabled", max_length=20)),
                ("image_api_key_encrypted", models.TextField(blank=True, default="")),
                ("maic_enabled", models.BooleanField(default=False, help_text="Master switch for OpenMAIC AI Classroom feature")),
                ("max_classrooms_per_teacher", models.PositiveIntegerField(default=20, help_text="Maximum classrooms a single teacher can create")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="ai_config", to="tenants.tenant")),
            ],
            options={
                "verbose_name": "Tenant AI Config",
                "verbose_name_plural": "Tenant AI Configs",
                "db_table": "tenant_ai_configs",
            },
        ),
        migrations.CreateModel(
            name="MAICClassroom",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True, default="")),
                ("topic", models.CharField(blank=True, default="", help_text="Original topic or PDF filename used for generation", max_length=500)),
                ("language", models.CharField(default="en", max_length=10)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("GENERATING", "Generating"), ("READY", "Ready"), ("FAILED", "Failed"), ("ARCHIVED", "Archived")], default="DRAFT", max_length=12)),
                ("error_message", models.TextField(blank=True, default="")),
                ("config", models.JSONField(blank=True, default=dict)),
                ("is_public", models.BooleanField(default=False, help_text="When True, students can browse and access this classroom")),
                ("scene_count", models.PositiveIntegerField(default=0)),
                ("estimated_minutes", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="maic_classrooms", to="tenants.tenant")),
                ("creator", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="maic_classrooms", to=settings.AUTH_USER_MODEL)),
                ("course", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="maic_classrooms", to="courses.course")),
            ],
            options={
                "db_table": "maic_classrooms",
                "ordering": ["-updated_at"],
                "indexes": [
                    models.Index(fields=["tenant", "creator", "-updated_at"], name="maic_cls_tenant_creator_idx"),
                    models.Index(fields=["tenant", "status"], name="maic_cls_tenant_status_idx"),
                    models.Index(fields=["tenant", "is_public", "status"], name="maic_cls_tenant_public_idx"),
                    models.Index(fields=["tenant", "course"], name="maic_cls_tenant_course_idx"),
                ],
            },
        ),
    ]
