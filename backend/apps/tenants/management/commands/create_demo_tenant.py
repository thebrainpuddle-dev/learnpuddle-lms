# apps/tenants/management/commands/create_demo_tenant.py

import os
from django.core.management.base import BaseCommand
from apps.courses.demo_maic_seed import ensure_demo_ai_config, ensure_demo_maic_classroom
from apps.courses.demo_student_seed import ensure_demo_student_portal_content
from apps.tenants.services import TenantService
from apps.tenants.models import Tenant
from apps.users.models import User


# Default credentials for local development
DEMO_USERS = [
    {
        'email': 'admin@demo.learnpuddle.com',
        'password': 'Admin@123',
        'first_name': 'Demo',
        'last_name': 'Admin',
        'role': 'SCHOOL_ADMIN',
    },
    {
        'email': 'teacher@demo.learnpuddle.com',
        'password': 'Teacher@123',
        'first_name': 'Demo',
        'last_name': 'Teacher',
        'role': 'TEACHER',
    },
    {
        'email': 'student@demo.learnpuddle.com',
        'password': 'Student@123',
        'first_name': 'Demo',
        'last_name': 'Student',
        'role': 'STUDENT',
    },
]


class Command(BaseCommand):
    help = 'Creates a demo tenant with admin, teacher, and student accounts'

    # ── E2E test dependency note ──────────────────────────────────────────────
    # The default credentials in DEMO_USERS (above) are the source of truth for
    # the automated e2e test suite.  Specifically:
    #
    #   TEACHER_EMAIL    = 'teacher@demo.learnpuddle.com'  (DEMO_USERS[1]['email'])
    #   TEACHER_PASSWORD = 'Teacher@123'                   (DEMO_USERS[1]['password'])
    #
    # These defaults are read by:
    #   frontend/e2e/maic-full-playback.spec.js  (E2E_TEACHER_PASSWORD fallback)
    #   .github/workflows/e2e.yml               (E2E_TEACHER_PASSWORD fallback env)
    #
    # If you change either value here you MUST update the matching defaults in
    # both files above, and rotate the E2E_TEACHER_PASSWORD repository secret
    # in GitHub Settings → Secrets & Variables → Actions.
    # ─────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        admin_email = os.getenv('DEMO_TENANT_ADMIN_EMAIL', DEMO_USERS[0]['email'])
        admin_password = os.getenv('DEMO_TENANT_ADMIN_PASSWORD', DEMO_USERS[0]['password'])

        # Check if demo tenant exists
        if Tenant.objects.filter(subdomain='demo').exists():
            tenant = Tenant.objects.get(subdomain='demo')
            self.stdout.write(self.style.WARNING('Demo tenant already exists'))
            self._ensure_users(tenant)
            self._ensure_maic_demo(tenant)
            self._ensure_student_demo_content(tenant)
            self._print_credentials(tenant)
            return

        # Create demo tenant with admin
        result = TenantService.create_tenant_with_admin(
            name='Demo School',
            email=admin_email,
            admin_first_name='Demo',
            admin_last_name='Admin',
            admin_password=admin_password,
        )

        tenant = result['tenant']
        tenant.subdomain = 'demo'
        tenant.plan = 'ENTERPRISE'
        tenant.feature_maic = True
        tenant.feature_ai_studio = True
        tenant.feature_students = True
        tenant.feature_video_upload = True
        tenant.feature_auto_quiz = True
        tenant.feature_transcripts = True
        tenant.feature_certificates = True
        tenant.feature_teacher_authoring = True
        tenant.save()

        # Update the admin user's email if it differs from the default
        admin_user = result.get('admin')
        if admin_user and admin_user.email != DEMO_USERS[0]['email']:
            admin_user.email = DEMO_USERS[0]['email']
            admin_user.set_password(DEMO_USERS[0]['password'])
            admin_user.save()

        # Create teacher and student accounts
        self._ensure_users(tenant)
        self._ensure_maic_demo(tenant)
        self._ensure_student_demo_content(tenant)

        self.stdout.write(self.style.SUCCESS('\n  Demo tenant created successfully!\n'))
        self._print_credentials(tenant)

    def _ensure_users(self, tenant: Tenant) -> None:
        """Create any missing demo users."""
        for user_data in DEMO_USERS:
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
                self.stdout.write(f"  Created {user_data['role']}: {user_data['email']}")
            user.first_name = user_data['first_name']
            user.last_name = user_data['last_name']
            user.role = user_data['role']
            user.tenant = tenant
            user.is_active = True
            user.set_password(user_data['password'])
            user.save()

        feature_updates = []
        for field in (
            'feature_maic',
            'feature_ai_studio',
            'feature_students',
            'feature_video_upload',
            'feature_auto_quiz',
            'feature_transcripts',
            'feature_certificates',
            'feature_teacher_authoring',
        ):
            if not getattr(tenant, field):
                setattr(tenant, field, True)
                feature_updates.append(field)
        if feature_updates:
            tenant.save(update_fields=feature_updates)
            self.stdout.write(f"  Enabled demo features: {', '.join(feature_updates)}")

    def _ensure_maic_demo(self, tenant: Tenant) -> None:
        """Ensure the demo student portal has one real, playable MAIC classroom."""
        ensure_demo_ai_config(tenant)
        teacher = User.objects.get(email=DEMO_USERS[1]['email'])
        classroom = ensure_demo_maic_classroom(tenant=tenant, teacher=teacher)
        self.stdout.write(f"  Ensured MAIC demo classroom: {classroom.title} ({classroom.id})")

    def _ensure_student_demo_content(self, tenant: Tenant) -> None:
        """Ensure student portal smoke tests have real non-empty demo data."""
        seeded = ensure_demo_student_portal_content(tenant)
        self.stdout.write(
            "  Ensured student demo content: "
            f"course={seeded['course_id']} "
            f"thread={seeded['thread_id']} "
            f"chatbot={seeded['chatbot_id']}"
        )

    def _print_credentials(self, tenant: Tenant) -> None:
        """Print login credentials table."""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  Demo School — Login Credentials'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  Subdomain:  demo')
        self.stdout.write(f'  Login URL:  http://demo.localhost:3000/login')
        self.stdout.write('')
        self.stdout.write(f'  {"Role":<15} {"Email":<35} {"Password"}')
        self.stdout.write(f'  {"-"*15} {"-"*35} {"-"*12}')
        for u in DEMO_USERS:
            self.stdout.write(f'  {u["role"]:<15} {u["email"]:<35} {u["password"]}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
