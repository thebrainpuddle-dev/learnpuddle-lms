# Migration: Add performance indexes to ReminderDelivery.
#
# ReminderDelivery had no indexes beyond the implicit campaign_id and teacher_id FK indexes.
# Adding composite indexes for the three most common access patterns:
#   1. (campaign, status)   — list deliveries for a campaign filtered by status
#   2. (teacher, status)    — list a teacher's reminder history by status
#   3. (status, created_at) — batch processing of PENDING/FAILED deliveries ordered by age

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reminders', '0003_rename_reminder_cam_tenant__efcc47_idx_reminder_ca_tenant__851f01_idx_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='reminderdelivery',
            index=models.Index(
                fields=['campaign', 'status'],
                name='reminder_del_campaign_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='reminderdelivery',
            index=models.Index(
                fields=['teacher', 'status'],
                name='reminder_del_teacher_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='reminderdelivery',
            index=models.Index(
                fields=['status', 'created_at'],
                name='reminder_del_status_created_idx',
            ),
        ),
    ]
