# Generated migration for Learning Path models

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0006_course_soft_delete_search_vector"),
        ("tenants", "0004_tenant_sso_2fa_custom_domain"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── LearningPath ────────────────────────────────────────────────
        migrations.CreateModel(
            name="LearningPath",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True)),
                ("thumbnail", models.ImageField(blank=True, null=True, upload_to="learning_path_thumbnails/")),
                ("is_published", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("assigned_to_all", models.BooleanField(default=False, help_text="Assign to all teachers")),
                ("estimated_hours", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="learning_paths", to="tenants.tenant")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_learning_paths", to=settings.AUTH_USER_MODEL)),
                ("assigned_groups", models.ManyToManyField(blank=True, related_name="learning_paths", to="courses.teachergroup")),
                ("assigned_teachers", models.ManyToManyField(blank=True, related_name="assigned_learning_paths", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "learning_paths",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="learningpath",
            index=models.Index(fields=["tenant", "is_published", "is_active"], name="lp_tenant_pub_active_idx"),
        ),

        # ── LearningPathCourse ──────────────────────────────────────────
        migrations.CreateModel(
            name="LearningPathCourse",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("order", models.PositiveIntegerField(default=1)),
                ("min_completion_percentage", models.PositiveSmallIntegerField(default=100, help_text="Minimum completion % to unlock dependent courses")),
                ("is_optional", models.BooleanField(default=False, help_text="Optional courses don't block path progression")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("learning_path", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="path_courses", to="courses.learningpath")),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="learning_path_entries", to="courses.course")),
                ("prerequisites", models.ManyToManyField(blank=True, related_name="dependents", to="courses.learningpathcourse")),
            ],
            options={
                "db_table": "learning_path_courses",
                "ordering": ["learning_path", "order"],
                "unique_together": {("learning_path", "course")},
            },
        ),
        migrations.AddIndex(
            model_name="learningpathcourse",
            index=models.Index(fields=["learning_path", "order"], name="lpc_path_order_idx"),
        ),

        # ── LearningPathProgress ────────────────────────────────────────
        migrations.CreateModel(
            name="LearningPathProgress",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("NOT_STARTED", "Not Started"), ("IN_PROGRESS", "In Progress"), ("COMPLETED", "Completed")], default="NOT_STARTED", max_length=20)),
                ("progress_percentage", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("courses_completed", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_accessed", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="learning_path_progress", to=settings.AUTH_USER_MODEL)),
                ("learning_path", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="progress_records", to="courses.learningpath")),
                ("current_course", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="courses.learningpathcourse")),
            ],
            options={
                "db_table": "learning_path_progress",
                "unique_together": {("teacher", "learning_path")},
            },
        ),
        migrations.AddIndex(
            model_name="learningpathprogress",
            index=models.Index(fields=["teacher", "status"], name="lpp_teacher_status_idx"),
        ),
        migrations.AddIndex(
            model_name="learningpathprogress",
            index=models.Index(fields=["learning_path", "status"], name="lpp_path_status_idx"),
        ),
    ]
