# Generated migration for LessonQuizResponse model

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0016_interactive_lesson_v2_fields"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LessonQuizResponse",
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
                (
                    "scene_id",
                    models.CharField(
                        help_text="UUID of the quiz scene",
                        max_length=36,
                    ),
                ),
                (
                    "scene_index",
                    models.IntegerField(
                        help_text="Index of the scene in the lesson",
                    ),
                ),
                (
                    "selected_option_id",
                    models.CharField(
                        help_text="UUID of the selected option",
                        max_length=36,
                    ),
                ),
                (
                    "is_correct",
                    models.BooleanField(
                        help_text="Whether the selected answer was correct",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "lesson",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quiz_responses",
                        to="courses.interactivelesson",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lesson_quiz_responses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lesson_quiz_responses",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "lesson_quiz_responses",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="lessonquizresponse",
            index=models.Index(
                fields=["tenant", "teacher", "lesson"],
                name="lesson_quiz_tenant__idx",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="lessonquizresponse",
            unique_together={("lesson", "teacher", "scene_id")},
        ),
    ]
