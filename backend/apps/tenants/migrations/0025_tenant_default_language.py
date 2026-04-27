"""Migration 0025 — TASK-058 Tenant.default_language.

Adds a per-tenant source-language pin (``default_language``) used by the
auto-translation service (apps.translations) as the ``from`` language
when calling the translation provider.

Default ``"en"``. Never null, never blank — existing rows are back-filled
with ``"en"`` which matches historic behaviour (platform copy is English
unless a tenant explicitly overrides).

NB: The task spec filed this as migration 0024. 0024 was already taken by
TASK-020 (``0024_tenant_mode``) so this ships as 0025.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0024_tenant_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="default_language",
            field=models.CharField(
                default="en",
                max_length=20,
                help_text=(
                    "BCP-47 language code for this tenant's source "
                    "content. Used by the auto-translation service "
                    "(TASK-058) as the 'from' language when translating "
                    "Course / Module / Content."
                ),
            ),
        ),
    ]
