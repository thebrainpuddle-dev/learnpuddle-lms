# utils/tenant_manager.py

from django.db import models
from .tenant_middleware import get_current_tenant


class TenantQuerySet(models.QuerySet):
    """
    QuerySet that automatically filters by current tenant.
    """
    
    def filter_by_tenant(self):
        tenant = get_current_tenant()
        if tenant:
            return self.filter(tenant=tenant)
        return self
    
    def all(self):
        """Override all() to always filter by tenant."""
        return self.filter_by_tenant()


class TenantManager(models.Manager):
    """
    Manager that uses TenantQuerySet.
    Use this for all tenant-scoped models.
    """
    
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db).filter_by_tenant()
    
    def all_tenants(self):
        """Get all records across all tenants (admin use only)."""
        return super().get_queryset()


class TenantAwareModel(models.Model):
    """
    Abstract base model for tenant-scoped models.
    Automatically filters queries by current tenant.
    
    Note: Models that already have a tenant field defined should NOT
    inherit from this. Instead, just add `objects = TenantManager()`.
    """
    
    # Note: tenant field should be defined in concrete models
    # to allow for custom related_name
    
    objects = TenantManager()
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        """Auto-set tenant on save if not set."""
        if hasattr(self, 'tenant_id') and not self.tenant_id:
            tenant = get_current_tenant()
            if tenant:
                self.tenant = tenant
        super().save(*args, **kwargs)
