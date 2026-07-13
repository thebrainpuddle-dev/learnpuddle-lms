import json
import os
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.ai_classroom.models import TenantAIProviderCredential
from apps.ai_classroom.serializers import ProviderCredentialSerializer
from apps.ai_classroom.services import bump_provider_config_version, runtime_config_for
from apps.tenants.models import Tenant
from utils.audit import log_audit


def _resolve_tenant(identifier):
    try:
        tenant_id = uuid.UUID(identifier)
    except (ValueError, TypeError):
        tenant_id = None
    if tenant_id:
        tenant = Tenant.objects.filter(id=tenant_id).first()
        if tenant:
            return tenant
    tenant = Tenant.objects.filter(slug=identifier).first()
    if tenant:
        return tenant
    tenant = Tenant.objects.filter(subdomain=identifier).first()
    if tenant:
        return tenant
    raise CommandError(f"Tenant not found: {identifier}")


class Command(BaseCommand):
    help = "Provision a LearnPuddle-managed OpenMAIC provider without exposing its key to a school."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant UUID, slug, or subdomain")
        parser.add_argument(
            "--modality",
            required=True,
            choices=[value for value, _label in TenantAIProviderCredential.MODALITY_CHOICES],
        )
        parser.add_argument("--provider", required=True)
        parser.add_argument("--display-name")
        parser.add_argument("--models", help="Comma-separated exact model IDs")
        parser.add_argument("--base-url")
        parser.add_argument("--provider-config-json")
        parser.add_argument(
            "--api-key-env",
            help="Name of the environment variable containing the provider key. Raw keys are rejected.",
        )
        parser.add_argument("--enabled", choices=["yes", "no", "unchanged"], default="unchanged")
        parser.add_argument("--default", choices=["yes", "no", "unchanged"], default="unchanged")
        parser.add_argument("--delete", action="store_true")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        tenant = _resolve_tenant(options["tenant"])
        runtime_config_for(tenant)
        identity = {
            "tenant": tenant,
            "modality": options["modality"],
            "provider_id": options["provider"],
        }
        credential = TenantAIProviderCredential.all_objects.filter(**identity).first()

        if options["delete"]:
            if not credential:
                raise CommandError("Managed provider does not exist")
            self.stdout.write(
                f"Delete {credential.modality}:{credential.provider_id} for {tenant.name} ({tenant.id})"
            )
            self._require_confirmation(options)
            credential_id = credential.id
            with transaction.atomic():
                credential.delete()
                bump_provider_config_version(tenant)
                log_audit(
                    "DELETE",
                    "TenantAIProviderCredential",
                    target_id=credential_id,
                    target_repr=f"{options['modality']}:{options['provider']}",
                    tenant=tenant,
                    changes={"source": "managed_provider_command"},
                )
            self.stdout.write(self.style.SUCCESS("Managed provider removed."))
            return

        data = {}
        if not credential:
            data.update(
                modality=options["modality"],
                provider_id=options["provider"],
                is_enabled=True,
                is_default=not TenantAIProviderCredential.all_objects.filter(
                    tenant=tenant,
                    modality=options["modality"],
                    is_default=True,
                ).exists(),
            )
        if options["display_name"] is not None:
            data["display_name"] = options["display_name"]
        if options["models"] is not None:
            data["model_allowlist"] = [
                model.strip() for model in options["models"].split(",") if model.strip()
            ]
        if options["base_url"] is not None:
            data["base_url"] = options["base_url"]
        if options["provider_config_json"] is not None:
            try:
                provider_config = json.loads(options["provider_config_json"])
            except json.JSONDecodeError as exc:
                raise CommandError("--provider-config-json must be valid JSON") from exc
            if not isinstance(provider_config, dict):
                raise CommandError("--provider-config-json must contain a JSON object")
            data["provider_config"] = provider_config
        if options["enabled"] != "unchanged":
            data["is_enabled"] = options["enabled"] == "yes"
        if options["default"] != "unchanged":
            data["is_default"] = options["default"] == "yes"

        key_env = options["api_key_env"]
        if key_env:
            api_key = os.environ.get(key_env, "")
            if not api_key:
                raise CommandError(f"{key_env} is not set or is empty")
            data["api_key"] = api_key
        elif not credential:
            raise CommandError("New managed providers require --api-key-env")

        action = "Update" if credential else "Create"
        self.stdout.write(
            f"{action} {options['modality']}:{options['provider']} for {tenant.name} ({tenant.id})\n"
            f"Key source: {key_env or 'retain encrypted key'}"
        )
        self._require_confirmation(options)

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

        with transaction.atomic():
            if serializer.validated_data.get("is_default"):
                TenantAIProviderCredential.all_objects.filter(
                    tenant=tenant,
                    modality=options["modality"],
                    is_default=True,
                ).exclude(pk=getattr(credential, "pk", None)).update(is_default=False)
            saved = serializer.save()
            bump_provider_config_version(tenant)
            log_audit(
                "UPDATE" if credential else "CREATE",
                "TenantAIProviderCredential",
                target_id=saved.id,
                target_repr=f"{saved.modality}:{saved.provider_id}",
                tenant=tenant,
                changes={
                    "source": "managed_provider_command",
                    "key_rotated": bool(key_env),
                    "model_allowlist": saved.model_allowlist,
                    "enabled": saved.is_enabled,
                    "default": saved.is_default,
                },
            )

        self.stdout.write(self.style.SUCCESS("Managed provider provisioned and marked unverified."))

    @staticmethod
    def _require_confirmation(options):
        if not options["confirm"]:
            raise CommandError("No changes applied. Re-run with --confirm after review.")
