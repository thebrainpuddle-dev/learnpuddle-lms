# apps/academics/management/commands/seed_keystone.py
"""
Seed the Keystone International School tenant with full academic structure.

Usage:
    python manage.py seed_keystone
    python manage.py seed_keystone --reset   # Clear and re-create academic data

Creates:
- Tenant (subdomain: keystone)
- School Admin user
- 4 Grade Bands (Early Years, Primary, Middle, High School)
- 15 Grades (Nursery through Grade 12)
- 30 Sections (A + B for each grade)
- 14 Subjects with grade-appropriate applicability
"""

import os
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tenants.models import Tenant
from apps.academics.models import GradeBand, Grade, Section, Subject
from apps.users.models import User


KEYSTONE_USERS = [
    {
        'email': 'admin@keystoneeducation.in',
        'password': 'Keystone@123',
        'first_name': 'Keystone',
        'last_name': 'Admin',
        'role': 'SCHOOL_ADMIN',
    },
    {
        'email': 'teacher@keystoneeducation.in',
        'password': 'Teacher@123',
        'first_name': 'Keystone',
        'last_name': 'Teacher',
        'role': 'TEACHER',
    },
    {
        'email': 'student@keystoneeducation.in',
        'password': 'Student@123',
        'first_name': 'Keystone',
        'last_name': 'Student',
        'role': 'STUDENT',
    },
]


