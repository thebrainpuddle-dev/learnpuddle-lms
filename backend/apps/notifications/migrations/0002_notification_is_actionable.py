from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="is_actionable",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["teacher", "is_actionable", "is_read"],
                name="notificatio_teacher_action_idx",
            ),
        ),
    ]
