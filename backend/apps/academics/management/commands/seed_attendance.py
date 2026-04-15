# apps/academics/management/commands/seed_attendance.py
"""
Seed realistic attendance data for the Keystone demo tenant.

Usage:
    python manage.py seed_attendance
    python manage.py seed_attendance --days 30
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.academics.models import Section
from apps.academics.attendance_models import Attendance


class Command(BaseCommand):
    help = "Seed attendance data for the Keystone demo tenant"

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='Number of days to seed (default: 30)')

    def handle(self, *args, **options):
        days = options['days']

        try:
            tenant = Tenant.objects.get(subdomain='keystone')
        except Tenant.DoesNotExist:
            self.stderr.write("Keystone tenant not found. Run seed_keystone first.")
            return

        sections = Section.all_objects.filter(tenant=tenant)
        if not sections.exists():
            self.stderr.write("No sections found. Run seed_keystone first.")
            return

        today = timezone.localdate()
        start_date = today - timedelta(days=days)
        # Skip weekends
        school_days = [
            start_date + timedelta(days=i)
            for i in range(days + 1)
            if (start_date + timedelta(days=i)).weekday() < 5  # Mon-Fri
        ]

        created_count = 0

        for section in sections:
            students = User.all_objects.filter(
                tenant=tenant, section_fk=section,
                role='STUDENT', is_deleted=False,
            )
            if not students.exists():
                continue

            for day in school_days:
                records = []
                for student in students:
                    # Realistic distribution: ~86% present, ~8% late, ~4% absent, ~2% excused
                    rand = random.random()
                    if rand < 0.86:
                        status_val = 'PRESENT'
                    elif rand < 0.94:
                        status_val = 'LATE'
                    elif rand < 0.98:
                        status_val = 'ABSENT'
                    else:
                        status_val = 'EXCUSED'

                    records.append(Attendance(
                        tenant=tenant,
                        section=section,
                        student=student,
                        date=day,
                        status=status_val,
                        remarks='',
                    ))

                # Bulk create, ignore conflicts on (section, student, date)
                Attendance.objects.bulk_create(records, ignore_conflicts=True)
                created_count += len(records)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created_count} attendance records across {sections.count()} sections for {len(school_days)} school days."
        ))
