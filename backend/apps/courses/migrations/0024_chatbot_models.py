# Generated for LearnPuddle AI Chatbot Builder feature.
# Creates chatbot models with pgvector support and adds Content FKs.

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0023_drop_deprecated_and_update_content"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Enable pgvector extension
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;",
        ),

        # AIChatbot
        migrations.CreateModel(
            name="AIChatbot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("avatar_url", models.CharField(blank=True, default="", max_length=500)),
                ("persona_preset", models.CharField(choices=[("tutor", "Socratic Tutor"), ("reference", "Reference Assistant"), ("open", "Open Discussion")], default="tutor", max_length=20)),
                ("persona_description", models.TextField(blank=True, default="", help_text="Personality description for the LLM system prompt")),
                ("custom_rules", models.TextField(blank=True, default="", help_text="Additional guardrail instructions appended to system prompt")),
                ("block_off_topic", models.BooleanField(default=True)),
                ("welcome_message", models.TextField(blank=True, default="", help_text="First message shown to students when starting a conversation")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_chatbots", to="tenants.tenant")),
                ("creator", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_chatbots", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "ai_chatbots",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="aichatbot",
            index=models.Index(fields=["tenant", "creator", "-updated_at"], name="ai_chatbots_tenant__idx1"),
        ),
        migrations.AddIndex(
            model_name="aichatbot",
            index=models.Index(fields=["tenant", "is_active"], name="ai_chatbots_tenant__idx2"),
        ),

        # AIChatbotKnowledge
        migrations.CreateModel(
            name="AIChatbotKnowledge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_type", models.CharField(choices=[("pdf", "PDF Document"), ("text", "Raw Text"), ("url", "Web URL"), ("document", "Uploaded Document")], max_length=20)),
                ("title", models.CharField(max_length=300)),
                ("filename", models.CharField(blank=True, default="", max_length=500)),
                ("file_url", models.CharField(blank=True, default="", max_length=500)),
                ("raw_text", models.TextField(blank=True, default="")),
                ("content_hash", models.CharField(blank=True, default="", max_length=64)),
                ("chunk_count", models.PositiveIntegerField(default=0)),
                ("total_token_count", models.PositiveIntegerField(default=0)),
                ("embedding_status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("ready", "Ready"), ("failed", "Failed")], default="pending", max_length=20)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("chatbot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="knowledge_sources", to="courses.aichatbot")),
            ],
            options={
                "db_table": "ai_chatbot_knowledge",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="aichatbotknowledge",
            index=models.Index(fields=["chatbot", "embedding_status"], name="ai_chatbot__chatbot_idx"),
        ),

        # AIChatbotChunk (with pgvector)
        migrations.CreateModel(
            name="AIChatbotChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("heading", models.CharField(blank=True, default="", max_length=512)),
                ("page_number", models.PositiveIntegerField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("knowledge", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="courses.aichatbotknowledge")),
                ("tenant", models.ForeignKey(help_text="Denormalized for fast filtered vector search", on_delete=django.db.models.deletion.CASCADE, related_name="ai_chatbot_chunks", to="tenants.tenant")),
                ("chatbot", models.ForeignKey(help_text="Denormalized for fast filtered vector search", on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="courses.aichatbot")),
            ],
            options={
                "db_table": "ai_chatbot_chunks",
                "ordering": ["knowledge", "chunk_index"],
                "unique_together": {("knowledge", "chunk_index")},
            },
        ),
        # Add vector column via raw SQL (pgvector VectorField)
        migrations.RunSQL(
            "ALTER TABLE ai_chatbot_chunks ADD COLUMN embedding vector(1536);",
            reverse_sql="ALTER TABLE ai_chatbot_chunks DROP COLUMN IF EXISTS embedding;",
        ),
        # HNSW index for vector similarity search
        migrations.RunSQL(
            "CREATE INDEX chunk_embedding_hnsw_idx ON ai_chatbot_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
            reverse_sql="DROP INDEX IF EXISTS chunk_embedding_hnsw_idx;",
        ),
        migrations.AddIndex(
            model_name="aichatbotchunk",
            index=models.Index(fields=["tenant", "chatbot"], name="ai_chatbot__tenant_chatbot_idx"),
        ),

        # AIChatbotConversation
        migrations.CreateModel(
            name="AIChatbotConversation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(blank=True, default="", max_length=300)),
                ("messages", models.JSONField(default=list)),
                ("message_count", models.PositiveIntegerField(default=0)),
                ("is_flagged", models.BooleanField(default=False)),
                ("flag_reason", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("last_message_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_chatbot_conversations", to="tenants.tenant")),
                ("chatbot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversations", to="courses.aichatbot")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chatbot_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "ai_chatbot_conversations",
                "ordering": ["-last_message_at"],
            },
        ),
        migrations.AddIndex(
            model_name="aichatbotconversation",
            index=models.Index(fields=["tenant", "student", "-last_message_at"], name="ai_chatbot__conv_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="aichatbotconversation",
            index=models.Index(fields=["chatbot", "student"], name="ai_chatbot__conv_chatbot_idx"),
        ),
        migrations.AddIndex(
            model_name="aichatbotconversation",
            index=models.Index(fields=["tenant", "is_flagged"], name="ai_chatbot__conv_flagged_idx"),
        ),

        # Add FK fields to Content
        migrations.AddField(
            model_name="content",
            name="maic_classroom",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="content_items",
                to="courses.maicclassroom",
            ),
        ),
        migrations.AddField(
            model_name="content",
            name="ai_chatbot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="content_items",
                to="courses.aichatbot",
            ),
        ),
    ]
