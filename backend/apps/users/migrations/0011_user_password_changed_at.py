# Generated for TASK-045 revision 2 — password_changed_at for refresh-token
# invalidation when a tenant policy change (or user password change) happens.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0010_password_history_and_saml_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="password_changed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "When the user last changed their password; used to "
                    "invalidate stale refresh tokens."
                ),
            ),
        ),
    ]
