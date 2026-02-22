from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0006_quiz_question_types_and_selection_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TeacherQuestClaim",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quest_key", models.CharField(max_length=100)),
                ("claim_date", models.DateField()),
                ("points_awarded", models.PositiveIntegerField(default=0)),
                ("claimed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quest_claims",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "teacher_quest_claims",
                "ordering": ["-claimed_at"],
                "indexes": [
                    models.Index(fields=["teacher", "claim_date"], name="teacher_que_teacher_ad9057_idx"),
                    models.Index(fields=["teacher", "quest_key"], name="teacher_que_teacher_e0a053_idx"),
                ],
                "unique_together": {("teacher", "quest_key", "claim_date")},
            },
        ),
    ]
