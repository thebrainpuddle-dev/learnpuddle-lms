# apps/tenants/management/commands/create_demo_tenant.py

from django.core.management.base import BaseCommand
from apps.tenants.services import TenantService
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Creates a demo tenant for local development'
    
    def handle(self, *args, **options):
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
            email='admin@demo.com',
            admin_first_name='Demo',
            admin_last_name='Admin',
            admin_password='demo123'
        )
        
        # Update subdomain to 'demo' specifically for development
        tenant = result['tenant']
        tenant.subdomain = 'demo'
        tenant.save()
        
        self.stdout.write(self.style.SUCCESS('✅ Demo tenant created successfully!'))
        self.stdout.write(f"Subdomain: demo")
        self.stdout.write(f"Admin email: admin@demo.com")
        self.stdout.write(f"Admin password: demo123")
        self.stdout.write(f"Login URL: http://localhost:8000")
