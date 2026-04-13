from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0021_maic_models"),
    ]

    operations = [
        migrations.DeleteModel(name="ClassroomParticipant"),
        migrations.DeleteModel(name="ClassroomSession"),
        migrations.DeleteModel(name="AIPersonaMessage"),
        migrations.DeleteModel(name="AIPersonaSession"),
        migrations.DeleteModel(name="CoursePodcast"),
        migrations.DeleteModel(name="LessonQuizResponse"),
        migrations.DeleteModel(name="LessonReflectionResponse"),
        migrations.DeleteModel(name="InteractiveLesson"),
    ]
