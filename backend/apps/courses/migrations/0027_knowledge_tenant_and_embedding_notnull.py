# Add tenant FK to AIChatbotKnowledge for proper tenant isolation,
# add NOT NULL constraint to embedding column, and add tenant+chatbot index.

from django.db import migrations, models
import django.db.models.deletion


def backfill_knowledge_tenant(apps, schema_editor):
    """Populate tenant FK from chatbot.tenant for existing knowledge rows."""
    AIChatbotKnowledge = apps.get_model('courses', 'AIChatbotKnowledge')
    for knowledge in AIChatbotKnowledge.objects.select_related('chatbot').all():
        if not knowledge.tenant_id:
            knowledge.tenant_id = knowledge.chatbot.tenant_id
            knowledge.save(update_fields=['tenant_id'])


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0026_improve_hnsw_index"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        # Step 1: Add tenant FK as nullable
        migrations.AddField(
            model_name="aichatbotknowledge",
            name="tenant",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ai_chatbot_knowledge",
                to="tenants.tenant",
                help_text="Direct tenant FK for proper isolation (avoids join through chatbot)",
            ),
        ),

        # Step 2: Backfill tenant from chatbot.tenant
        migrations.RunPython(
            backfill_knowledge_tenant,
            reverse_code=migrations.RunPython.noop,
        ),

        # Step 3: Make tenant NOT NULL
        migrations.AlterField(
            model_name="aichatbotknowledge",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ai_chatbot_knowledge",
                to="tenants.tenant",
                help_text="Direct tenant FK for proper isolation (avoids join through chatbot)",
            ),
        ),

        # Step 4: Add tenant+chatbot index on knowledge
        migrations.AddIndex(
            model_name="aichatbotknowledge",
            index=models.Index(
                fields=["tenant", "chatbot"],
                name="ai_knowledge_tenant_chatbot_idx",
            ),
        ),

        # Step 5: Make embedding column NOT NULL
        # (It was added via raw SQL without NOT NULL constraint)
        migrations.RunSQL(
            sql=(
                "UPDATE ai_chatbot_chunks SET embedding = array_fill(0, ARRAY[1536])::vector "
                "WHERE embedding IS NULL;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="ALTER TABLE ai_chatbot_chunks ALTER COLUMN embedding SET NOT NULL;",
            reverse_sql="ALTER TABLE ai_chatbot_chunks ALTER COLUMN embedding DROP NOT NULL;",
        ),
    ]
