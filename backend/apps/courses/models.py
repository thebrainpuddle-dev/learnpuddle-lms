# apps/courses/models.py

from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.utils.text import slugify
import uuid

from utils.tenant_manager import TenantManager
from utils.soft_delete import SoftDeleteMixin, SoftDeleteManager
from utils.tenant_soft_delete_manager import TenantSoftDeleteManager


class TeacherGroup(models.Model):
    """
    Groups for organizing teachers (e.g., by subject, grade, department).
    Used for bulk course assignment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='teacher_groups')
    
    name = models.CharField(max_length=200, help_text="e.g., 'Math Teachers', 'Grade 9'")
    description = models.TextField(blank=True)
    
    # Group type for filtering
    GROUP_TYPE_CHOICES = [
        ('SUBJECT', 'Subject-based'),
        ('GRADE', 'Grade-based'),
        ('DEPARTMENT', 'Department-based'),
        ('CUSTOM', 'Custom'),
    ]
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES, default='CUSTOM')
    
    objects = TenantManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'teacher_groups'
        unique_together = [('tenant', 'name')]
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class Course(SoftDeleteMixin, models.Model):
    """
    Represents a training course.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='courses')

    # Basic info
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300)
    description = models.TextField()
    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)

    # Course settings
    is_mandatory = models.BooleanField(default=False, help_text="Required for all teachers")
    deadline = models.DateField(null=True, blank=True, help_text="Completion deadline")
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Assignment
    assigned_to_all = models.BooleanField(default=False, help_text="Assign to all teachers")
    assigned_groups = models.ManyToManyField(TeacherGroup, related_name='courses', blank=True)
    assigned_teachers = models.ManyToManyField('users.User', related_name='assigned_courses', blank=True)

    # Status
    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Metadata
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='created_courses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Full-text search vector (PostgreSQL)
    search_vector = SearchVectorField(null=True, blank=True)

    objects = TenantSoftDeleteManager()
    all_objects = TenantManager()
    
    class Meta:
        db_table = 'courses'
        unique_together = [('tenant', 'slug')]
        ordering = ['-created_at']
        indexes = [
            # Composite indexes for common query patterns
            models.Index(fields=['tenant', 'is_published', 'is_active']),
            models.Index(fields=['tenant', 'is_mandatory', 'is_active']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['deadline']),
            # Full-text search
            GinIndex(fields=['search_vector'], name='course_search_vector_idx'),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or 'course'
            slug = base_slug
            counter = 1
            while Course.all_objects.filter(tenant=self.tenant, slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)
        # Update search vector after save
        self.update_search_vector()
    
    def update_search_vector(self):
        """Update the search vector for full-text search."""
        from django.contrib.postgres.search import SearchVector
        from django.db.models import Value
        
        # Combine title (weight A) and description (weight B)
        Course.objects.filter(pk=self.pk).update(
            search_vector=SearchVector('title', weight='A') + SearchVector('description', weight='B')
        )


class Module(SoftDeleteMixin, models.Model):
    """
    Course modules (sections/chapters).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Display order")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'modules'
        ordering = ['course', 'order']
        indexes = [
            models.Index(fields=['course', 'order']),
        ]

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Content(SoftDeleteMixin, models.Model):
    """
    Module content (videos, documents, links).
    """
    CONTENT_TYPE_CHOICES = [
        ('VIDEO', 'Video'),
        ('DOCUMENT', 'Document'),
        ('LINK', 'External Link'),
        ('TEXT', 'Text Content'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='contents')

    title = models.CharField(max_length=300)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    order = models.PositiveIntegerField(default=0)

    # File/URL storage
    file_url = models.URLField(blank=True, help_text="S3 URL or external link")
    file_size = models.BigIntegerField(null=True, blank=True, help_text="File size in bytes")
    duration = models.PositiveIntegerField(null=True, blank=True, help_text="Duration in seconds (for videos)")

    # Text content
    text_content = models.TextField(blank=True)

    # Settings
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'contents'
        ordering = ['module', 'order']
        indexes = [
            models.Index(fields=['module', 'order']),
        ]

    def __str__(self):
        return f"{self.module.title} - {self.title}"


# Ensure Django registers video-related models that live in a separate module.
# (Django auto-imports `apps.courses.models` but not sibling modules by default.)
from .video_models import VideoAsset, VideoTranscript  # noqa: E402,F401