class Command(BaseCommand):
    help = 'Seeds Keystone International School with complete academic structure'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing Keystone academic data before seeding',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('\n═══ Keystone International School — Seed Data ═══\n'))

        # ─── 1. Tenant ────────────────────────────────────────────────
        tenant, tenant_created = Tenant.objects.get_or_create(
            subdomain='keystone',
            defaults={
                'name': 'Keystone International School',
                'slug': 'keystone-international',
                'email': 'admin@keystoneeducation.in',
                'phone': '',
                'address': 'Puppalguda, Financial District, Hyderabad, Telangana, India',
                'primary_color': '#00964B',
                'current_academic_year': '2026-27',
                'id_prefix': 'KIS',
                'student_id_counter': 1,
                'teacher_id_counter': 1,
                'white_label': True,
                'welcome_message': 'Welcome to Keystone Learning',
                'school_motto': 'Powered by the Idea-Loom Model',
                'plan': 'ENTERPRISE',
                'is_trial': False,
                'max_teachers': 200,
                'max_students': 2000,
                'max_courses': 500,
                'max_storage_mb': 50000,
                'feature_video_upload': True,
                'feature_auto_quiz': True,
                'feature_transcripts': True,
                'feature_reminders': True,
                'feature_custom_branding': True,
                'feature_reports_export': True,
                'feature_groups': True,
                'feature_certificates': True,
                'feature_teacher_authoring': True,
                'feature_ai_studio': True,
                'feature_students': True,
                'feature_sso': True,
                'feature_2fa': True,
            },
        )

        if tenant_created:
            self.stdout.write(self.style.SUCCESS('  ✓ Created tenant: Keystone International School'))
        else:
            self.stdout.write('  • Tenant already exists: Keystone International School')

        # Handle --reset
        if options['reset'] and not tenant_created:
            GradeBand.all_objects.filter(tenant=tenant).delete()
            Subject.all_objects.filter(tenant=tenant).delete()
            self.stdout.write(self.style.WARNING('  ⟳ Reset: deleted existing academic data'))

        # ─── 2. Users (Admin, Teacher, Student) ──────────────────────
        # Override admin email/password via env if set
        admin_email_env = os.getenv('KEYSTONE_ADMIN_EMAIL')
        admin_pass_env = os.getenv('KEYSTONE_ADMIN_PASSWORD')
        if admin_email_env:
            KEYSTONE_USERS[0]['email'] = admin_email_env
        if admin_pass_env:
            KEYSTONE_USERS[0]['password'] = admin_pass_env

        # Enable MAIC feature
        if not tenant.feature_maic:
            tenant.feature_maic = True
            tenant.save(update_fields=['feature_maic'])

        for user_data in KEYSTONE_USERS:
            user, created = User.objects.get_or_create(
                email=user_data['email'],
                defaults={
                    'first_name': user_data['first_name'],
                    'last_name': user_data['last_name'],
                    'role': user_data['role'],
                    'tenant': tenant,
                    'is_active': True,
                },
            )
            if created:
                user.set_password(user_data['password'])
                user.save()
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created {user_data["role"]}: {user_data["email"]}'))
            else:
                self.stdout.write(f'  • {user_data["role"]} already exists: {user_data["email"]}')

        # ─── 3. Grade Bands ──────────────────────────────────────────
        BAND_DEFS = [
            {
                'name': 'Early Years',
                'short_code': 'KEY',
                'order': 1,
                'curriculum_framework': 'REGGIO_EMILIA',
                'theme_config': {
                    'accent_color': '#8DC63F',
                    'bg_image': '',
                    'welcome_msg': 'Welcome, little explorer! 🌱',
                },
            },
            {
                'name': 'Primary',
                'short_code': 'PRI',
                'order': 2,
                'curriculum_framework': 'CAMBRIDGE_PRIMARY',
                'theme_config': {
                    'accent_color': '#00A99D',
                    'bg_image': '',
                    'welcome_msg': 'Ready to learn something amazing today?',
                },
            },
            {
                'name': 'Middle School',
                'short_code': 'MID',
                'order': 3,
                'curriculum_framework': 'CAMBRIDGE_SECONDARY',
                'theme_config': {
                    'accent_color': '#0072BC',
                    'bg_image': '',
                    'welcome_msg': 'Challenge yourself. Grow every day.',
                },
            },
            {
                'name': 'High School',
                'short_code': 'HS',
                'order': 4,
                'curriculum_framework': 'IGCSE',
                'theme_config': {
                    'accent_color': '#662D91',
                    'bg_image': '',
                    'welcome_msg': 'Your future starts with what you do today.',
                },
            },
        ]

        band_objs = {}
        for bd in BAND_DEFS:
            band, created = GradeBand.all_objects.get_or_create(
                tenant=tenant,
                name=bd['name'],
                defaults={
                    'short_code': bd['short_code'],
                    'order': bd['order'],
                    'curriculum_framework': bd['curriculum_framework'],
                    'theme_config': bd['theme_config'],
                },
            )
            band_objs[bd['short_code']] = band
            status = '✓' if created else '•'
            self.stdout.write(f'  {status} GradeBand: {bd["name"]} [{bd["curriculum_framework"]}]')

        # ─── 4. Grades ────────────────────────────────────────────────
        GRADE_DEFS = [
            # (band_code, name, short_code, order)
            ('KEY', 'Nursery', 'NUR', 1),
            ('KEY', 'PP1', 'PP1', 2),
            ('KEY', 'PP2', 'PP2', 3),
            ('PRI', 'Grade 1', 'G1', 4),
            ('PRI', 'Grade 2', 'G2', 5),
            ('PRI', 'Grade 3', 'G3', 6),
            ('PRI', 'Grade 4', 'G4', 7),
            ('PRI', 'Grade 5', 'G5', 8),
            ('MID', 'Grade 6', 'G6', 9),
            ('MID', 'Grade 7', 'G7', 10),
            ('MID', 'Grade 8', 'G8', 11),
            ('HS', 'Grade 9', 'G9', 12),
            ('HS', 'Grade 10', 'G10', 13),
            ('HS', 'Grade 11', 'G11', 14),
            ('HS', 'Grade 12', 'G12', 15),
        ]

        grade_objs = {}
        for band_code, name, short_code, order in GRADE_DEFS:
            grade, _ = Grade.all_objects.get_or_create(
                tenant=tenant,
                short_code=short_code,
                defaults={
                    'grade_band': band_objs[band_code],
                    'name': name,
                    'order': order,
                },
            )
            grade_objs[short_code] = grade

        self.stdout.write(self.style.SUCCESS(f'  ✓ {len(grade_objs)} grades (Nursery → Grade 12)'))

        # ─── 5. Sections (A + B per grade) ────────────────────────────
        section_count = 0
        for short_code, grade in grade_objs.items():
            for section_name in ['A', 'B']:
                _, created = Section.all_objects.get_or_create(
                    tenant=tenant,
                    grade=grade,
                    name=section_name,
                    academic_year=tenant.current_academic_year or '2026-27',
                )
                if created:
                    section_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ {section_count} sections created (A + B per grade)'))

        # ─── 6. Subjects ─────────────────────────────────────────────
        SUBJECT_DEFS = [
            # (name, code, department, from_grade_code, is_elective)
            ('English', 'ENG', 'Languages', 'NUR', False),
            ('Mathematics', 'MAT', 'Mathematics', 'NUR', False),
            ('Science', 'SCI', 'Science', 'NUR', False),
            ('Social Studies', 'SST', 'Humanities', 'G1', False),
            ('Hindi', 'HIN', 'Languages', 'G6', False),
            ('Computer Science', 'CS', 'Technology', 'G6', False),
            ('Physics', 'PHY', 'Science', 'G9', False),
            ('Chemistry', 'CHE', 'Science', 'G9', False),
            ('Biology', 'BIO', 'Science', 'G9', False),
            ('Economics', 'ECO', 'Commerce', 'G9', True),
            ('Business Studies', 'BUS', 'Commerce', 'G9', True),
            ('Psychology', 'PSY', 'Humanities', 'G11', True),
            ('Sociology', 'SOC', 'Humanities', 'G11', True),
            ('Art & Design', 'ART', 'Arts', 'G11', True),
        ]

        subject_count = 0
        for name, code, dept, from_code, is_elective in SUBJECT_DEFS:
            subject, created = Subject.all_objects.get_or_create(
                tenant=tenant,
                code=code,
                defaults={
                    'name': name,
                    'department': dept,
                    'is_elective': is_elective,
                },
            )

            # Set applicable grades (from_code and above)
            from_order = grade_objs[from_code].order
            applicable = [g for g in grade_objs.values() if g.order >= from_order]
            subject.applicable_grades.set(applicable)

            if created:
                subject_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ {subject_count} subjects with grade mappings'))

        # ─── Summary ─────────────────────────────────────────────────
        self.stdout.write(self.style.HTTP_INFO('\n═══ Seed Complete ═══'))
        self.stdout.write(f'''
  Tenant:        {tenant.name}
  Subdomain:     keystone
  Academic Year: {tenant.current_academic_year}
  ID Prefix:     {tenant.id_prefix}
  White Label:   {tenant.white_label}

  Grade Bands:   {len(band_objs)}
  Grades:        {len(grade_objs)}
  Sections:      {Section.all_objects.filter(tenant=tenant).count()}
  Subjects:      {Subject.all_objects.filter(tenant=tenant).count()}

  Login URL:     http://keystone.localhost:3000/login
''')
        self.stdout.write(self.style.SUCCESS('  ── Login Credentials ──'))
        self.stdout.write(f'  {"Role":<15} {"Email":<35} {"Password"}')
        self.stdout.write(f'  {"-"*15} {"-"*35} {"-"*15}')
        for u in KEYSTONE_USERS:
            self.stdout.write(f'  {u["role"]:<15} {u["email"]:<35} {u["password"]}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Done!\n'))
