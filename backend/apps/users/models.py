# apps/users/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import uuid

from utils.user_soft_delete_manager import UserSoftDeleteManager, AllUsersManager


from utils.storage_paths import profile_picture_upload_to as profile_picture_upload_path


class User(AbstractUser):
    """
    Custom user model with tenant relationship.
    Extends Django's AbstractUser.
    """
    
    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Admin'),  # Platform admin (Anthropic team)
        ('SCHOOL_ADMIN', 'School Admin'),  # School principal/coordinator
        ('TEACHER', 'Teacher'),
        ('HOD', 'Head of Department'),
        ('IB_COORDINATOR', 'IB Coordinator'),
    ]
    
    # Override username to not be required
    username = None
    
    # Primary fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    # Tenant relationship (null for super admins)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True
    )
    
    # Role and permissions
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='TEACHER')
    
    # Teacher-specific fields
    employee_id = models.CharField(max_length=50, blank=True, help_text="School-assigned Teacher ID")
    subjects = models.JSONField(default=list, blank=True, help_text="List of subjects taught e.g. ['Mathematics', 'Physics']")
    grades = models.JSONField(default=list, blank=True, help_text="List of grades/classes e.g. ['Class 9', 'Class 10']")
    department = models.CharField(max_length=100, blank=True, help_text="e.g. Science, Mathematics, Languages")
    designation = models.CharField(max_length=100, blank=True, help_text="e.g. PGT, TGT, PRT, HOD, Vice Principal")
    date_of_joining = models.DateField(null=True, blank=True)
    bio = models.TextField(blank=True, default='', help_text="Short profile description")
    profile_picture = models.ImageField(upload_to=profile_picture_upload_path, blank=True, null=True)
    
    # Groups (for course assignment)
    teacher_groups = models.ManyToManyField('courses.TeacherGroup', related_name='members', blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)
    must_change_password = models.BooleanField(
        default=False,
        help_text="Force password change on next login (e.g., after bulk import)"
    )

    # Soft delete fields
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_users',
        help_text="Admin who soft-deleted this user"
    )

    # Notification preferences (JSON: {"email_courses": true, "email_assignments": true, ...})
    notification_preferences = models.JSONField(blank=True, default=dict)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    # Managers - soft delete by default, all_objects includes deleted
    objects = UserSoftDeleteManager()
    all_objects = AllUsersManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    class Meta:
        db_table = 'users'
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['tenant', 'role']),
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['is_deleted']),
            models.Index(fields=['tenant', 'is_deleted']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def is_admin(self):
        return self.role in ['SUPER_ADMIN', 'SCHOOL_ADMIN']
    
    @property
    def is_teacher(self):
        return self.role == 'TEACHER'

    def delete(self, using=None, keep_parents=False, deleted_by=None):
        """
        Soft-delete this user.
        
        Sets is_deleted=True, is_active=False, and records deletion metadata.
        The user's data is preserved for audit/recovery purposes.
        
        Args:
            deleted_by: Optional User who performed the deletion (for audit trail)
        """
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=['is_deleted', 'is_active', 'deleted_at', 'deleted_by'])

    def hard_delete(self, using=None, keep_parents=False):
        """
        Permanently delete this user from the database.
        
        WARNING: This is irreversible. Use only for GDPR compliance or
        data cleanup after appropriate retention period.
        """
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self, restored_by=None):
        """
        Restore a soft-deleted user.
        
        Re-enables the user account while preserving audit trail.
        Note: is_active is set to True, but email_verified state is preserved.
        
        Args:
            restored_by: Optional User who performed the restoration
        """
        self.is_deleted = False
        self.is_active = True
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'is_active', 'deleted_at', 'deleted_by'])
