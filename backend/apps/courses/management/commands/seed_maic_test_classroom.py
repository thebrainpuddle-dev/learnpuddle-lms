"""Seed a production-shaped MAIC classroom for end-to-end tests.

The seed is idempotent and uses the same demo credentials as
``create_demo_tenant``:

    teacher@demo.learnpuddle.com / Teacher@123
    student@demo.learnpuddle.com / Student@123

Speech actions do not carry fake audio URLs. Playback drives the real student
TTS endpoint when pre-generated audio is absent, matching production behavior.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.courses.demo_maic_seed import (
    DEMO_MAIC_CLASSROOM_TITLE,
    ensure_demo_ai_config,
    ensure_demo_maic_classroom,
)
from apps.courses.maic_models import MAICClassroom
from apps.tenants.models import Tenant
from apps.users.models import User


TENANT_SUBDOMAIN = "demo"
TENANT_NAME = "Demo School"
TEACHER_EMAIL = "teacher@demo.learnpuddle.com"
STUDENT_EMAIL = "student@demo.learnpuddle.com"
TEACHER_PASSWORD = "Teacher@123"
STUDENT_PASSWORD = "Student@123"


class Command(BaseCommand):
    help = "Seed a production-shaped MAIC classroom for e2e tests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete any existing seed classroom with the same title before recreating.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get("reset", False)

        tenant, tenant_created = Tenant.objects.get_or_create(
            subdomain=TENANT_SUBDOMAIN,
            defaults={
                "name": TENANT_NAME,
                "email": f"admin@{TENANT_SUBDOMAIN}.learnpuddle.com",
                "plan": "FREE",
            },
        )

        changed_fields: list[str] = []
        for field, value in {
            "feature_maic": True,
            "feature_students": True,
            "feature_ai_studio": True,
        }.items():
            if getattr(tenant, field) != value:
                setattr(tenant, field, value)
                changed_fields.append(field)
        if changed_fields:
            tenant.save(update_fields=changed_fields + ["updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if tenant_created else 'Using'} tenant '{tenant.subdomain}'"
            )
        )

        teacher, teacher_created = User.objects.get_or_create(
            email=TEACHER_EMAIL,
            defaults={
                "tenant": tenant,
                "role": "TEACHER",
                "first_name": "Demo",
                "last_name": "Teacher",
                "is_active": True,
            },
        )
        teacher.set_password(TEACHER_PASSWORD)
        teacher.tenant = tenant
        teacher.role = "TEACHER"
        teacher.is_active = True
        teacher.save()

        student, student_created = User.objects.get_or_create(
            email=STUDENT_EMAIL,
            defaults={
                "tenant": tenant,
                "role": "STUDENT",
                "first_name": "Demo",
                "last_name": "Student",
                "is_active": True,
            },
        )
        student.set_password(STUDENT_PASSWORD)
        student.tenant = tenant
        student.role = "STUDENT"
        student.is_active = True
        student.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if teacher_created else 'Updated'} teacher '{teacher.email}'"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if student_created else 'Updated'} student '{student.email}'"
            )
        )

        ai_config = ensure_demo_ai_config(tenant)
        self.stdout.write(
            self.style.SUCCESS(
                "Ensured TenantAIConfig "
                f"(tts={ai_config.tts_provider}, maic_enabled={ai_config.maic_enabled})"
            )
        )

        if reset:
            deleted, _ = (
                MAICClassroom.objects.all_tenants()
                .filter(tenant=tenant, title=DEMO_MAIC_CLASSROOM_TITLE)
                .delete()
            )
            if deleted:
                self.stdout.write(
                    self.style.WARNING(
                        f"Removed {deleted} prior seed classroom(s) titled "
                        f"'{DEMO_MAIC_CLASSROOM_TITLE}'"
                    )
                )

        existed = (
            MAICClassroom.objects.all_tenants()
            .filter(tenant=tenant, title=DEMO_MAIC_CLASSROOM_TITLE)
            .exists()
        )
        classroom = ensure_demo_maic_classroom(tenant=tenant, teacher=teacher)
        created_msg = "Refreshed" if existed else "Created"
        content = classroom.composed_content

        speech_count = sum(
            1 for action in content["scenes"][0]["actions"] if action.get("type") == "speech"
        )
        transition_count = sum(
            1 for action in content["scenes"][0]["actions"] if action.get("type") == "transition"
        )
        manifest = content["audioManifest"]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(f"  {created_msg} classroom"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  id:      {classroom.id}")
        self.stdout.write(f"  title:   {classroom.title}")
        self.stdout.write(f"  tenant:  {tenant.subdomain}")
        self.stdout.write(f"  status:  {classroom.status} (public={classroom.is_public})")
        self.stdout.write(f"  scenes:  {classroom.scene_count}")
        self.stdout.write(
            f"  actions: {speech_count} speech + {transition_count} transitions"
        )
        self.stdout.write(
            f"  manifest status: {manifest['status']} "
            f"({manifest['completedActions']}/{manifest['totalActions']})"
        )
        self.stdout.write("")
        self.stdout.write("  Login for e2e:")
        self.stdout.write(f"    teacher: {TEACHER_EMAIL} / {TEACHER_PASSWORD}")
        self.stdout.write(f"    student: {STUDENT_EMAIL} / {STUDENT_PASSWORD}")
        self.stdout.write("")
