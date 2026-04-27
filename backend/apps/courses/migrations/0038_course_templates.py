"""Course Templates library (TASK-049) — platform-level CourseTemplate model
+ Content.meta_json JSONField for storing placeholder markers after clone."""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0037_content_revisions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="content",
            name="meta_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name="CourseTemplate",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("slug", models.SlugField(max_length=200, unique=True)),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("TEACHING_SKILLS", "Teaching Skills"),
                            ("IB_PYP", "IB PYP"),
                            ("IB_MYP", "IB MYP"),
                            ("IB_DP", "IB DP"),
                            ("LEADERSHIP", "Leadership"),
                            ("WELLBEING", "Wellbeing"),
                            ("OTHER", "Other"),
                        ],
                        default="OTHER",
                        max_length=32,
                    ),
                ),
                ("language", models.CharField(default="en", max_length=10)),
                ("estimated_hours", models.PositiveIntegerField(default=0)),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("BEGINNER", "Beginner"),
                            ("INTERMEDIATE", "Intermediate"),
                            ("ADVANCED", "Advanced"),
                        ],
                        default="BEGINNER",
                        max_length=16,
                    ),
                ),
                ("thumbnail_url", models.URLField(blank=True, default="")),
                ("blueprint_json", models.JSONField(blank=True, default=dict)),
                ("is_published", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="authored_course_templates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "course_templates",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["category", "is_published"],
                        name="course_tpl_cat_pub_idx",
                    ),
                    models.Index(
                        fields=["language", "is_published"],
                        name="course_tpl_lang_pub_idx",
                    ),
                    models.Index(
                        fields=["level", "is_published"],
                        name="course_tpl_level_pub_idx",
                    ),
                ],
            },
        ),
    ]
