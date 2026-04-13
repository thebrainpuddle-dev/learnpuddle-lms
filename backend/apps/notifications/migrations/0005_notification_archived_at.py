# Migration: Add archived_at field to Notification for 90-day TTL archival.
#
# Notifications older than 90 days are stamped with archived_at by the
# archive_old_notifications Celery Beat task.  The ActiveNotificationManager
# filters archived_at__isnull=True so archived rows are invisible to normal
# application queries.  Hard-deletion occurs 30 days after archival via the
# delete_archived_notifications task (120-day total lifecycle).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0004_add_tenant_manager_and_update_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='archived_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
