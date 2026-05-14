from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0022_alter_quizsubmission_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gamificationconfig",
            name="freeze_token_max_inventory",
            field=models.PositiveIntegerField(
                default=3,
                help_text="Cap on unspent freeze tokens per teacher.",
            ),
        ),
        migrations.AlterField(
            model_name="gamificationconfig",
            name="weekend_mode_available",
            field=models.BooleanField(
                default=False,
                help_text="Allow teachers to opt into weekend mode (Sat/Sun don't count).",
            ),
        ),
    ]
