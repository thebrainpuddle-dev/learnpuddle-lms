from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0029_knowledge_auto_ingest_fields"),
        ("academics", "0001_initial_academic_structure"),
    ]

    operations = [
        migrations.AddField(
            model_name="maicclassroom",
            name="assigned_sections",
            field=models.ManyToManyField(
                blank=True,
                help_text="Sections that can access this classroom. If empty + is_public, all students see it.",
                related_name="maic_classrooms",
                to="academics.section",
            ),
        ),
    ]
