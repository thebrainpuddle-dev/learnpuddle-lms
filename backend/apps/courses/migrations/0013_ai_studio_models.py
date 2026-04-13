# Generated migration for AI Studio models

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0012_rename_chat_messa_session_m3n4o5_idx_chat_messag_session_597c4e_idx_and_more"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add new content types to Content model
        migrations.AlterField(
            model_name="content",
            name="content_type",
            field=models.CharField(
                choices=[
                    ("VIDEO", "Video"),
                    ("DOCUMENT", "Document"),
                    ("LINK", "External Link"),
                    ("TEXT", "Text Content"),
                    ("INTERACTIVE_LESSON", "Interactive Lesson"),
                    ("SCENARIO", "Scenario Simulation"),
                ],
                max_length=20,
            ),
        ),
        # InteractiveLesson
        migrations.CreateModel(
            name="InteractiveLesson",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True)),
                ("topic", models.CharField(blank=True, help_text="Original generation topic", max_length=500)),
                ("target_audience", models.CharField(blank=True, max_length=300)),
                ("scenes", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(
                    choices=[("DRAFT", "Draft"), ("GENERATING", "Generating"), ("READY", "Ready"), ("FAILED", "Failed")],
                    default="DRAFT", max_length=20,
                )),
                ("generation_model", models.CharField(blank=True, default="", max_length=100)),
                ("generation_metadata", models.JSONField(blank=True, default=dict)),
                ("estimated_minutes", models.PositiveIntegerField(default=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content", models.OneToOneField(
                    blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="interactive_lesson", to="courses.content",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_interactive_lessons", to=settings.AUTH_USER_MODEL,
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="interactive_lessons", to="tenants.tenant",
                )),
            ],
            options={
                "db_table": "interactive_lessons",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["tenant", "status"], name="interactiv_tenant__e1a2b3_idx"),
                    models.Index(fields=["tenant", "created_at"], name="interactiv_tenant__f4g5h6_idx"),
                ],
            },
        ),
        # ScenarioTemplate
        migrations.CreateModel(
            name="ScenarioTemplate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True)),
                ("teaching_context", models.CharField(
                    blank=True, help_text="e.g., 'Classroom management', 'Parent-teacher conference'",
                    max_length=500,
                )),
                ("difficulty", models.CharField(
                    choices=[("BEGINNER", "Beginner"), ("INTERMEDIATE", "Intermediate"), ("ADVANCED", "Advanced")],
                    default="INTERMEDIATE", max_length=20,
                )),
                ("decision_tree", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(
                    choices=[("DRAFT", "Draft"), ("GENERATING", "Generating"), ("READY", "Ready"), ("FAILED", "Failed")],
                    default="DRAFT", max_length=20,
                )),
                ("generation_model", models.CharField(blank=True, default="", max_length=100)),
                ("generation_metadata", models.JSONField(blank=True, default=dict)),
                ("max_score", models.PositiveIntegerField(default=10)),
                ("estimated_minutes", models.PositiveIntegerField(default=8)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content", models.OneToOneField(
                    blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="scenario_template", to="courses.content",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_scenarios", to=settings.AUTH_USER_MODEL,
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="scenario_templates", to="tenants.tenant",
                )),
            ],
            options={
                "db_table": "scenario_templates",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["tenant", "status"], name="scenario_t_tenant__j7k8l9_idx"),
                    models.Index(fields=["tenant", "difficulty"], name="scenario_t_tenant__m0n1o2_idx"),
                    models.Index(fields=["tenant", "created_at"], name="scenario_t_tenant__p3q4r5_idx"),
                ],
            },
        ),
        # ScenarioAttempt
        migrations.CreateModel(
            name="ScenarioAttempt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("path", models.JSONField(blank=True, default=list)),
                ("total_score", models.PositiveIntegerField(default=0)),
                ("max_possible_score", models.PositiveIntegerField(default=0)),
                ("is_completed", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scenario", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="attempts", to="courses.scenariotemplate",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="scenario_attempts", to=settings.AUTH_USER_MODEL,
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="scenario_attempts", to="tenants.tenant",
                )),
            ],
            options={
                "db_table": "scenario_attempts",
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["tenant", "teacher", "scenario"], name="scenario_a_tenant__s6t7u8_idx"),
                    models.Index(fields=["tenant", "scenario", "is_completed"], name="scenario_a_tenant__v9w0x1_idx"),
                ],
            },
        ),
        # LessonReflectionResponse
        migrations.CreateModel(
            name="LessonReflectionResponse",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("scene_index", models.PositiveIntegerField(help_text="0-based index of the scene")),
                ("response_text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lesson", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="reflection_responses", to="courses.interactivelesson",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lesson_reflections", to=settings.AUTH_USER_MODEL,
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lesson_reflection_responses", to="tenants.tenant",
                )),
            ],
            options={
                "db_table": "lesson_reflection_responses",
                "ordering": ["scene_index"],
                "unique_together": {("lesson", "teacher", "scene_index")},
                "indexes": [
                    models.Index(fields=["tenant", "teacher", "lesson"], name="lesson_ref_tenant__y2z3a4_idx"),
                ],
            },
        ),
    ]
