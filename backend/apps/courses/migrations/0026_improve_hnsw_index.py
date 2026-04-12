# Improve HNSW index parameters for better recall with 1536-dim embeddings.
# Increases ef_construction from 64 to 128 for higher recall at index time.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0025_add_max_chatbots_per_teacher"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS chunk_embedding_hnsw_idx;",
            reverse_sql=(
                "CREATE INDEX chunk_embedding_hnsw_idx "
                "ON ai_chatbot_chunks USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 64);"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX chunk_embedding_hnsw_idx "
                "ON ai_chatbot_chunks USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 128);"
            ),
            reverse_sql="DROP INDEX IF EXISTS chunk_embedding_hnsw_idx;",
        ),
    ]
