# Generated migration for adding xp_per_lesson_reflection to GamificationConfig

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0011_badgedefinition_gamificationconfig_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="gamificationconfig",
            name="xp_per_lesson_reflection",
            field=models.PositiveIntegerField(default=5),
        ),
    ]
