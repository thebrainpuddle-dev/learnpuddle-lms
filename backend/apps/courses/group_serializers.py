from rest_framework import serializers

from .models import TeacherGroup


class TeacherGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherGroup
        fields = ["id", "name", "description", "group_type", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

