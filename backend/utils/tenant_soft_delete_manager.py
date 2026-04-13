# utils/tenant_soft_delete_manager.py

from django.db import models
from .tenant_middleware import get_current_tenant
from .soft_delete import SoftDeleteQuerySet


class TenantSoftDeleteQuerySet(SoftDeleteQuerySet):
    """QuerySet that filters by tenant AND excludes soft-deleted records."""

    def filter_by_tenant(self):
        tenant = get_current_tenant()
        if tenant:
            return self.filter(tenant=tenant)
        return self


class TenantSoftDeleteManager(models.Manager):
    """Manager combining tenant filtering and soft-delete."""

    def get_queryset(self):
        return (
            TenantSoftDeleteQuerySet(self.model, using=self._db)
            .alive()
            .filter_by_tenant()
        )

    def all_tenants(self):
        """All non-deleted records across all tenants."""
        return TenantSoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self):
        """All records including soft-deleted, for current tenant."""
        qs = TenantSoftDeleteQuerySet(self.model, using=self._db)
        tenant = get_current_tenant()
        if tenant:
            return qs.filter(tenant=tenant)
        return qs
