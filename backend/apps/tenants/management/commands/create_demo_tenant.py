# apps/tenants/management/commands/create_demo_tenant.py

import os
from django.core.management.base import BaseCommand
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

    def handle(self, *args, **options):
        admin_email = os.getenv('DEMO_TENANT_ADMIN_EMAIL', DEMO_USERS[0]['email'])
        admin_password = os.getenv('DEMO_TENANT_ADMIN_PASSWORD', DEMO_USERS[0]['password'])

        # Check if demo tenant exists
        if Tenant.objects.filter(subdomain='demo').exists():
            tenant = Tenant.objects.get(subdomain='demo')
            self.stdout.write(self.style.WARNING('Demo tenant already exists'))
            self._ensure_users(tenant)
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
                user.set_password(user_data['password'])
                user.save()
                self.stdout.write(f"  Created {user_data['role']}: {user_data['email']}")

        # Ensure MAIC is enabled
        if not tenant.feature_maic:
            tenant.feature_maic = True
            tenant.save(update_fields=['feature_maic'])
            self.stdout.write('  Enabled feature_maic on tenant')

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
