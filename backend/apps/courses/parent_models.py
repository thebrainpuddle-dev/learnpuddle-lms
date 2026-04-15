"""
Parent Portal models.

ParentSession — Authenticated parent session via magic link.
Parents have no User account; they authenticate by email matching
a student's parent_email field.

ParentMagicToken — Single-use token for parent email verification.
"""

import secrets
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class ParentSession(models.Model):
    """
    Represents an authenticated parent session.
    Created when a parent verifies their magic link token.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='parent_sessions',
    )
    parent_email = models.EmailField()
    students = models.ManyToManyField(
        'users.User',
        related_name='parent_sessions',
        blank=True,
    )
    session_token = models.CharField(max_length=255, unique=True)
    refresh_token = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'parent_sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['tenant', 'parent_email'],
                name='parent_sess_tenant_email_idx',
            ),
        ]

    def __str__(self):
        return f"ParentSession({self.parent_email}) — {self.tenant}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def create_session(cls, tenant, parent_email, students):
        """Create a new active session with 24h expiry and 7-day refresh."""
        session = cls.objects.create(
            tenant=tenant,
            parent_email=parent_email,
            session_token=secrets.token_urlsafe(64),
            refresh_token=secrets.token_urlsafe(64),
            expires_at=timezone.now() + timedelta(hours=24),
        )
        session.students.set(students)
        return session


class ParentMagicToken(models.Model):
    """
    Single-use magic link token for parent authentication.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
    )
    parent_email = models.EmailField()
    token = models.CharField(max_length=255, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'parent_magic_tokens'

    def __str__(self):
        return f"MagicToken({self.parent_email})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired
