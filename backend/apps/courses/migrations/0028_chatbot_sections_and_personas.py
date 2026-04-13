# Add sections M2M to AIChatbot and update persona_preset choices.

from django.db import migrations, models


def migrate_old_personas(apps, schema_editor):
    """Map old persona presets to new ones."""
    AIChatbot = apps.get_model('courses', 'AIChatbot')
    mapping = {
        'tutor': 'study_buddy',
        'reference': 'concept_explainer',
        'open': 'study_buddy',
    }
    for old_key, new_key in mapping.items():
        AIChatbot.objects.filter(persona_preset=old_key).update(persona_preset=new_key)


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0027_knowledge_tenant_and_embedding_notnull"),
        ("academics", "0001_initial_academic_structure"),
    ]

    operations = [
        # Add sections M2M
        migrations.AddField(
            model_name="aichatbot",
            name="sections",
            field=models.ManyToManyField(
                blank=True,
                help_text="Sections that can see this chatbot",
                related_name="ai_chatbots",
                to="academics.section",
            ),
        ),

        # Update persona_preset choices and default
        migrations.AlterField(
            model_name="aichatbot",
            name="persona_preset",
            field=models.CharField(
                choices=[
                    ("study_buddy", "Study Buddy"),
                    ("quiz_master", "Quiz Master"),
                    ("concept_explainer", "Concept Explainer"),
                    ("homework_helper", "Homework Helper"),
                    ("revision_coach", "Revision Coach"),
                    ("custom", "Custom"),
                ],
                default="study_buddy",
                max_length=20,
            ),
        ),

        # Migrate existing data
        migrations.RunPython(
            migrate_old_personas,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
