# apps/users/password_policy_views.py
"""Admin endpoints for managing tenant password policy + SAML config."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.tenants.password_policy_models import TenantPasswordPolicy
from apps.tenants.saml_models import (
    ALLOWED_ATTRIBUTE_KEYS,
    TenantSAMLConfig,
    default_attribute_mapping,
)
from apps.users.saml_service import SAMLValidationError, parse_idp_metadata
from utils.audit import log_audit
from utils.decorators import admin_only, check_feature, tenant_required


class _PasswordPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantPasswordPolicy
        fields = [
            "min_length",
            "require_uppercase",
            "require_lowercase",
            "require_digit",
            "require_special",
            "prevent_common",
            "prevent_reuse_last_n",
            "max_age_days",
            "lockout_threshold",
            "lockout_duration_minutes",
            "policy_rotated_at",
            "updated_at",
        ]
        read_only_fields = ["policy_rotated_at", "updated_at"]

    def validate_min_length(self, value):
        if value < 6:
            raise serializers.ValidationError("min_length must be at least 6.")
        if value > 128:
            raise serializers.ValidationError("min_length must be 128 or less.")
        return value

    def validate_prevent_reuse_last_n(self, value):
        if value > 50:
            raise serializers.ValidationError("prevent_reuse_last_n cannot exceed 50.")
        return value

    def validate_lockout_threshold(self, value):
        if value < 1:
            raise serializers.ValidationError("lockout_threshold must be >= 1.")
        if value > 100:
            raise serializers.ValidationError("lockout_threshold cannot exceed 100.")
        return value


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def password_policy_view(request):
    """GET or PATCH the current tenant's password policy."""
    tenant = request.tenant
    policy, _ = TenantPasswordPolicy.objects.get_or_create(tenant=tenant)

    if request.method == "GET":
        return Response(_PasswordPolicySerializer(policy).data)

    serializer = _PasswordPolicySerializer(policy, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    policy = serializer.save()
    # Bump the rotation marker so JWT refreshes predating the change can be rejected.
    policy.policy_rotated_at = timezone.now()
    policy.save(update_fields=["policy_rotated_at"])

    log_audit(
        "SETTINGS_CHANGE",
        "TenantPasswordPolicy",
        target_id=str(policy.id),
        target_repr=f"password policy for {tenant.subdomain}",
        request=request,
    )
    return Response(_PasswordPolicySerializer(policy).data)


# ----------------------------------------------------------------------
# SAML configuration
# ----------------------------------------------------------------------

class _SAMLConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSAMLConfig
        fields = [
            "enabled",
            "idp_metadata_xml",
            "idp_entity_id",
            "idp_sso_url",
            "idp_slo_url",
            "idp_x509_certs",
            "sp_entity_id",
            "sp_x509_cert",
            "attribute_mapping",
            "auto_provision",
            "default_role",
            "allowed_email_domains",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]
        extra_kwargs = {
            # Never expose private key in GET responses.
            "sp_x509_cert": {"required": False},
        }

    def validate_attribute_mapping(self, value):
        if value in (None, ""):
            return default_attribute_mapping()
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be a JSON object.")
        unknown = set(value.keys()) - ALLOWED_ATTRIBUTE_KEYS
        if unknown:
            raise serializers.ValidationError(
                f"Unknown keys: {', '.join(sorted(unknown))}"
            )
        for k, v in value.items():
            if not isinstance(v, str) or not v:
                raise serializers.ValidationError(
                    f"Value for '{k}' must be a non-empty string."
                )
        return value


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("features.saml")
def saml_config_view(request):
    """GET / PUT / PATCH the current tenant's SAML config.

    On write, if ``idp_metadata_xml`` is provided, we parse it and auto
    -populate ``idp_entity_id``, ``idp_sso_url``, ``idp_slo_url`` and
    ``idp_x509_certs`` so admins don't copy-paste each piece by hand.
    """
    tenant = request.tenant
    config, _ = TenantSAMLConfig.objects.get_or_create(
        tenant=tenant,
        defaults={"sp_entity_id": f"saml-sp:{tenant.subdomain}"},
    )

    if request.method == "GET":
        data = _SAMLConfigSerializer(config).data
        # Redact sensitive values in responses.
        data["sp_private_key_configured"] = bool(config.sp_private_key)
        return Response(data)

    serializer = _SAMLConfigSerializer(
        config, data=request.data, partial=(request.method == "PATCH")
    )
    serializer.is_valid(raise_exception=True)
    config = serializer.save()

    # If admin supplied metadata XML, parse it to fill in the other fields.
    metadata_xml = request.data.get("idp_metadata_xml")
    if metadata_xml:
        try:
            parsed = parse_idp_metadata(metadata_xml)
            config.idp_entity_id = parsed["entity_id"] or config.idp_entity_id
            config.idp_sso_url = parsed["sso_url"] or config.idp_sso_url
            config.idp_slo_url = parsed["slo_url"] or config.idp_slo_url
            config.idp_x509_certs = parsed["certs"]
            config.save(
                update_fields=[
                    "idp_entity_id",
                    "idp_sso_url",
                    "idp_slo_url",
                    "idp_x509_certs",
                ]
            )
        except SAMLValidationError as exc:
            return Response(
                {"error": f"Invalid IdP metadata: {exc.message}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Allow private key upload only on write and never echo it back.
    # Stored Fernet-encrypted at rest via the model helper.
    if "sp_private_key" in request.data:
        config.set_sp_private_key(request.data["sp_private_key"] or "")
        config.save(update_fields=["sp_private_key"])

    try:
        config.full_clean()
    except Exception as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    log_audit(
        "SETTINGS_CHANGE",
        "TenantSAMLConfig",
        target_id=str(config.id),
        target_repr=f"SAML config for {tenant.subdomain}",
        request=request,
    )

    data = _SAMLConfigSerializer(config).data
    data["sp_private_key_configured"] = bool(config.sp_private_key)
    return Response(data)
