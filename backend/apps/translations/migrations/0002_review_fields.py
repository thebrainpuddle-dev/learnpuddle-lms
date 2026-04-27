"""Migration 0002 — TASK-064b per-field translation review state.

Adds to ``ContentTranslation``:
  * ``review_status``   CharField(max_length=20, default='pending')
  * ``edited_text``     TextField(null=True, blank=True)
  * ``reviewed_by``     FK(users.User, SET_NULL, null=True)
  * ``reviewed_at``     DateTimeField(null=True)
  * ``published_at``    DateTimeField(null=True)

Also adds a composite index on (tenant, source_id, target_language,
review_status) to accelerate the review-page query.

All existing rows default to ``review_status='pending'``
(Django field default applied at DB level via the DEFAULT clause).
"""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("translations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="contenttranslation",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="contenttranslation",
            name="edited_text",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contenttranslation",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="translation_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="contenttranslation",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contenttranslation",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="contenttranslation",
            index=models.Index(
                fields=["tenant", "source_id", "target_language", "review_status"],
                name="trn_review_query_idx",
            ),
        ),
    ]
