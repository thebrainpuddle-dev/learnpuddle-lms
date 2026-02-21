# apps/tenants/management/commands/create_demo_tenant.py

import os
import secrets
from django.core.management.base import BaseCommand
from apps.tenants.services import TenantService
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Creates a demo tenant for local development'
    
    def handle(self, *args, **options):
        admin_email = os.getenv('DEMO_TENANT_ADMIN_EMAIL', 'admin@example.test')
        admin_password = os.getenv('DEMO_TENANT_ADMIN_PASSWORD') or secrets.token_urlsafe(18)

        # Check if demo tenant exists
        if Tenant.objects.filter(subdomain='demo').exists():
            self.stdout.write(self.style.WARNING('Demo tenant already exists'))
            tenant = Tenant.objects.get(subdomain='demo')
            self.stdout.write(f"Subdomain: {tenant.subdomain}")
            self.stdout.write(f"Name: {tenant.name}")
            return
        
        # Create demo tenant
        result = TenantService.create_tenant_with_admin(
            name='Demo School',
            email=admin_email,
            admin_first_name='Demo',
            admin_last_name='Admin',
            admin_password=admin_password
        )
        
        # Update subdomain to 'demo' specifically for development
        tenant = result['tenant']
        tenant.subdomain = 'demo'
        tenant.save()
        
        self.stdout.write(self.style.SUCCESS('✅ Demo tenant created successfully!'))
        self.stdout.write(f"Subdomain: demo")
        self.stdout.write(f"Admin email: {admin_email}")
        self.stdout.write("Admin password: generated or provided via DEMO_TENANT_ADMIN_PASSWORD (not printed)")
        self.stdout.write(f"Login URL: http://localhost:8000")
