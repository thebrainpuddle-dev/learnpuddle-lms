# Add content_source FK and is_auto flag to AIChatbotKnowledge for auto-ingestion.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0028_chatbot_sections_and_personas"),
    ]

    operations = [
        migrations.AddField(
            model_name="aichatbotknowledge",
            name="content_source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="chatbot_knowledge",
                to="courses.content",
                help_text="Auto-ingested from this Content item (null for manual uploads)",
            ),
        ),
        migrations.AddField(
            model_name="aichatbotknowledge",
            name="is_auto",
            field=models.BooleanField(
                default=False,
                help_text="True = auto-ingested from course content, False = manual upload",
            ),
        ),
        migrations.AddIndex(
            model_name="aichatbotknowledge",
            index=models.Index(
                fields=["chatbot", "is_auto"],
                name="ai_knowledge_chatbot_auto_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="aichatbotknowledge",
            index=models.Index(
                fields=["chatbot", "content_source"],
                name="ai_knowledge_content_src_idx",
            ),
        ),
    ]
