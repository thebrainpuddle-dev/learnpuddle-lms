"""Content versioning (TASK-048) — ContentRevision model."""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0036_scorm_xapi"),
        ("tenants", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContentRevision",
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
                ("object_id", models.UUIDField()),
                ("revision_number", models.PositiveIntegerField()),
                ("snapshot_json", models.JSONField(default=dict)),
                (
                    "change_summary",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="content_revisions",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "content_revisions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "content_type", "object_id", "-created_at"],
                        name="content_rev_tenant_obj_idx",
                    ),
                    models.Index(
                        fields=["tenant", "created_at"],
                        name="content_rev_tenant_time_idx",
                    ),
                ],
                "unique_together": {("content_type", "object_id", "revision_number")},
            },
        ),
    ]
