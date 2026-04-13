# apps/tenants/admin.py

from django.contrib import admin
from .models import Tenant, AuditLog, DemoBooking


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'subdomain', 'is_active', 'is_trial', 'plan', 'created_at']
    list_filter = ['is_active', 'is_trial', 'plan']
    search_fields = ['name', 'email', 'subdomain']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'target_type', 'target_repr', 'actor', 'timestamp']
    list_filter = ['action', 'target_type']
    search_fields = ['target_repr', 'actor__email']
    readonly_fields = ['id', 'timestamp']
    raw_id_fields = ['actor', 'tenant']


@admin.register(DemoBooking)
class DemoBookingAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'company', 'status', 'scheduled_at', 'created_at']
    list_filter = ['status']
    search_fields = ['name', 'email', 'company']
    readonly_fields = ['id', 'created_at']
