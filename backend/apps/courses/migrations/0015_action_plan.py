# Generated migration for ActionPlan model

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0014_teaching_strategy"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ActionPlan",
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
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("ACTIVE", "Active"),
                            ("COMPLETED", "Completed"),
                        ],
                        default="ACTIVE",
                        max_length=20,
                    ),
                ),
                ("goals", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="action_plans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="action_plans",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "action_plans",
                "ordering": ["-updated_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "teacher", "-updated_at"],
                        name="action_plan_tenant__d1e2f3_idx",
                    ),
                    models.Index(
                        fields=["tenant", "teacher", "status"],
                        name="action_plan_tenant__g4h5i6_idx",
                    ),
                ],
            },
        ),
    ]
