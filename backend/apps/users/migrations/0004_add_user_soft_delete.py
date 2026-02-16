# Generated migration for User soft delete fields
# apps/users/migrations/0004_add_user_soft_delete.py

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_add_teacher_profile_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='deleted_by',
            field=models.ForeignKey(
                blank=True,
                help_text='Admin who soft-deleted this user',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='deleted_users',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['is_deleted'], name='users_is_dele_abc123_idx'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['tenant', 'is_deleted'], name='users_tenant__def456_idx'),
        ),
    ]
