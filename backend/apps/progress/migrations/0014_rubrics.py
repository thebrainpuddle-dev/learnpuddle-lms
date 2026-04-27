# Migration: Rubric-based grading (TASK-044)
#
# New tables:
#   - rubrics
#   - rubric_criteria
#   - rubric_levels
#   - rubric_evaluations
#
# Schema change:
#   - assignments.rubric_id  (FK, nullable, SET_NULL)

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Merge point after the parallel 0013 migrations (TASK-043 variants).
        ("progress", "0013_assessment"),
        ("progress", "0013_quiz_attempts_and_time_limit"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Rubric ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Rubric",
            fields=[
                ("id", models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("total_points", models.DecimalField(
                    decimal_places=2, default=0, max_digits=8,
                    validators=[django.core.validators.MinValueValidator(0)],
                    help_text="Sum of the max_points of every RubricCriterion.",
                )),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="rubrics_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="rubrics",
                    to="tenants.tenant",
                )),
            ],
            options={
                "db_table": "rubrics",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="rubric",
            index=models.Index(fields=["tenant", "is_active"], name="rubrics_tenant_active_idx"),
        ),
        migrations.AddIndex(
            model_name="rubric",
            index=models.Index(fields=["tenant", "title"], name="rubrics_tenant_title_idx"),
        ),

        # ── RubricCriterion ───────────────────────────────────────────
        migrations.CreateModel(
            name="RubricCriterion",
            fields=[
                ("id", models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("max_points", models.DecimalField(
                    decimal_places=2, default=0, max_digits=6,
                    validators=[django.core.validators.MinValueValidator(0)],
                )),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rubric", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="criteria",
                    to="progress.rubric",
                )),
            ],
            options={
                "db_table": "rubric_criteria",
                "ordering": ["rubric", "order", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="rubriccriterion",
            index=models.Index(fields=["rubric", "order"], name="rubric_crit_rubric_order_idx"),
        ),

        # ── RubricLevel ───────────────────────────────────────────────
        migrations.CreateModel(
            name="RubricLevel",
            fields=[
                ("id", models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("points", models.DecimalField(
                    decimal_places=2, default=0, max_digits=6,
                    validators=[django.core.validators.MinValueValidator(0)],
                )),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("criterion", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="levels",
                    to="progress.rubriccriterion",
                )),
            ],
            options={
                "db_table": "rubric_levels",
                "ordering": ["criterion", "order", "-points"],
            },
        ),
        migrations.AddIndex(
            model_name="rubriclevel",
            index=models.Index(fields=["criterion", "order"], name="rubric_lvl_crit_order_idx"),
        ),

        # ── Assignment.rubric FK ──────────────────────────────────────
        migrations.AddField(
            model_name="assignment",
            name="rubric",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assignments",
                to="progress.rubric",
            ),
        ),

        # ── RubricEvaluation ──────────────────────────────────────────
        migrations.CreateModel(
            name="RubricEvaluation",
            fields=[
                ("id", models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ("scores", models.JSONField(blank=True, default=dict)),
                ("total_score", models.DecimalField(
                    decimal_places=2, default=0, max_digits=8,
                    help_text="Server-computed: sum of per-criterion points in `scores`.",
                    validators=[django.core.validators.MinValueValidator(0)],
                )),
                ("feedback", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("evaluator", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="rubric_evaluations",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("rubric", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="evaluations",
                    help_text="Snapshot: the rubric used at grading time.",
                    to="progress.rubric",
                )),
                ("submission", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="rubric_evaluations",
                    to="progress.assignmentsubmission",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="rubric_evaluations",
                    to="tenants.tenant",
                )),
            ],
            options={
                "db_table": "rubric_evaluations",
                "ordering": ["-created_at"],
                "unique_together": {("submission", "evaluator")},
            },
        ),
        migrations.AddIndex(
            model_name="rubricevaluation",
            index=models.Index(fields=["tenant", "submission"], name="rubric_eval_tenant_sub_idx"),
        ),
        migrations.AddIndex(
            model_name="rubricevaluation",
            index=models.Index(fields=["tenant", "rubric"], name="rubric_eval_tenant_rub_idx"),
        ),
        migrations.AddIndex(
            model_name="rubricevaluation",
            index=models.Index(fields=["tenant", "evaluator"], name="rubric_eval_tenant_eval_idx"),
        ),
    ]
