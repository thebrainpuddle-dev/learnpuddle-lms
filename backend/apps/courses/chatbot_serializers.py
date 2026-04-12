# apps/courses/chatbot_serializers.py
from rest_framework import serializers
from apps.courses.chatbot_models import (
    AIChatbot, AIChatbotKnowledge, AIChatbotConversation,
)


class AIChatbotSerializer(serializers.ModelSerializer):
    knowledge_count = serializers.SerializerMethodField()
    conversation_count = serializers.SerializerMethodField()

    class Meta:
        model = AIChatbot
        fields = [
            'id', 'name', 'avatar_url', 'persona_preset',
            'persona_description', 'custom_rules', 'block_off_topic',
            'welcome_message', 'is_active',
            'knowledge_count', 'conversation_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_knowledge_count(self, obj):
        # Use annotation if available (avoids N+1), fall back to .count()
        if hasattr(obj, '_knowledge_count'):
            return obj._knowledge_count
        return obj.knowledge_sources.count()

    def get_conversation_count(self, obj):
        # Use annotation if available (avoids N+1), fall back to .count()
        if hasattr(obj, '_conversation_count'):
            return obj._conversation_count
        return obj.conversations.count()


class AIChatbotCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIChatbot
        fields = [
            'name', 'avatar_url', 'persona_preset',
            'persona_description', 'custom_rules', 'block_off_topic',
            'welcome_message',
        ]


class AIChatbotKnowledgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIChatbotKnowledge
        fields = [
            'id', 'source_type', 'title', 'filename',
            'chunk_count', 'total_token_count',
            'embedding_status', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'chunk_count', 'total_token_count',
            'embedding_status', 'error_message',
            'created_at', 'updated_at',
        ]


class AIChatbotConversationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for conversation lists (no messages)."""
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)

    class Meta:
        model = AIChatbotConversation
        fields = [
            'id', 'title', 'student_name', 'message_count',
            'is_flagged', 'started_at', 'last_message_at',
        ]


class AIChatbotConversationDetailSerializer(serializers.ModelSerializer):
    """Full serializer with messages."""
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)

    class Meta:
        model = AIChatbotConversation
        fields = [
            'id', 'chatbot', 'title', 'student_name',
            'messages', 'message_count',
            'is_flagged', 'flag_reason',
            'started_at', 'last_message_at',
        ]
