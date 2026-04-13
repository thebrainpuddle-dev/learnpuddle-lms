"""
Management command to backfill tenant_id on progress-related models.

All progress models added a nullable ``tenant`` FK in migration
0009_add_tenant_isolation_to_progress_models.  New records always set the
tenant, but legacy rows created before that migration have ``tenant_id IS
NULL``.  This command derives the correct tenant from each model's parent
chain and fills it in.

Usage:
    # Preview what would be updated (no writes):
    python manage.py backfill_tenant --dry-run

    # Perform the backfill:
    python manage.py backfill_tenant
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.progress.models import (
    TeacherProgress,
    Assignment,
    AssignmentSubmission,
    Quiz,
    QuizQuestion,
    QuizSubmission,
    TeacherQuestClaim,
)


class Command(BaseCommand):
    help = "Backfill tenant_id on progress models where it is NULL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report counts without making any changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        total_updated = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no records will be modified.\n"))

        # Each entry: (model_class, select_related path to reach Course/tenant, attribute chain to get tenant_id)
        backfill_specs = [
            {
                "model": TeacherProgress,
                "label": "TeacherProgress",
                "select_related": ["course"],
                "get_tenant": lambda obj: obj.course.tenant_id if obj.course_id else None,
            },
            {
                "model": Assignment,
                "label": "Assignment",
                "select_related": ["course"],
                "get_tenant": lambda obj: obj.course.tenant_id if obj.course_id else None,
                # Assignment uses SoftDeleteMixin — all_objects reaches soft-deleted rows too.
            },
            {
                "model": Quiz,
                "label": "Quiz",
                "select_related": ["assignment__course"],
                "get_tenant": lambda obj: (
                    obj.assignment.course.tenant_id
                    if obj.assignment_id and obj.assignment.course_id
                    else None
                ),
            },
            {
                "model": QuizQuestion,
                "label": "QuizQuestion",
                "select_related": ["quiz__assignment__course"],
                "get_tenant": lambda obj: (
                    obj.quiz.assignment.course.tenant_id
                    if obj.quiz_id
                    and obj.quiz.assignment_id
                    and obj.quiz.assignment.course_id
                    else None
                ),
            },
            {
                "model": QuizSubmission,
                "label": "QuizSubmission",
                "select_related": ["quiz__assignment__course"],
                "get_tenant": lambda obj: (
                    obj.quiz.assignment.course.tenant_id
                    if obj.quiz_id
                    and obj.quiz.assignment_id
                    and obj.quiz.assignment.course_id
                    else None
                ),
            },
            {
                "model": AssignmentSubmission,
                "label": "AssignmentSubmission",
                "select_related": ["assignment__course"],
                "get_tenant": lambda obj: (
                    obj.assignment.course.tenant_id
                    if obj.assignment_id and obj.assignment.course_id
                    else None
                ),
            },
            {
                "model": TeacherQuestClaim,
                "label": "TeacherQuestClaim",
                "select_related": ["teacher"],
                "get_tenant": lambda obj: obj.teacher.tenant_id if obj.teacher_id else None,
            },
        ]

        for spec in backfill_specs:
            updated = self._backfill_model(spec, dry_run)
            total_updated += updated

        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN complete. {total_updated} record(s) would be updated.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Backfill complete. {total_updated} record(s) updated.")
            )

    def _backfill_model(self, spec: dict, dry_run: bool) -> int:
        model = spec["model"]
        label = spec["label"]
        select_related = spec["select_related"]
        get_tenant = spec["get_tenant"]
        # Management commands run without a request context, so TenantManager
        # (model.objects) would return empty querysets. Use all_objects to
        # bypass tenant filtering.
        manager = model.all_objects
        qs = manager.filter(tenant__isnull=True).select_related(*select_related)

        null_count = qs.count()
        if null_count == 0:
            self.stdout.write(f"  {label}: 0 rows with NULL tenant — nothing to do.")
            return 0

        self.stdout.write(f"  {label}: {null_count} row(s) with NULL tenant.")

        if dry_run:
            return null_count

        updated = 0
        skipped = 0
        batch: list = []

        for obj in qs.iterator(chunk_size=500):
            tenant_id = get_tenant(obj)
            if tenant_id is None:
                skipped += 1
                continue
            obj.tenant_id = tenant_id
            batch.append(obj)

            if len(batch) >= 500:
                with transaction.atomic():
                    model.all_objects.bulk_update(batch, ["tenant_id"])
                updated += len(batch)
                batch = []

        # Flush remaining
        if batch:
            with transaction.atomic():
                model.all_objects.bulk_update(batch, ["tenant_id"])
            updated += len(batch)

        msg = f"    -> Updated {updated} row(s)."
        if skipped:
            msg += f" Skipped {skipped} (could not derive tenant)."
        self.stdout.write(msg)
        return updated
