from django.db import migrations, models


class Migration(migrations.Migration):
    """CG-P0-3: add `images_pending` boolean to MAICClassroom.

    Default False — existing rows already have images filled (or are disabled)
    so no backfill is needed. The field flips to True when the per-scene
    content endpoint defers image resolution to the Celery task, and back to
    False when `fill_classroom_images` completes.
    """

    dependencies = [
        ("courses", "0041_strip_legacy_scene_data_urls"),
    ]

    operations = [
        migrations.AddField(
            model_name="maicclassroom",
            name="images_pending",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True while the fill_classroom_images Celery task is in-flight. "
                    "Frontend polls this field to know whether slide images are still loading."
                ),
            ),
        ),
    ]
