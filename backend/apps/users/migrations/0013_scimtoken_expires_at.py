# Migration for AUDIT-2026-04-26-PHASE3-13: add `expires_at` to SCIMToken.
#
# NULL = never expires (back-compat default).  When set, ``SCIMToken.verify``
# rejects the token once ``timezone.now() > expires_at``.
#
# Authored by hand (rather than via ``manage.py makemigrations``) to keep this
# migration scoped strictly to the SCIMToken security fix and to avoid
# bundling unrelated index-rename drift accumulated in other apps.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_scim_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="scimtoken",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="Optional expiry; NULL = never expires",
                null=True,
            ),
        ),
    ]
