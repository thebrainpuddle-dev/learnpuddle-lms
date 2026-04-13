# apps/courses/chatbot_models.py
"""
AI Chatbot models: teacher-created RAG chatbots with persona presets,
knowledge bases, and configurable guardrails.
"""
import uuid

from django.db import models
from pgvector.django import VectorField, HnswIndex

from utils.tenant_manager import TenantManager

# Shared embedding model constant — imported by chatbot_tasks.py and chatbot_rag_service.py
EMBEDDING_MODEL = "text-embedding-3-small"


class AIChatbot(models.Model):
    """Teacher-created AI chatbot with persona and guardrails."""

    PERSONA_CHOICES = [
        ('tutor', 'Socratic Tutor'),
        ('reference', 'Reference Assistant'),
        ('open', 'Open Discussion'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='ai_chatbots',
    )
    creator = models.ForeignKey(
        'users.User', on_delete=models.CASCADE,
        related_name='ai_chatbots',
    )

    name = models.CharField(max_length=200)
    avatar_url = models.CharField(max_length=500, blank=True, default='')
    persona_preset = models.CharField(
        max_length=20, choices=PERSONA_CHOICES, default='tutor',
    )
    persona_description = models.TextField(
        blank=True, default='',
        help_text='Personality description for the LLM system prompt',
    )
    custom_rules = models.TextField(
        blank=True, default='',
        help_text='Additional guardrail instructions appended to system prompt',
    )
    block_off_topic = models.BooleanField(default=True)
    welcome_message = models.TextField(
        blank=True, default='',
        help_text='First message shown to students when starting a conversation',
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'ai_chatbots'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['tenant', 'creator', '-updated_at']),
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.persona_preset})"


class AIChatbotKnowledge(models.Model):
    """Knowledge source uploaded to a chatbot (PDF, text, URL)."""

    SOURCE_TYPE_CHOICES = [
        ('pdf', 'PDF Document'),
        ('text', 'Raw Text'),
        ('url', 'Web URL'),
        ('document', 'Uploaded Document'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chatbot = models.ForeignKey(
        AIChatbot, on_delete=models.CASCADE,
        related_name='knowledge_sources',
    )

    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    title = models.CharField(max_length=300)
    filename = models.CharField(max_length=500, blank=True, default='')
    file_url = models.CharField(max_length=500, blank=True, default='')
    raw_text = models.TextField(blank=True, default='')
    content_hash = models.CharField(max_length=64, blank=True, default='')
    chunk_count = models.PositiveIntegerField(default=0)
    total_token_count = models.PositiveIntegerField(default=0)
    embedding_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending',
    )
    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    all_objects = models.Manager()

    class Meta:
        db_table = 'ai_chatbot_knowledge'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['chatbot', 'embedding_status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.source_type}, {self.embedding_status})"


class AIChatbotChunk(models.Model):
    """Individual text chunk with pgvector embedding for RAG retrieval."""

    knowledge = models.ForeignKey(
        AIChatbotKnowledge, on_delete=models.CASCADE,
        related_name='chunks',
    )
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='ai_chatbot_chunks',
        help_text='Denormalized for fast filtered vector search',
    )
    chatbot = models.ForeignKey(
        AIChatbot, on_delete=models.CASCADE,
        related_name='chunks',
        help_text='Denormalized for fast filtered vector search',
    )

    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    heading = models.CharField(max_length=512, blank=True, default='')
    page_number = models.PositiveIntegerField(null=True, blank=True)
    embedding = VectorField(dimensions=1536)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'ai_chatbot_chunks'
        ordering = ['knowledge', 'chunk_index']
        unique_together = [('knowledge', 'chunk_index')]
        indexes = [
            HnswIndex(
                name='chunk_embedding_hnsw_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
            models.Index(fields=['tenant', 'chatbot']),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.knowledge.title}"


class AIChatbotConversation(models.Model):
    """Student conversation session with a chatbot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='ai_chatbot_conversations',
    )
    chatbot = models.ForeignKey(
        AIChatbot, on_delete=models.CASCADE,
        related_name='conversations',
    )
    student = models.ForeignKey(
        'users.User', on_delete=models.CASCADE,
        related_name='chatbot_conversations',
    )

    title = models.CharField(max_length=300, blank=True, default='')
    messages = models.JSONField(default=list)
    message_count = models.PositiveIntegerField(default=0)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True, default='')

    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'ai_chatbot_conversations'
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['tenant', 'student', '-last_message_at']),
            models.Index(fields=['chatbot', 'student']),
            models.Index(fields=['tenant', 'is_flagged']),
        ]

    def __str__(self):
        return f"Conversation: {self.title or 'Untitled'}"
