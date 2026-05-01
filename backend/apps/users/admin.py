# apps/users/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from .scim_models import SCIMToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'tenant', 'role', 'is_active']
    list_filter = ['role', 'is_active', 'tenant']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['email']
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'tenant', 'role')}),
        ('Teacher Info', {'fields': ('employee_id', 'subjects', 'grades', 'department', 'date_of_joining')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    readonly_fields = ['created_at', 'updated_at', 'last_login']
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'tenant', 'role'),
        }),
    )


@admin.register(SCIMToken)
class SCIMTokenAdmin(admin.ModelAdmin):
    """
    Admin UI for SCIM Bearer tokens.

    The raw token value is *never* shown — only its SHA-256 hash, plus the
    operational fields (name, tenant, expiry, last-used).  Use the
    `/api/v1/admin/sso/scim-tokens/` endpoint to mint new tokens (the raw value
    is returned in the 201 response and cannot be recovered afterwards).
    """

    list_display = (
        "name",
        "tenant",
        "is_active",
        "expires_at",
        "last_used_at",
        "created_at",
        "created_by",
    )
    list_filter = ("is_active", "tenant", "expires_at")
    search_fields = ("name", "tenant__name", "tenant__subdomain")
    ordering = ("-created_at",)
    # token_hash is sensitive (treat as opaque); created_at/last_used_at are
    # auto-managed by the model.
    readonly_fields = ("id", "token_hash", "created_at", "last_used_at")
    fieldsets = (
        (None, {"fields": ("id", "name", "tenant", "is_active")}),
        ("Lifecycle", {"fields": ("expires_at", "last_used_at", "created_at")}),
        ("Audit", {"fields": ("created_by", "token_hash")}),
    )
