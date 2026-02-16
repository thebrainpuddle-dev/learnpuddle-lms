# apps/media/models.py

import uuid
from django.db import models

from utils.tenant_manager import TenantManager


class MediaAsset(models.Model):
    """
    Tenant-scoped media library for videos, documents, and links.
    Used by course content "From Library" picker and Media Library page.
    """
    MEDIA_TYPE_CHOICES = [
        ('VIDEO', 'Video'),
        ('DOCUMENT', 'Document'),
        ('LINK', 'Link'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='media_assets',
    )

    title = models.CharField(max_length=300)
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPE_CHOICES)

    # File storage (for VIDEO, DOCUMENT)
    file = models.FileField(upload_to='media_assets/%Y/%m/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)

    # URL (for LINK, or CDN URL for uploaded files)
    file_url = models.URLField(blank=True, help_text='External URL or CDN path for file')

    # Video-specific
    duration = models.PositiveIntegerField(null=True, blank=True, help_text='Duration in seconds')
    thumbnail_url = models.URLField(blank=True)

    # Metadata
    tags = models.JSONField(default=list, blank=True)  # List of tag strings
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_media',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'media_assets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'media_type']),
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self):
        return f"{self.title} ({self.media_type})"
