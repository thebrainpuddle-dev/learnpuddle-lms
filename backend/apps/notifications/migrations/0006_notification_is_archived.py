# Migration: Add is_archived boolean field to Notification.
#
# Provides a simple boolean flag for user-initiated archival (via the
# PATCH /notifications/<id>/archive/ and POST /notifications/bulk-archive/
# endpoints).  The existing archived_at timestamp is retained for the
# Celery-based 90-day TTL archival flow.  The ActiveNotificationManager
# now filters on BOTH is_archived=False AND archived_at__isnull=True.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0005_notification_archived_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='is_archived',
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
