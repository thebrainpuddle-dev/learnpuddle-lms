# apps/courses/learning_path_models.py
"""
Learning Path models for structured course sequences.

Learning paths allow admins to:
- Create ordered sequences of courses
- Set prerequisites between courses
- Track progress across the entire path
"""

import uuid
from django.db import models
from utils.tenant_manager import TenantManager


def learning_path_thumbnail_upload_path(instance, filename):
    """
    Generate tenant-scoped upload path for learning path thumbnails.
    Format: learning_path_thumbnails/tenant/{tenant_id}/{uuid}_{ext}
    """
    ext = ''
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return f"learning_path_thumbnails/tenant/{instance.tenant_id}/{unique_name}"


class LearningPath(models.Model):
    """
    An ordered collection of courses with prerequisites.
    
    Teachers must complete courses in sequence to progress
    through the learning path.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='learning_paths'
    )
    
    # Basic info
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to=learning_path_thumbnail_upload_path, blank=True, null=True)
    
    # Status
    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Assignment
    assigned_to_all = models.BooleanField(default=False, help_text="Assign to all teachers")
    assigned_groups = models.ManyToManyField(
        'courses.TeacherGroup',
        related_name='learning_paths',
        blank=True
    )
    assigned_teachers = models.ManyToManyField(
        'users.User',
        related_name='assigned_learning_paths',
        blank=True
    )
    
    # Estimated completion
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Metadata
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_learning_paths'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = TenantManager()
    
    class Meta:
        db_table = 'learning_paths'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'is_published', 'is_active']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def course_count(self) -> int:
        return self.path_courses.count()
    
    def calculate_total_hours(self) -> float:
        """Calculate total estimated hours from all courses."""
        from django.db.models import Sum
        total = self.path_courses.aggregate(
            total=Sum('course__estimated_hours')
        )['total']
        return float(total or 0)


class LearningPathCourse(models.Model):
    """
    A course within a learning path with order and prerequisites.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name='path_courses'
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='learning_path_entries'
    )
    
    # Order in the path (1-based)
    order = models.PositiveIntegerField(default=1)
    
    # Prerequisites (other courses in the path that must be completed first)
    prerequisites = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='dependents',
        blank=True
    )
    
    # Optional: minimum score required to unlock next course
    min_completion_percentage = models.PositiveSmallIntegerField(
        default=100,
        help_text="Minimum completion % to unlock dependent courses"
    )
    
    # Status
    is_optional = models.BooleanField(
        default=False,
        help_text="Optional courses don't block path progression"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'learning_path_courses'
        unique_together = [('learning_path', 'course')]
        ordering = ['learning_path', 'order']
        indexes = [
            models.Index(fields=['learning_path', 'order']),
        ]
    
    def __str__(self):
        return f"{self.learning_path.title} - {self.order}. {self.course.title}"


class LearningPathProgress(models.Model):
    """
    Teacher progress through a learning path.
    """
    
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='learning_path_progress'
    )
    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.CASCADE,
        related_name='progress_records'
    )
    
    # Progress tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED')
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    courses_completed = models.PositiveIntegerField(default=0)
    
    # Current position
    current_course = models.ForeignKey(
        LearningPathCourse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    
    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'learning_path_progress'
        unique_together = [('teacher', 'learning_path')]
        indexes = [
            models.Index(fields=['teacher', 'status']),
            models.Index(fields=['learning_path', 'status']),
        ]
    
    def __str__(self):
        return f"{self.teacher.email} - {self.learning_path.title} ({self.status})"
    
    def calculate_progress(self):
        """Calculate progress based on completed courses."""
        from apps.progress.models import TeacherProgress
        
        total_courses = self.learning_path.path_courses.filter(is_optional=False).count()
        if total_courses == 0:
            return 0
        
        completed = 0
        for path_course in self.learning_path.path_courses.filter(is_optional=False):
            # Check if teacher completed this course
            course_progress = TeacherProgress.objects.filter(
                teacher=self.teacher,
                course=path_course.course,
                content__isnull=True,  # Course-level progress
                status='COMPLETED',
            ).first()
            
            if course_progress:
                completed += 1
        
        self.courses_completed = completed
        self.progress_percentage = (completed / total_courses) * 100
        
        if completed == 0:
            self.status = 'NOT_STARTED'
        elif completed >= total_courses:
            self.status = 'COMPLETED'
        else:
            self.status = 'IN_PROGRESS'
        
        return self.progress_percentage
