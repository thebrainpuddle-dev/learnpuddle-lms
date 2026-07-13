import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ai_classroom.models import TenantAIRuntimeConfig
from apps.tenants.models import Tenant
from utils.audit import log_audit


class Command(BaseCommand):
    help = "Switch one tenant between the legacy and pinned OpenMAIC runtimes."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant UUID, slug, or subdomain")
        parser.add_argument(
            "--runtime",
            required=True,
            choices=[
                TenantAIRuntimeConfig.RUNTIME_LEGACY,
                TenantAIRuntimeConfig.RUNTIME_OPENMAIC,
            ],
        )
        parser.add_argument(
            "--student-generation",
            choices=["enabled", "disabled", "unchanged"],
            default="unchanged",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required to apply the runtime change.",
        )

    def handle(self, *args, **options):
        identifier = options["tenant"]
        tenant = None
        try:
            tenant_id = uuid.UUID(identifier)
        except (ValueError, TypeError):
            tenant_id = None
        if tenant_id:
            tenant = Tenant.objects.filter(id=tenant_id).first()
        if not tenant:
            tenant = Tenant.objects.filter(slug=identifier).first()
        if not tenant:
            tenant = Tenant.objects.filter(subdomain=identifier).first()
        if not tenant:
            raise CommandError(f"Tenant not found: {identifier}")

        config, _created = TenantAIRuntimeConfig.all_objects.get_or_create(tenant=tenant)
        old_runtime = config.runtime
        old_student_generation = config.student_generation_enabled
        student_generation = options["student_generation"]
        new_student_generation = old_student_generation
        if student_generation != "unchanged":
            new_student_generation = student_generation == "enabled"

        self.stdout.write(
            f"Tenant: {tenant.name} ({tenant.id})\n"
            f"Runtime: {old_runtime} -> {options['runtime']}\n"
            "Student generation: "
            f"{old_student_generation} -> {new_student_generation}"
        )
        if not options["confirm"]:
            raise CommandError("No changes applied. Re-run with --confirm after review.")

        with transaction.atomic():
            config = TenantAIRuntimeConfig.all_objects.select_for_update().get(pk=config.pk)
            config.runtime = options["runtime"]
            config.student_generation_enabled = new_student_generation
            config.save(
                update_fields=[
                    "runtime",
                    "student_generation_enabled",
                    "updated_at",
                ]
            )
            log_audit(
                "AI_CLASSROOM_RUNTIME_SWITCH",
                "TenantAIRuntimeConfig",
                target_id=config.id,
                target_repr=f"{old_runtime}->{config.runtime}",
                tenant=tenant,
                changes={
                    "old_runtime": old_runtime,
                    "new_runtime": config.runtime,
                    "old_student_generation": old_student_generation,
                    "new_student_generation": config.student_generation_enabled,
                    "source": "management_command",
                },
            )

        self.stdout.write(self.style.SUCCESS("AI Classroom runtime updated."))
