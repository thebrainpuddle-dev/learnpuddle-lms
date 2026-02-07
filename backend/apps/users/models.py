# apps/users/models.py

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
import uuid


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPER_ADMIN')
        return self.create_user(email, password, **extra_fields)


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
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    
    # Groups (for course assignment)
    teacher_groups = models.ManyToManyField('courses.TeacherGroup', related_name='members', blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)

    # Notification preferences (JSON: {"email_courses": true, "email_assignments": true, ...})
    notification_preferences = models.JSONField(blank=True, default=dict)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    class Meta:
        db_table = 'users'
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['tenant', 'role']),
            models.Index(fields=['tenant', 'is_active']),
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
