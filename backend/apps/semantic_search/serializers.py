"""
Serializers for the semantic_search API (TASK-057).

We use DRF serializers only for inbound validation; outbound responses
are dict-payloads assembled in views so the retrieval shape matches
exactly what TASK-059 / TASK-061 will consume.
"""

from __future__ import annotations

from rest_framework import serializers

from .retrieval import ALLOWED_KINDS, MAX_TOP_K, MAX_QUERY_CHARS


class SemanticSearchRequestSerializer(serializers.Serializer):
    query = serializers.CharField(required=True, allow_blank=False, max_length=MAX_QUERY_CHARS + 1)
    top_k = serializers.IntegerField(required=False, default=10, min_value=1)
    kinds = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    course_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_query(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("query must be non-empty")
        if len(v) > MAX_QUERY_CHARS:
            raise serializers.ValidationError("QUERY_TOO_LONG")
        return v

    def validate_top_k(self, value: int) -> int:
        if value > MAX_TOP_K:
            raise serializers.ValidationError("TOP_K_TOO_LARGE")
        return value

    def validate_kinds(self, value):
        if not value:
            return value
        bad = [k for k in value if k not in ALLOWED_KINDS]
        if bad:
            raise serializers.ValidationError(f"Unknown kinds: {bad}")
        return value
