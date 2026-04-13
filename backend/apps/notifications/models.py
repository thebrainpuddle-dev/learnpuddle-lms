import uuid
from django.db import models

from utils.tenant_manager import TenantManager


class ActiveNotificationManager(TenantManager):
    """
    Default manager for Notification.

    Extends TenantManager (auto-filters by current tenant) with an additional
    filter that excludes archived notifications.  This means any code that
    calls ``Notification.objects.all()`` will never see stale/archived rows —
    exactly what the application wants during normal operation.

    Use ``Notification.all_objects`` when you need to reach archived rows
    (e.g., the archival/deletion Celery tasks themselves).
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_archived=False, archived_at__isnull=True)


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
    is_actionable = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # Archival — can be set manually by the user or by the archive_old_notifications
    # Celery task.  Notifications are archived after 90 days and hard-deleted
    # 30 days later.
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # Default manager: tenant-scoped + excludes archived rows.
    objects = ActiveNotificationManager()
    # Bypass manager: use for archival/deletion tasks that must reach all rows.
    all_objects = models.Manager()

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'teacher', 'is_read'], name='notif_tenant_teacher_read_idx'),
            models.Index(fields=['tenant', 'teacher', '-created_at'], name='notif_tnt_tch_created_idx'),
            models.Index(fields=['tenant', 'teacher', 'is_actionable', 'is_read'], name='notif_tnt_tch_act_read_idx'),
        ]

    def __str__(self):
        return f"{self.notification_type}: {self.title} -> {self.teacher.email}"
