"""DRF serializers for ContentRevision list / detail (TASK-048)."""

from rest_framework import serializers

from .versioning_models import ContentRevision


class ContentRevisionListSerializer(serializers.ModelSerializer):
    """Compact row for the history panel — no snapshot body."""

    target_type = serializers.SerializerMethodField()
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ContentRevision
        fields = [
            "id",
            "revision_number",
            "target_type",
            "object_id",
            "change_summary",
            "changed_by",
            "changed_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_target_type(self, obj):
        return obj.content_type.model if obj.content_type_id else None

    def get_changed_by_name(self, obj):
        u = obj.changed_by
        if u is None:
            return None
        full = (getattr(u, "first_name", "") or "") + " " + (
            getattr(u, "last_name", "") or ""
        )
        full = full.strip()
        return full or getattr(u, "email", None)


class ContentRevisionDetailSerializer(ContentRevisionListSerializer):
    """Full record including the snapshot body."""

    class Meta(ContentRevisionListSerializer.Meta):
        fields = ContentRevisionListSerializer.Meta.fields + ["snapshot_json"]
        read_only_fields = fields
