"""TASK-043 (2026-04-28) — Add QUIZ content type to Content.content_type choices.

A QuizConfig row is created lazily on first admin access via
GET/PATCH /api/v1/assessments/quiz-config/<content_id>/.

No data migration required: QUIZ is a new value; no existing rows use it.
No SQL schema change: choices= is Django-only metadata on a VARCHAR(20) column.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0044_classroom_image_tasks"),
    ]

    operations = [
        # Extend Content.content_type choices with QUIZ.
        # Adding a new choice is additive; max_length=20 already accommodates
        # 'QUIZ' (4 chars). No data migration needed.
        migrations.AlterField(
            model_name="content",
            name="content_type",
            field=models.CharField(
                choices=[
                    ("VIDEO", "Video"),
                    ("DOCUMENT", "Document"),
                    ("LINK", "External Link"),
                    ("TEXT", "Text Content"),
                    ("AI_CLASSROOM", "AI Classroom"),
                    ("CHATBOT", "AI Chatbot"),
                    ("SCORM", "SCORM Package"),
                    ("QUIZ", "Quiz"),
                ],
                max_length=20,
            ),
        ),
    ]
