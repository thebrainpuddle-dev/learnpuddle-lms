"""
Migration 0002 — Rename ChatQuery (tenant, user, created_at) index.

The original index name ``chatquery_tenant_user_created_idx`` is 33 chars
which exceeds Django's 30-char `Meta.indexes` name limit, raising the
system-check error E034 and blocking every ``manage.py`` subcommand. The
index already exists in Postgres (which has a 63-char identifier limit),
so we simply rename it to a 27-char alias.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="chatquery",
            new_name="chq_tenant_user_created_idx",
            old_name="chatquery_tenant_user_created_idx",
        ),
    ]
