# apps/courses/chatbot_serializers.py
from rest_framework import serializers
from apps.courses.chatbot_models import (
    AIChatbot, AIChatbotKnowledge, AIChatbotConversation,
)


class SectionBriefSerializer(serializers.Serializer):
    """Lightweight read-only serializer for section info on chatbot cards."""
    id = serializers.UUIDField()
    name = serializers.CharField()
    grade_name = serializers.CharField(source='grade.name')
    grade_short_code = serializers.CharField(source='grade.short_code')


class AIChatbotSerializer(serializers.ModelSerializer):
    knowledge_count = serializers.SerializerMethodField()
    conversation_count = serializers.SerializerMethodField()
    sections = SectionBriefSerializer(many=True, read_only=True)

    class Meta:
        model = AIChatbot
        fields = [
            'id', 'name', 'avatar_url', 'persona_preset',
            'persona_description', 'custom_rules', 'block_off_topic',
            'welcome_message', 'is_active',
            'knowledge_count', 'conversation_count',
            'sections',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_knowledge_count(self, obj):
        if hasattr(obj, '_knowledge_count'):
            return obj._knowledge_count
        return obj.knowledge_sources.count()

    def get_conversation_count(self, obj):
        if hasattr(obj, '_conversation_count'):
            return obj._conversation_count
        return obj.conversations.count()


class AIChatbotStudentSerializer(serializers.ModelSerializer):
    """Read-only serializer for student-facing chatbot views (hides internal config)."""
    knowledge_count = serializers.SerializerMethodField()
    sections = SectionBriefSerializer(many=True, read_only=True)

    class Meta:
        model = AIChatbot
        fields = [
            'id', 'name', 'avatar_url', 'persona_preset',
            'welcome_message', 'is_active', 'knowledge_count',
            'sections',
            'created_at',
        ]
        read_only_fields = fields

    def get_knowledge_count(self, obj):
        return getattr(obj, '_knowledge_count', obj.knowledge_sources.count())


class AIChatbotCreateSerializer(serializers.ModelSerializer):
    persona_description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    custom_rules = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    section_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True,
    )

    class Meta:
        model = AIChatbot
        fields = [
            'name', 'avatar_url', 'persona_preset',
            'persona_description', 'custom_rules', 'block_off_topic',
            'welcome_message', 'section_ids',
        ]


class AIChatbotKnowledgeSerializer(serializers.ModelSerializer):
    content_source_title = serializers.SerializerMethodField()

    class Meta:
        model = AIChatbotKnowledge
        fields = [
            'id', 'source_type', 'title', 'filename',
            'chunk_count', 'total_token_count',
            'embedding_status', 'error_message',
            'is_auto', 'content_source_title',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'chunk_count', 'total_token_count',
            'embedding_status', 'error_message',
            'is_auto', 'content_source_title',
            'created_at', 'updated_at',
        ]

    def get_content_source_title(self, obj):
        if obj.content_source:
            return obj.content_source.title
        return None


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
