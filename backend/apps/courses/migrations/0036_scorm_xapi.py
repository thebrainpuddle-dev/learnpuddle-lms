"""SCORM 1.2 + xAPI minimal LRS schema (TASK-047)."""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0035_maic_audio_manifest"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1) Extend Content.content_type choices with SCORM
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
                ],
                max_length=20,
            ),
        ),

        # 2) SCORMPackage
        migrations.CreateModel(
            name="SCORMPackage",
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
                ("manifest_path", models.CharField(max_length=500)),
                ("launch_url", models.CharField(max_length=500)),
                (
                    "version",
                    models.CharField(
                        choices=[("1.2", "SCORM 1.2"), ("2004", "SCORM 2004")],
                        default="1.2",
                        max_length=8,
                    ),
                ),
                ("package_path", models.CharField(max_length=500)),
                ("package_size", models.BigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scorm_package",
                        to="courses.content",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scorm_packages",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_scorm_packages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "scorm_packages",
                "indexes": [
                    models.Index(
                        fields=["tenant", "created_at"],
                        name="scorm_pkg_tenant_created_idx",
                    ),
                ],
            },
        ),

        # 3) SCORMTrackingData
        migrations.CreateModel(
            name="SCORMTrackingData",
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
                ("lesson_status", models.CharField(blank=True, default="", max_length=32)),
                ("score_raw", models.FloatField(blank=True, null=True)),
                ("session_time", models.CharField(blank=True, default="", max_length=32)),
                ("total_time", models.CharField(blank=True, default="", max_length=32)),
                ("cmi", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "package",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tracking_rows",
                        to="courses.scormpackage",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scorm_tracking_rows",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scorm_tracking_rows",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "scorm_tracking_data",
                "unique_together": {("package", "user")},
                "indexes": [
                    models.Index(
                        fields=["tenant", "user"],
                        name="scorm_track_tenant_user_idx",
                    ),
                    models.Index(
                        fields=["package", "user"],
                        name="scorm_track_pkg_user_idx",
                    ),
                ],
            },
        ),

        # 4) XAPIStatement
        migrations.CreateModel(
            name="XAPIStatement",
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
                ("statement_id", models.UUIDField(default=uuid.uuid4)),
                ("actor_mbox", models.CharField(blank=True, default="", max_length=320)),
                ("actor_name", models.CharField(blank=True, default="", max_length=255)),
                ("verb_id", models.CharField(max_length=500)),
                ("verb_display", models.CharField(blank=True, default="", max_length=255)),
                ("object_id", models.CharField(max_length=500)),
                ("object_name", models.CharField(blank=True, default="", max_length=500)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("context", models.JSONField(blank=True, default=dict)),
                ("stored", models.DateTimeField(auto_now_add=True)),
                ("raw", models.JSONField(blank=True, default=dict)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="xapi_statements",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "xapi_statements",
                "indexes": [
                    models.Index(
                        fields=["tenant", "stored"],
                        name="xapi_stmt_tenant_stored_idx",
                    ),
                    models.Index(
                        fields=["tenant", "actor_mbox"],
                        name="xapi_stmt_tenant_actor_idx",
                    ),
                    models.Index(
                        fields=["tenant", "verb_id"],
                        name="xapi_stmt_tenant_verb_idx",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="xapistatement",
            constraint=models.UniqueConstraint(
                fields=("tenant", "statement_id"),
                name="xapi_statement_unique_per_tenant",
            ),
        ),
    ]
