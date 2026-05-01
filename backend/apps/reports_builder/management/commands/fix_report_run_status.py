# apps/reports_builder/management/commands/fix_report_run_status.py
"""
Data-integrity repair command: update stale ReportRun.status = "failed" rows
to the canonical failure value "error".

Background
----------
A bug introduced in tasks.py line 374 set ``run.status = "failed"`` on
delivery-failure paths, but ``"failed"`` is not in ReportRun.STATUS_CHOICES:
    ("pending", "running", "success", "error")

The code bug was fixed in the 2026-04-28 patch (``run.status = "error"``).
This command repairs any rows that were written with the invalid status before
the patch landed.  Run once after deploying the patch; re-runs are safe
(idempotent — the WHERE clause selects nothing on an already-clean table).

Reviewer suggestion: REVIEW-VERDICT-BE-REPORT-BUILDER-DELIVERY-STATUS-2026-04-28.md

Usage
-----
    # Preview (no writes)
    python manage.py fix_report_run_status --dry-run

    # Apply
    python manage.py fix_report_run_status

    # Limit to a single tenant
    python manage.py fix_report_run_status --tenant-id <uuid>
"""

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Repair stale ReportRun rows whose status is the invalid value "
        "'failed' (not in STATUS_CHOICES) by updating them to 'error'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview the number of affected rows without writing to the DB.",
        )
        parser.add_argument(
            "--tenant-id",
            default=None,
            dest="tenant_id",
            help=(
                "Restrict the sweep to a single tenant UUID.  "
                "Useful for staged rollouts or verifying a specific tenant."
            ),
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        raw_tenant_id: str | None = options["tenant_id"]

        # Import here to avoid issues at import time (command is loaded lazily).
        from apps.reports_builder.models import ReportRun

        # Build the base queryset — all_objects bypasses TenantManager's
        # thread-local filtering so the command is safe to run from a shell
        # or cron job without a request context.
        qs = ReportRun.all_objects.filter(status="failed")

        if raw_tenant_id is not None:
            try:
                tenant_uuid = uuid.UUID(raw_tenant_id)
            except ValueError:
                raise CommandError(
                    f"Invalid --tenant-id '{raw_tenant_id}': must be a valid UUID."
                )
            qs = qs.filter(tenant_id=tenant_uuid)

        count = qs.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "No ReportRun rows with status='failed' found.  "
                    "Table is already clean — nothing to do."
                )
            )
            return

        tenant_note = f" (tenant {raw_tenant_id})" if raw_tenant_id else " (all tenants)"
        self.stdout.write(
            f"Found {count} ReportRun row(s) with status='failed'{tenant_note}."
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN — {count} row(s) would be updated to status='error'"
                    f"{tenant_note}.  Re-run without --dry-run to apply."
                )
            )
            return

        # Wrap in atomic so the update is all-or-nothing.
        with transaction.atomic():
            updated = qs.update(status="error")

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully updated {updated} ReportRun row(s): "
                f"status 'failed' → 'error'."
            )
        )
        self.stdout.write(
            "Next step: verify with "
            "ReportRun.all_objects.filter(status='failed').count() == 0."
        )
