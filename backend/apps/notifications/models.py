import uuid
from django.db import models


class Notification(models.Model):
    """
    In-app notifications for teachers.
    Created when admin sends reminders, assigns courses, etc.
    """
    NOTIFICATION_TYPES = [
        ('REMINDER', 'Reminder'),
        ('COURSE_ASSIGNED', 'Course Assigned'),
        ('ASSIGNMENT_DUE', 'Assignment Due'),
        ('ANNOUNCEMENT', 'Announcement'),
        ('SYSTEM', 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='notifications')
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='SYSTEM')
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Optional links to related objects
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, null=True, blank=True)
    assignment = models.ForeignKey('progress.Assignment', on_delete=models.CASCADE, null=True, blank=True)
    
    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['teacher', 'is_read']),
            models.Index(fields=['teacher', '-created_at']),
        ]

    def __str__(self):
        return f"{self.notification_type}: {self.title} -> {self.teacher.email}"
