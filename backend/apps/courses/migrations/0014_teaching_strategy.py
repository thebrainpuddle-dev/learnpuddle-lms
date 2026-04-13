# Generated migration for TeachingStrategy model

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0013_ai_studio_models"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TeachingStrategy",
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
                ("topic", models.CharField(max_length=500)),
                ("subject", models.CharField(blank=True, max_length=200)),
                ("grade_level", models.CharField(blank=True, max_length=100)),
                ("challenge", models.TextField(blank=True)),
                ("strategies", models.JSONField(blank=True, default=list)),
                ("is_bookmarked", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teaching_strategies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teaching_strategies",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "teaching_strategies",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "teacher", "-created_at"],
                        name="teaching_st_tenant__a1b2c3_idx",
                    ),
                ],
            },
        ),
    ]
