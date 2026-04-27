# Migration: Question Banks + Advanced Quizzing (TASK-043)
#
# New tables:
#   - question_banks
#   - bank_questions
#   - bank_question_choices
#   - quiz_configs
#   - quiz_attempts

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0012_gamificationconfig_xp_per_lesson_reflection"),
        # L2 — depend on the latest tenant migration so this migration
        # stacks on top of every prior tenant schema change.
        ("tenants", "0019_saml_and_password_policy"),
        ("courses", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── QuestionBank ──────────────────────────────────────────────
        migrations.CreateModel(
            name="QuestionBank",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("tags", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="question_banks",
                    to="tenants.tenant",
                )),
                ("created_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name="authored_question_banks",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "question_banks",
                "ordering": ["title"],
                "unique_together": {("tenant", "title")},
            },
        ),
        migrations.AddIndex(
            model_name="questionbank",
            index=models.Index(fields=["tenant", "title"], name="qbank_tenant_title_idx"),
        ),
        migrations.AddIndex(
            model_name="questionbank",
            index=models.Index(fields=["tenant", "is_active"], name="qbank_tenant_active_idx"),
        ),

        # ── Question ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="Question",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("question_type", models.CharField(max_length=20, choices=[
                    ("MCQ", "Multiple Choice (single)"),
                    ("MULTI", "Multiple Choice (multiple)"),
                    ("SHORT", "Short Answer"),
                    ("TRUE_FALSE", "True / False"),
                    ("ESSAY", "Essay"),
                ])),
                ("prompt", models.TextField()),
                ("points", models.PositiveIntegerField(default=1)),
                ("difficulty", models.CharField(
                    max_length=10, default="MEDIUM",
                    choices=[("EASY", "Easy"), ("MEDIUM", "Medium"), ("HARD", "Hard")],
                )),
                ("explanation", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="bank_questions",
                    to="tenants.tenant",
                )),
                ("bank", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="questions",
                    to="progress.questionbank",
                )),
            ],
            options={
                "db_table": "bank_questions",
                "ordering": ["bank", "order", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="question",
            index=models.Index(fields=["tenant", "bank"], name="bankq_tenant_bank_idx"),
        ),
        migrations.AddIndex(
            model_name="question",
            index=models.Index(fields=["tenant", "question_type"], name="bankq_tenant_type_idx"),
        ),
        migrations.AddIndex(
            model_name="question",
            index=models.Index(fields=["bank", "order"], name="bankq_bank_order_idx"),
        ),

        # ── QuestionChoice ────────────────────────────────────────────
        migrations.CreateModel(
            name="QuestionChoice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("text", models.CharField(max_length=500)),
                ("is_correct", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(default=0)),
                ("question", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="choices",
                    to="progress.question",
                )),
            ],
            options={
                "db_table": "bank_question_choices",
                "ordering": ["question", "order"],
            },
        ),
        migrations.AddIndex(
            model_name="questionchoice",
            index=models.Index(fields=["question", "order"], name="bankqc_q_order_idx"),
        ),

        # ── QuizConfig ────────────────────────────────────────────────
        migrations.CreateModel(
            name="QuizConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("time_limit_seconds", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveIntegerField(default=1)),
                ("pass_threshold_percent", models.DecimalField(
                    max_digits=5, decimal_places=2, default=70,
                    validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(100),
                    ],
                )),
                ("shuffle_questions", models.BooleanField(default=False)),
                ("shuffle_choices", models.BooleanField(default=False)),
                ("show_correct_answers_after", models.BooleanField(default=True)),
                ("multi_partial_credit", models.BooleanField(default=False)),
                ("random_selection_count", models.PositiveIntegerField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quiz_configs",
                    to="tenants.tenant",
                )),
                ("content", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quiz_config",
                    to="courses.content",
                )),
                ("source_question_banks", models.ManyToManyField(
                    blank=True,
                    related_name="used_by_quiz_configs",
                    to="progress.questionbank",
                )),
            ],
            options={
                "db_table": "quiz_configs",
            },
        ),
        migrations.AddIndex(
            model_name="quizconfig",
            index=models.Index(fields=["tenant", "content"], name="qcfg_tenant_content_idx"),
        ),

        # ── QuizAttempt ──────────────────────────────────────────────
        migrations.CreateModel(
            name="QuizAttempt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("attempt_number", models.PositiveIntegerField(default=1)),
                ("status", models.CharField(max_length=20, default="IN_PROGRESS", choices=[
                    ("IN_PROGRESS", "In Progress"),
                    ("SUBMITTED", "Submitted"),
                    ("EXPIRED", "Expired (auto-submit on time-limit)"),
                ])),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("submitted_at", models.DateTimeField(null=True, blank=True)),
                ("time_spent_seconds", models.PositiveIntegerField(default=0)),
                ("questions_snapshot", models.JSONField(blank=True, default=list)),
                ("answers", models.JSONField(blank=True, default=dict)),
                ("score", models.DecimalField(max_digits=7, decimal_places=2, default=0)),
                ("max_score", models.DecimalField(max_digits=7, decimal_places=2, default=0)),
                ("passed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quiz_attempts",
                    to="tenants.tenant",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="bank_quiz_attempts",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("content", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quiz_attempts",
                    to="courses.content",
                )),
            ],
            options={
                "db_table": "quiz_attempts",
                "ordering": ["-started_at"],
                "unique_together": {("teacher", "content", "attempt_number")},
            },
        ),
        migrations.AddIndex(
            model_name="quizattempt",
            index=models.Index(fields=["tenant", "teacher", "content"], name="qatt_tenant_t_c_idx"),
        ),
        migrations.AddIndex(
            model_name="quizattempt",
            index=models.Index(fields=["tenant", "content", "status"], name="qatt_tenant_c_status_idx"),
        ),
        migrations.AddIndex(
            model_name="quizattempt",
            index=models.Index(fields=["tenant", "teacher", "status"], name="qatt_tenant_t_status_idx"),
        ),
        migrations.AddIndex(
            model_name="quizattempt",
            index=models.Index(fields=["started_at"], name="qatt_started_idx"),
        ),
    ]
