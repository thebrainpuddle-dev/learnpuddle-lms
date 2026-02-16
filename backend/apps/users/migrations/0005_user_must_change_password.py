# Generated migration for must_change_password field
# Used by bulk import to force password change on first login

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_add_user_soft_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="must_change_password",
            field=models.BooleanField(
                default=False,
                help_text="Force password change on next login (e.g., after bulk import)",
            ),
        ),
    ]
