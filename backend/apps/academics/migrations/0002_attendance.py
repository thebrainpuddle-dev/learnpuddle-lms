# apps/academics/migrations/0002_attendance.py
# Generated migration for Attendance model.

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial_academic_structure'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attendance',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField()),
                ('status', models.CharField(choices=[('PRESENT', 'Present'), ('ABSENT', 'Absent'), ('LATE', 'Late'), ('EXCUSED', 'Excused')], default='PRESENT', max_length=10)),
                ('remarks', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('section', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='academics.section')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='tenants.tenant')),
            ],
            options={
                'db_table': 'attendance',
                'ordering': ['-date', 'student__last_name'],
                'unique_together': {('tenant', 'section', 'student', 'date')},
            },
        ),
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(fields=['tenant', 'section', 'date'], name='attendance_tenant__1a9b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(fields=['tenant', 'student', 'date'], name='attendance_tenant__3d4e5f_idx'),
        ),
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(fields=['tenant', 'date'], name='attendance_tenant__6g7h8i_idx'),
        ),
    ]
