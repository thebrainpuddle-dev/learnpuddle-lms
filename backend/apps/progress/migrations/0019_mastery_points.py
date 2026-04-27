# Migration: Mastery Points (TASK-018, Phase 4 Gamification)
#
# Additive-only.  Introduces a Mastery Point (MP) ledger separate from the
# existing XP ledger.  Mastery Points represent demonstrated competence
# (high-score quizzes, graded assignments, course completion bonuses) as a
# complement to XP, which represents effort.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0018_challenges"),
        ("tenants", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        # --- GamificationConfig: MP tunables ---------------------------------
        migrations.AddField(
            model_name="gamificationconfig",
            name="mp_quiz_threshold_percent",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=80,
                help_text=(
                    "Minimum quiz score percentage (0-100) required to award "
                    "Mastery Points. Scores below this threshold award XP only."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="mp_quiz_weight",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=1,
                help_text=(
                    "Multiplier applied to quiz score percentage when awarding "
                    "Mastery Points. MP = round(score_percent * weight)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="mp_assignment_weight",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=1,
                help_text=(
                    "Multiplier applied to assignment grade (out of max_score) "
                    "when awarding Mastery Points. MP = round(score * weight)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="mp_assignment_threshold_percent",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=80,
                help_text=(
                    "Minimum assignment score percentage (0-100) required to "
                    "award Mastery Points on an assignment grade."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="mp_course_bonus",
            field=models.PositiveIntegerField(
                default=50,
                help_text=(
                    "Flat Mastery Point bonus awarded on course completion "
                    "when the teacher's average quiz score in that course "
                    "meets the quiz threshold."
                ),
            ),
        ),
        # --- MasteryPointTransaction -----------------------------------------
        migrations.CreateModel(
            name="MasteryPointTransaction",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("quiz_mastery", "Quiz Mastery"),
                            ("assignment_mastery", "Assignment Mastery"),
                            ("course_mastery_bonus", "Course Mastery Bonus"),
                            ("admin_adjust", "Admin Adjustment"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "description",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "reference_id",
                    models.UUIDField(
                        blank=True,
                        help_text="ID of related object (submission, course, etc.)",
                        null=True,
                    ),
                ),
                (
                    "reference_type",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Type of related object",
                        max_length=50,
                    ),
                ),
                (
                    "skill_code",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Optional skill/competency identifier for future "
                            "per-skill mastery aggregation."
                        ),
                        max_length=100,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mastery_point_transactions",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mastery_point_transactions",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "db_table": "mastery_point_transactions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="masterypointtransaction",
            index=models.Index(
                fields=["tenant", "teacher"],
                name="mp_txn_tenant_teacher_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="masterypointtransaction",
            index=models.Index(
                fields=["tenant", "teacher", "reason"],
                name="mp_txn_tenant_reason_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="masterypointtransaction",
            index=models.Index(
                fields=["tenant", "teacher", "skill_code"],
                name="mp_txn_tenant_skill_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="masterypointtransaction",
            index=models.Index(
                fields=["created_at"],
                name="mp_txn_created_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="masterypointtransaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(("reference_id__isnull", False)),
                fields=("teacher", "reason", "reference_type", "reference_id"),
                name="uniq_mp_txn_per_reference",
            ),
        ),
        # --- TeacherMasterySummary -------------------------------------------
        migrations.CreateModel(
            name="TeacherMasterySummary",
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
                    "total_mastery_points",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "mp_this_month",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "mp_this_week",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                ("last_mp_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teacher_mastery_summaries",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "teacher",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mastery_summary",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "db_table": "teacher_mastery_summaries",
            },
        ),
        migrations.AddIndex(
            model_name="teachermasterysummary",
            index=models.Index(
                fields=["tenant", "total_mastery_points"],
                name="mp_sum_tenant_total_idx",
            ),
        ),
    ]
