# Generated migration for Course, Module, Content soft-delete fields
# and Course.search_vector for full-text search

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0005_content_media_asset"),
    ]

    operations = [
        # ── Course: add soft-delete fields ──────────────────────────────
        migrations.AddField(
            model_name="course",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="course",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── Course: add full-text search vector ─────────────────────────
        migrations.AddField(
            model_name="course",
            name="search_vector",
            field=SearchVectorField(blank=True, null=True),
        ),

        # ── Module: add soft-delete fields ──────────────────────────────
        migrations.AddField(
            model_name="module",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="module",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── Content: add soft-delete fields ─────────────────────────────
        migrations.AddField(
            model_name="content",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="content",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── Update Course indexes ───────────────────────────────────────
        # Add new composite indexes
        migrations.AddIndex(
            model_name="course",
            index=models.Index(
                fields=["tenant", "is_published", "is_active"],
                name="courses_tenant_pub_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="course",
            index=models.Index(
                fields=["tenant", "is_mandatory", "is_active"],
                name="courses_tenant_mand_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="course",
            index=models.Index(
                fields=["tenant", "created_at"],
                name="courses_tenant_created_idx",
            ),
        ),

        # GIN index for full-text search
        migrations.AddIndex(
            model_name="course",
            index=GinIndex(
                fields=["search_vector"],
                name="course_search_vector_idx",
            ),
        ),
    ]
