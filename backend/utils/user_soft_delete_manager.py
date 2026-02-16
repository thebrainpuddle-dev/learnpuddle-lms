# utils/user_soft_delete_manager.py
"""
Combined User Manager with soft-delete and tenant filtering support.

This manager extends Django's BaseUserManager to support:
1. Soft delete filtering (excludes is_deleted=True by default)
2. Tenant filtering (for multi-tenant queries)
3. Standard user creation methods (create_user, create_superuser)
"""

from django.contrib.auth.models import BaseUserManager
from django.db import models
from django.utils import timezone

from .tenant_middleware import get_current_tenant


class UserSoftDeleteQuerySet(models.QuerySet):
    """QuerySet for User model with soft-delete support."""

    def delete(self):
        """Soft-delete all users in the queryset."""
        return self.update(is_deleted=True, deleted_at=timezone.now(), is_active=False)

    def hard_delete(self):
        """Permanently delete all users."""
        return super().delete()

    def alive(self):
        """Return only non-deleted users."""
        return self.filter(is_deleted=False)

    def dead(self):
        """Return only soft-deleted users."""
        return self.filter(is_deleted=True)

    def filter_by_tenant(self):
        """Filter by current tenant context."""
        tenant = get_current_tenant()
        if tenant:
            return self.filter(tenant=tenant)
        return self


class UserSoftDeleteManager(BaseUserManager):
    """
    Custom User manager combining soft-delete with user creation methods.
    
    This manager:
    - Filters out soft-deleted users by default
    - Provides create_user() and create_superuser() methods required by Django
    - Supports tenant filtering for multi-tenant queries
    """

    def get_queryset(self):
        """Return queryset excluding soft-deleted users."""
        return UserSoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self):
        """Include soft-deleted users in results."""
        return UserSoftDeleteQuerySet(self.model, using=self._db)

    def deleted_only(self):
        """Return only soft-deleted users."""
        return UserSoftDeleteQuerySet(self.model, using=self._db).dead()

    def for_tenant(self, tenant=None):
        """
        Get users for a specific tenant or current tenant context.
        
        Args:
            tenant: Optional tenant instance. If None, uses current tenant from middleware.
        """
        qs = self.get_queryset()
        if tenant:
            return qs.filter(tenant=tenant)
        current_tenant = get_current_tenant()
        if current_tenant:
            return qs.filter(tenant=current_tenant)
        return qs

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular User with the given email and password.
        
        Args:
            email: User's email address (required, used as username)
            password: User's password (optional for social auth scenarios)
            **extra_fields: Additional fields for the User model
        
        Returns:
            User instance
        
        Raises:
            ValueError: If email is not provided
        """
        if not email:
            raise ValueError('Email is required')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        
        Superusers have:
        - is_staff=True (can access Django admin)
        - is_superuser=True (has all permissions)
        - role='SUPER_ADMIN' (platform-level admin)
        - No tenant association (platform-wide access)
        
        Args:
            email: Superuser's email address
            password: Superuser's password
            **extra_fields: Additional fields
        
        Returns:
            User instance with superuser privileges
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPER_ADMIN')
        extra_fields.setdefault('email_verified', True)  # Superusers are auto-verified
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)


class AllUsersManager(models.Manager):
    """
    Fallback manager that includes all users (including soft-deleted).
    
    Use this when you explicitly need to access soft-deleted users,
    such as for admin recovery or audit purposes.
    """

    def get_queryset(self):
        return UserSoftDeleteQuerySet(self.model, using=self._db)
