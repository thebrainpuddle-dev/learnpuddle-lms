# Generated for LearnPuddle chatbot feature
# Drops deprecated AI Studio models and updates Content.content_type choices.

from django.db import migrations, models


def convert_deprecated_content_types(apps, schema_editor):
    """Convert INTERACTIVE_LESSON and SCENARIO content rows to TEXT."""
    Content = apps.get_model('courses', 'Content')
    count = Content.objects.filter(
        content_type__in=['INTERACTIVE_LESSON', 'SCENARIO']
    ).update(content_type='TEXT')
    if count:
        print(f"  Converted {count} deprecated content items to TEXT")


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0022_remove_old_ai_models"),
    ]

    operations = [
        # Step 1: Convert deprecated content types
        migrations.RunPython(
            convert_deprecated_content_types,
            migrations.RunPython.noop,
        ),

        # Step 2: Drop deprecated AI Studio tables
        migrations.DeleteModel(name="ScenarioAttempt"),
        migrations.DeleteModel(name="ScenarioTemplate"),
        migrations.DeleteModel(name="TeachingStrategy"),
        migrations.DeleteModel(name="ActionPlan"),
        migrations.DeleteModel(name="StudyNotes"),

        # Step 3: Update Content.content_type choices
        migrations.AlterField(
            model_name="content",
            name="content_type",
            field=models.CharField(
                choices=[
                    ("VIDEO", "Video"),
                    ("DOCUMENT", "Document"),
                    ("LINK", "External Link"),
                    ("TEXT", "Text Content"),
                    ("AI_CLASSROOM", "AI Classroom"),
                    ("CHATBOT", "AI Chatbot"),
                ],
                max_length=20,
            ),
        ),
    ]
