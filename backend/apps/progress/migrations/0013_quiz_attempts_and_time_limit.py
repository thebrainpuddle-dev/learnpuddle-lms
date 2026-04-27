# Migration: Multiple quiz attempts + timed quizzes
#
# Quiz changes:
#   - max_attempts (PositiveIntegerField, default=1; 0 = unlimited)
#   - time_limit_minutes (PositiveIntegerField, nullable; NULL = no limit)
#
# QuizSubmission changes:
#   - attempt_number (PositiveIntegerField, default=1)  ← 1-based attempt counter
#   - started_at (DateTimeField, nullable)              ← when teacher began this attempt
#   - time_expired (BooleanField, default=False)        ← auto-submitted on timeout
#   - unique_together: ("quiz", "teacher") → ("quiz", "teacher", "attempt_number")
#   - New composite index on (quiz, teacher, attempt_number) for fast lookup

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0012_gamificationconfig_xp_per_lesson_reflection"),
    ]

    operations = [
        # ── Quiz — attempt and timing configuration ────────────────────────
        migrations.AddField(
            model_name="quiz",
            name="max_attempts",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Maximum number of attempts allowed. 0 = unlimited.",
            ),
        ),
        migrations.AddField(
            model_name="quiz",
            name="time_limit_minutes",
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
                help_text="Time limit per attempt in minutes. NULL = no time limit.",
            ),
        ),
        # ── QuizSubmission — per-attempt fields ─────────────────────────────
        migrations.AddField(
            model_name="quizsubmission",
            name="attempt_number",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Which attempt this is (1-based).",
            ),
        ),
        migrations.AddField(
            model_name="quizsubmission",
            name="started_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="Timestamp when the teacher began this attempt.",
            ),
        ),
        migrations.AddField(
            model_name="quizsubmission",
            name="time_expired",
            field=models.BooleanField(
                default=False,
                help_text="True if this submission was auto-submitted due to timeout.",
            ),
        ),
        # Change unique_together from (quiz, teacher) → (quiz, teacher, attempt_number).
        # Django will DROP the old constraint and CREATE the new one.
        migrations.AlterUniqueTogether(
            name="quizsubmission",
            unique_together={("quiz", "teacher", "attempt_number")},
        ),
        # Add index for fast per-attempt lookups.
        migrations.AddIndex(
            model_name="quizsubmission",
            index=models.Index(
                fields=["quiz", "teacher", "attempt_number"],
                name="quiz_sub_quiz_teacher_attempt_idx",
            ),
        ),
    ]
