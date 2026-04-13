# Improve HNSW index parameters — gracefully skips if pgvector is not installed.

import logging
from django.db import connection, migrations

logger = logging.getLogger(__name__)


def upgrade_hnsw(apps, schema_editor):
    cursor = connection.cursor()
    try:
        cursor.execute("SAVEPOINT hnsw_upgrade;")
        cursor.execute("DROP INDEX IF EXISTS chunk_embedding_hnsw_idx;")
        cursor.execute(
            "CREATE INDEX chunk_embedding_hnsw_idx "
            "ON ai_chatbot_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 128);"
        )
        cursor.execute("RELEASE SAVEPOINT hnsw_upgrade;")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT hnsw_upgrade;")
        logger.warning("Could not upgrade HNSW index — pgvector not installed.")


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0025_add_max_chatbots_per_teacher"),
    ]

    operations = [
        migrations.RunPython(upgrade_hnsw, migrations.RunPython.noop),
    ]
