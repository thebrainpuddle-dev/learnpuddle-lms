from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0033_parent_portal"),
    ]

    operations = [
        migrations.AddField(
            model_name="maicclassroom",
            name="content",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Full classroom content — slides, scenes, sceneSlideBounds",
            ),
        ),
    ]
