from django.db import migrations


TTS_PROVIDER_MAP = {
    "openai": "openai-tts",
    "elevenlabs": "elevenlabs-tts",
    "azure": "azure-tts",
    "minimax": "minimax-tts",
    "edge": "browser-native-tts",
}

IMAGE_PROVIDER_MAP = {
    "openai": "openai-image",
    "qwen": "qwen-image",
    "grok": "grok-image",
    "minimax": "minimax-image",
    "nano_banana": "nano-banana",
    "seedream": "seedream",
    "pollinations": "pollinations",
    "stability": "stability",
}


def normalize_openmaic_model(provider_id, model_id):
    value = (model_id or "").strip()
    if not value:
        return ""
    slash_prefix = f"{provider_id}/"
    colon_prefix = f"{provider_id}:"
    if value.startswith(slash_prefix):
        return f"{provider_id}:{value[len(slash_prefix):]}"
    if value.startswith(colon_prefix):
        return value
    return f"{provider_id}:{value}"


def migrate_legacy_configs(apps, schema_editor):
    LegacyConfig = apps.get_model("courses", "TenantAIConfig")
    RuntimeConfig = apps.get_model("ai_classroom", "TenantAIRuntimeConfig")
    Credential = apps.get_model("ai_classroom", "TenantAIProviderCredential")

    for legacy in LegacyConfig.objects.all().iterator():
        RuntimeConfig.objects.get_or_create(
            tenant_id=legacy.tenant_id,
            defaults={"runtime": "legacy", "provider_config_version": 1},
        )

        normalized_llm_model = normalize_openmaic_model(
            legacy.llm_provider,
            legacy.llm_model,
        )
        llm_models = [normalized_llm_model] if normalized_llm_model else []
        Credential.objects.get_or_create(
            tenant_id=legacy.tenant_id,
            modality="llm",
            provider_id=legacy.llm_provider,
            defaults={
                "api_key_encrypted": legacy.llm_api_key_encrypted,
                "base_url": legacy.llm_base_url,
                "model_allowlist": llm_models,
                "is_enabled": bool(legacy.llm_api_key_encrypted or legacy.llm_base_url),
                "is_default": True,
            },
        )

        if legacy.tts_provider != "disabled":
            Credential.objects.get_or_create(
                tenant_id=legacy.tenant_id,
                modality="tts",
                provider_id=TTS_PROVIDER_MAP.get(legacy.tts_provider, legacy.tts_provider),
                defaults={
                    "api_key_encrypted": legacy.tts_api_key_encrypted,
                    "base_url": legacy.tts_base_url,
                    "provider_config": {"voice": legacy.tts_voice_id},
                    "is_enabled": True,
                    "is_default": True,
                },
            )

        if legacy.image_provider != "disabled":
            Credential.objects.get_or_create(
                tenant_id=legacy.tenant_id,
                modality="image",
                provider_id=IMAGE_PROVIDER_MAP.get(legacy.image_provider, legacy.image_provider),
                defaults={
                    "api_key_encrypted": legacy.image_api_key_encrypted,
                    "base_url": legacy.image_base_url,
                    "model_allowlist": [legacy.image_model] if legacy.image_model else [],
                    "provider_config": {
                        "size": legacy.image_default_size,
                        "quality": legacy.image_default_quality,
                    },
                    "is_enabled": True,
                    "is_default": True,
                },
            )

        if legacy.video_provider != "disabled":
            Credential.objects.get_or_create(
                tenant_id=legacy.tenant_id,
                modality="video",
                provider_id=legacy.video_provider,
                defaults={
                    "api_key_encrypted": legacy.video_api_key_encrypted,
                    "base_url": legacy.video_base_url,
                    "model_allowlist": [legacy.video_model] if legacy.video_model else [],
                    "provider_config": {"duration": legacy.video_default_duration},
                    "is_enabled": True,
                    "is_default": True,
                },
            )

        if legacy.pdf_provider != "disabled":
            Credential.objects.get_or_create(
                tenant_id=legacy.tenant_id,
                modality="pdf",
                provider_id="mineru-cloud" if legacy.pdf_provider == "mineru" else legacy.pdf_provider,
                defaults={
                    "api_key_encrypted": legacy.mineru_api_key_encrypted,
                    "base_url": legacy.mineru_base_url,
                    "is_enabled": True,
                    "is_default": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("ai_classroom", "0001_initial"),
        ("courses", "0051_alter_aichatbotknowledge_managers_and_more"),
    ]

    operations = [migrations.RunPython(migrate_legacy_configs, migrations.RunPython.noop)]
