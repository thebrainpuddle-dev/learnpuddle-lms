"""
Serializers for the chatbot app (TASK-059).
"""

from __future__ import annotations

from rest_framework import serializers

from .models import ChatQuery


class CitationSerializer(serializers.Serializer):
    block = serializers.IntegerField()
    source_type = serializers.CharField()
    source_id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    score = serializers.FloatField()


class AskRequestSerializer(serializers.Serializer):
    question = serializers.CharField(
        max_length=2000,
        help_text="The question to ask (max 2000 characters).",
    )
    course_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optional Course UUID to scope retrieval.",
    )
    top_k = serializers.IntegerField(
        required=False,
        default=5,
        min_value=1,
        max_value=10,
        help_text="Max chunks to retrieve (1-10, default 5).",
    )


class AskResponseSerializer(serializers.Serializer):
    query_id = serializers.UUIDField()
    answer = serializers.CharField()
    citations = CitationSerializer(many=True)
    grounded = serializers.BooleanField()


class ChatQueryHistorySerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = ChatQuery
        fields = [
            "id",
            "course_id",
            "answer",
            "citations",
            "grounded",
            "provider",
            "model",
            "tokens_prompt",
            "tokens_completion",
            "latency_ms",
            "created_at",
        ]
        # NOTE: `question` is intentionally excluded from list/detail serializers
        # to avoid accidentally exposing PII in logs or API responses.
        # Teachers retrieve their own questions by querying the row directly.
