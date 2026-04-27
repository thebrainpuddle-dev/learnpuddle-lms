from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0038_course_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="maicclassroom",
            name="generation_phase",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "None"),
                    ("queued", "Queued"),
                    ("outline", "Generating outline"),
                    ("content", "Generating scene content"),
                    ("actions", "Generating scene actions"),
                    ("saving", "Saving"),
                    ("complete", "Complete"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="maicclassroom",
            name="phase_scene_index",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="maicclassroom",
            name="scenes_ready",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="maicclassroom",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="maicclassroom",
            name="last_progress_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
