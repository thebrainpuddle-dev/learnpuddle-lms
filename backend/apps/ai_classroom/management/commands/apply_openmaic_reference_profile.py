import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.ai_classroom.management.commands.provision_openmaic_provider import _resolve_tenant
from apps.ai_classroom.models import TenantAIProviderCredential, TenantAIRuntimeConfig
from apps.ai_classroom.reference_profiles import (
    REFERENCE_PROFILE_ID,
    load_reference_profile,
    reference_profile_sha256,
)
from apps.ai_classroom.serializers import ProviderCredentialSerializer
from apps.ai_classroom.services import runtime_config_for
from utils.audit import log_audit


class Command(BaseCommand):
    help = "Atomically apply the certified OpenMAIC provider and output profile to one tenant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant UUID, slug, or subdomain")
        parser.add_argument("--profile", default=REFERENCE_PROFILE_ID)
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        tenant = _resolve_tenant(options["tenant"])
        profile = load_reference_profile(options["profile"])
        digest = reference_profile_sha256(profile)
        runtime_config_for(tenant)

        existing = {
            (credential.modality, credential.provider_id): credential
            for credential in TenantAIProviderCredential.all_objects.filter(tenant=tenant)
        }
        missing_secrets = []
        for entry in profile["providers"]:
            key = (entry["modality"], entry["provider_id"])
            env_name = entry["api_key_env"]
            if not os.environ.get(env_name, "") and not getattr(
                existing.get(key), "api_key_encrypted", ""
            ):
                missing_secrets.append(env_name)
        if missing_secrets:
            raise CommandError(
                "Missing managed provider secret environment variables: "
                + ", ".join(sorted(set(missing_secrets)))
            )

        self.stdout.write(
            f"Tenant: {tenant.name} ({tenant.id})\n"
            f"Profile: {profile['id']}\n"
            f"SHA-256: {digest}\n"
            f"Providers: {len(profile['providers'])}"
        )
        if not options["confirm"]:
            raise CommandError("No changes applied. Re-run with --confirm after review.")

        expected_keys = {
            (entry["modality"], entry["provider_id"]) for entry in profile["providers"]
        }
        with transaction.atomic():
            list(
                TenantAIProviderCredential.all_objects.select_for_update()
                .filter(tenant=tenant)
                .values_list("pk", flat=True)
            )
            config = TenantAIRuntimeConfig.all_objects.select_for_update().get(tenant=tenant)
            for credential in TenantAIProviderCredential.all_objects.filter(tenant=tenant):
                if (credential.modality, credential.provider_id) not in expected_keys:
                    credential.is_enabled = False
                    credential.is_default = False
                    credential.save(update_fields=["is_enabled", "is_default", "updated_at"])

            for entry in profile["providers"]:
                identity = {
                    "tenant": tenant,
                    "modality": entry["modality"],
                    "provider_id": entry["provider_id"],
                }
                credential = TenantAIProviderCredential.all_objects.filter(**identity).first()
                data = {
                    "modality": entry["modality"],
                    "provider_id": entry["provider_id"],
                    "display_name": entry["display_name"],
                    "base_url": entry.get("base_url", ""),
                    "model_allowlist": entry["model_allowlist"],
                    "provider_config": entry["provider_config"],
                    "is_enabled": True,
                    "is_default": True,
                }
                api_key = os.environ.get(entry["api_key_env"], "")
                if api_key:
                    data["api_key"] = api_key
                serializer = ProviderCredentialSerializer(
                    credential,
                    data=data,
                    partial=bool(credential),
                    context={"tenant": tenant},
                )
                try:
                    serializer.is_valid(raise_exception=True)
                except ValidationError as exc:
                    raise CommandError(str(exc.detail)) from exc
                saved = serializer.save()
                log_audit(
                    "UPDATE" if credential else "CREATE",
                    "TenantAIProviderCredential",
                    target_id=saved.id,
                    target_repr=f"{saved.modality}:{saved.provider_id}",
                    tenant=tenant,
                    changes={
                        "source": "openmaic_reference_profile",
                        "profile_id": profile["id"],
                        "key_rotated": bool(api_key),
                        "model_allowlist": saved.model_allowlist,
                    },
                )

            config.reference_profile_id = profile["id"]
            config.reference_profile_sha256 = digest
            config.provider_config_version += 1
            config.save(
                update_fields=[
                    "reference_profile_id",
                    "reference_profile_sha256",
                    "provider_config_version",
                    "updated_at",
                ]
            )
            log_audit(
                "AI_PROFILE_APPLY",
                "TenantAIRuntimeConfig",
                target_id=config.id,
                target_repr=profile["id"],
                tenant=tenant,
                changes={"profile_id": profile["id"], "sha256": digest},
            )

        self.stdout.write(self.style.SUCCESS("Certified OpenMAIC reference profile applied."))
