# apps/tenants/admin.py

from django.contrib import admin
from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'subdomain', 'is_active', 'is_trial', 'created_at']
    list_filter = ['is_active', 'is_trial']
    search_fields = ['name', 'email', 'subdomain']
    readonly_fields = ['id', 'created_at', 'updated_at']
