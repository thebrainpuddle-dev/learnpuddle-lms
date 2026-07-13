from __future__ import annotations

from rest_framework import serializers

from apps.integrations_chat.ssrf_guard import SSRFError, validate_external_url

from .models import TenantAIProviderCredential


class ProviderCredentialSerializer(serializers.ModelSerializer):
    SENSITIVE_CONFIG_KEYS = {
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "password",
        "credential",
        "credentials",
    }
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    clear_api_key = serializers.BooleanField(write_only=True, required=False, default=False)
    api_key_set = serializers.SerializerMethodField()
    api_key_preview = serializers.SerializerMethodField()

    class Meta:
        model = TenantAIProviderCredential
        fields = [
            "id",
            "modality",
            "provider_id",
            "display_name",
            "api_key",
            "clear_api_key",
            "api_key_set",
            "api_key_preview",
            "base_url",
            "model_allowlist",
            "provider_config",
            "is_enabled",
            "is_default",
            "verification_status",
            "verification_message",
            "last_verified_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "verification_status",
            "verification_message",
            "last_verified_at",
            "created_at",
            "updated_at",
        ]

    def get_api_key_set(self, obj) -> bool:
        return bool(obj.api_key_encrypted)

    def get_api_key_preview(self, obj) -> str:
        return obj.api_key_preview

    def validate_base_url(self, value: str) -> str:
        value = (value or "").strip().rstrip("/")
        if not value:
            return ""
        try:
            validate_external_url(value)
        except SSRFError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate_model_allowlist(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("model_allowlist must be a list of strings")
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if len(cleaned) > 100:
            raise serializers.ValidationError("At most 100 models may be enabled")
        return cleaned

    def validate_provider_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("provider_config must be an object")

        def reject_secret_keys(node):
            if isinstance(node, dict):
                for key, child in node.items():
                    if str(key).lower() in self.SENSITIVE_CONFIG_KEYS:
                        raise serializers.ValidationError(
                            f"Secret field {key!r} must use the encrypted api_key field"
                        )
                    reject_secret_keys(child)
            elif isinstance(node, list):
                for child in node:
                    reject_secret_keys(child)

        reject_secret_keys(value)
        return value

    def validate(self, attrs):
        modality = attrs.get("modality", getattr(self.instance, "modality", None))
        provider_id = attrs.get(
            "provider_id",
            getattr(self.instance, "provider_id", ""),
        )
        models = attrs.get(
            "model_allowlist",
            getattr(self.instance, "model_allowlist", []),
        )
        if modality == "llm" and not models:
            raise serializers.ValidationError(
                {"model_allowlist": "At least one LLM model must be enabled"}
            )
        if modality == "llm" and "model_allowlist" in attrs:
            slash_prefix = f"{provider_id}/"
            attrs["model_allowlist"] = [
                f"{provider_id}:{model[len(slash_prefix):]}"
                if model.startswith(slash_prefix)
                else model
                for model in models
            ]
        return attrs

    def _apply_secret(self, instance, validated_data):
        api_key = validated_data.pop("api_key", "")
        clear_api_key = validated_data.pop("clear_api_key", False)
        if api_key and clear_api_key:
            raise serializers.ValidationError("api_key and clear_api_key are mutually exclusive")
        if clear_api_key:
            instance.api_key_encrypted = ""
        elif api_key:
            instance.set_api_key(api_key)

    def create(self, validated_data):
        tenant = self.context["tenant"]
        instance = TenantAIProviderCredential(tenant=tenant)
        self._apply_secret(instance, validated_data)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        self._apply_secret(instance, validated_data)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.verification_status = "unverified"
        instance.verification_message = ""
        instance.last_verified_at = None
        instance.save()
        return instance


class ProviderStatusSerializer(serializers.ModelSerializer):
    """Read-only school-facing view of LearnPuddle-managed AI capability."""

    class Meta:
        model = TenantAIProviderCredential
        fields = [
            "modality",
            "provider_id",
            "display_name",
            "model_allowlist",
            "is_enabled",
            "is_default",
            "verification_status",
            "last_verified_at",
        ]
        read_only_fields = fields
