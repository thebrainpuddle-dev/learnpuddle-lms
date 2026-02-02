# apps/tenants/models.py

from django.db import models
from django.utils.text import slugify
import uuid


class Tenant(models.Model):
    """
    Represents a school/institution.
    Each tenant is completely isolated from others.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="School name")
    slug = models.SlugField(max_length=200, unique=True, help_text="URL-friendly identifier")
    subdomain = models.CharField(max_length=100, unique=True, help_text="e.g., schoolname.lms.com")
    
    # Contact Information
    email = models.EmailField(help_text="Primary contact email")
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # Branding
    logo = models.ImageField(upload_to='tenant_logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#1F4788', help_text="Hex color code")
    secondary_color = models.CharField(max_length=7, blank=True, default='', help_text="Optional hex color code")
    font_family = models.CharField(max_length=100, blank=True, default='Inter', help_text="CSS font-family name")
    
    # Status
    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=True)
    trial_end_date = models.DateField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants'
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['subdomain']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
