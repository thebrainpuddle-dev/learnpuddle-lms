"""
DRF serializers for the integrations_chat app.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.integrations_common.crypto import decrypt_secret, encrypt_secret, mask_secret
from .models import ChatDelivery, ChatIntegration, ChatRoutingRule
from .ssrf_guard import SSRFError, validate_webhook_host


class ChatIntegrationSerializer(serializers.ModelSerializer):
    """
    Serializer for ChatIntegration.

    * Accepts ``webhook_url`` (plaintext) on write — validates allowlist,
      then encrypts before saving.
    * Returns ``webhook_url_masked`` (last-4 visible) on read — never the
      full URL.
    """

    # Write-only field for the raw URL.
    webhook_url = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Plaintext webhook URL. Stored encrypted; never returned.",
    )

    # Read-only masked representation.
    webhook_url_masked = serializers.SerializerMethodField()

    class Meta:
        model = ChatIntegration
        fields = [
            "id",
            "provider",
            "display_name",
            "webhook_url",
            "webhook_url_masked",
            "is_active",
            "last_delivery_at",
            "last_delivery_status",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "webhook_url_encrypted",
            "webhook_url_masked",
            "last_delivery_at",
            "last_delivery_status",
            "error",
            "created_at",
            "updated_at",
        ]

    def get_webhook_url_masked(self, obj: ChatIntegration) -> str:
        plaintext = decrypt_secret(obj.webhook_url_encrypted)
        if not plaintext:
            return ""
        return mask_secret(plaintext, visible=4)

    def validate_webhook_url(self, value: str) -> str:
        if not value:
            return value
        try:
            validate_webhook_host(value)
        except SSRFError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate(self, data: dict) -> dict:
        # On create, webhook_url is required.
        if self.instance is None and not data.get("webhook_url"):
            raise serializers.ValidationError({"webhook_url": "This field is required."})
        return data

    def create(self, validated_data: dict) -> ChatIntegration:
        webhook_url = validated_data.pop("webhook_url", "")
        validated_data["webhook_url_encrypted"] = encrypt_secret(webhook_url)
        return super().create(validated_data)

    def update(self, instance: ChatIntegration, validated_data: dict) -> ChatIntegration:
        webhook_url = validated_data.pop("webhook_url", None)
        if webhook_url:
            validated_data["webhook_url_encrypted"] = encrypt_secret(webhook_url)
        return super().update(instance, validated_data)


class ChatRoutingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRoutingRule
        fields = ["id", "integration", "notification_type", "role_filter", "enabled"]
        read_only_fields = ["id"]


class ChatDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatDelivery
        fields = [
            "id",
            "integration",
            "notification_id",
            "notification_type",
            "status",
            "attempts",
            "last_attempt_at",
            "last_error",
            "created_at",
        ]
        read_only_fields = fields
