"""
Initial migration for apps.semantic_search (TASK-057).

Creates:
  * semantic_search_embeddingchunk  — tenant-scoped vector(1024) chunks.
  * semantic_search_jobrun          — reindex job audit trail.

The pgvector extension, ``embedding`` vector column, and IVFFLAT cosine
index are installed via a :class:`migrations.RunPython` step that
degrades gracefully on DB images where the extension is unavailable
(typical on the stock ``postgres:15`` image). When that happens the
migration still succeeds; vector search is simply unavailable until
devops swaps in ``ankane/pgvector`` and this migration's forward
function is re-run via ``manage.py migrate semantic_search zero`` then
``migrate semantic_search``.
"""

from __future__ import annotations

import logging
import uuid

import django.db.models.deletion
from django.db import connection, migrations, models


logger = logging.getLogger(__name__)


def _install_pgvector(apps, schema_editor):
    """
    Best-effort installation of:
      1. pgvector extension (CREATE EXTENSION IF NOT EXISTS vector)
      2. embedding vector(1024) column on semantic_search_embeddingchunk
      3. IVFFLAT cosine index on that column

    Each step is wrapped in a savepoint so a failure on any step does not
    abort the entire migration transaction. This mirrors the pattern used
    by the existing ai_chatbot_chunks migration (apps.courses.0024).
    """
    cursor = connection.cursor()

    # 1. Extension — may require superuser; fail gracefully.
    try:
        cursor.execute("SAVEPOINT sem_pgv_ext;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cursor.execute("RELEASE SAVEPOINT sem_pgv_ext;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT sem_pgv_ext;")
        logger.warning(
            "semantic_search: pgvector extension unavailable (%s). "
            "Vector column and index skipped. Reindex/search will no-op.",
            exc,
        )
        return

    # 2. Vector column.
    try:
        cursor.execute("SAVEPOINT sem_pgv_col;")
        cursor.execute(
            "ALTER TABLE semantic_search_embeddingchunk "
            "ADD COLUMN IF NOT EXISTS embedding vector(1024);"
        )
        cursor.execute("RELEASE SAVEPOINT sem_pgv_col;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT sem_pgv_col;")
        logger.warning("semantic_search: could not add vector column (%s).", exc)
        return

    # 3. IVFFLAT cosine index. Low lists value works for small / cold-start
    # indexes — a later ticket can ANALYZE + REINDEX with higher ``lists``.
    try:
        cursor.execute("SAVEPOINT sem_pgv_idx;")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS semsearch_embedding_ivfflat_idx "
            "ON semantic_search_embeddingchunk "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
        )
        cursor.execute("RELEASE SAVEPOINT sem_pgv_idx;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT sem_pgv_idx;")
        logger.warning("semantic_search: could not create IVFFLAT index (%s).", exc)


def _noop_reverse(apps, schema_editor):
    # Reverse migration does not drop the vector extension (may be shared).
    # Drop only our objects.
    cursor = connection.cursor()
    for stmt in (
        "DROP INDEX IF EXISTS semsearch_embedding_ivfflat_idx;",
        "ALTER TABLE IF EXISTS semantic_search_embeddingchunk "
        "DROP COLUMN IF EXISTS embedding;",
    ):
        try:
            cursor.execute(f"SAVEPOINT sem_rev;")
            cursor.execute(stmt)
            cursor.execute("RELEASE SAVEPOINT sem_rev;")
        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT sem_rev;")


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0024_tenant_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmbeddingChunk",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("course", "Course"),
                            ("module", "Module"),
                            ("content", "Content"),
                            ("transcript", "Transcript"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("source_id", models.UUIDField(db_index=True)),
                ("chunk_index", models.PositiveIntegerField(default=0)),
                ("text", models.TextField()),
                ("text_hash", models.CharField(db_index=True, max_length=64)),
                ("model", models.CharField(blank=True, default="", max_length=100)),
                ("provider", models.CharField(blank=True, default="", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="semantic_embedding_chunks",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "semantic_search_embeddingchunk",
                "ordering": ["tenant", "source_type", "source_id", "chunk_index"],
                "unique_together": {("tenant", "source_type", "source_id", "chunk_index")},
            },
        ),
        migrations.AddIndex(
            model_name="embeddingchunk",
            index=models.Index(
                fields=["tenant", "source_type", "source_id"],
                name="semsearch_tenant_src_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="embeddingchunk",
            index=models.Index(
                fields=["tenant", "source_type"],
                name="semsearch_tenant_type_idx",
            ),
        ),
        migrations.CreateModel(
            name="EmbeddingJobRun",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("content", "Content"),
                            ("course", "Course"),
                            ("tenant", "Tenant"),
                        ],
                        db_index=True,
                        max_length=10,
                    ),
                ),
                ("target_id", models.CharField(blank=True, default="", max_length=64)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="running",
                        max_length=20,
                    ),
                ),
                ("chunks_indexed", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True, default="")),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="semantic_job_runs",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "semantic_search_jobrun",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="embeddingjobrun",
            index=models.Index(
                fields=["tenant", "-started_at"], name="semjob_tenant_started_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="embeddingjobrun",
            index=models.Index(
                fields=["kind", "status"], name="semjob_kind_status_idx"
            ),
        ),
        # pgvector extension + vector column + IVFFLAT index (all best-effort).
        migrations.RunPython(_install_pgvector, _noop_reverse),
    ]
