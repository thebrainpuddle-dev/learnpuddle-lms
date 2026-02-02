from rest_framework import serializers

from .models import ReminderCampaign, ReminderDelivery


class ReminderPreviewRequestSerializer(serializers.Serializer):
    reminder_type = serializers.ChoiceField(choices=["COURSE_DEADLINE", "ASSIGNMENT_DUE", "CUSTOM"])
    course_id = serializers.UUIDField(required=False)
    assignment_id = serializers.UUIDField(required=False)
    teacher_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    deadline_override = serializers.DateTimeField(required=False)
    subject = serializers.CharField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)


class ReminderSendRequestSerializer(ReminderPreviewRequestSerializer):
    pass


class ReminderCampaignSerializer(serializers.ModelSerializer):
    sent_count = serializers.SerializerMethodField()
    failed_count = serializers.SerializerMethodField()

    class Meta:
        model = ReminderCampaign
        fields = [
            "id",
            "reminder_type",
            "course",
            "assignment",
            "subject",
            "message",
            "deadline_override",
            "created_at",
            "sent_count",
            "failed_count",
        ]

    def get_sent_count(self, obj: ReminderCampaign):
        return obj.deliveries.filter(status="SENT").count()

    def get_failed_count(self, obj: ReminderCampaign):
        return obj.deliveries.filter(status="FAILED").count()


class ReminderDeliverySerializer(serializers.ModelSerializer):
    teacher_email = serializers.EmailField(source="teacher.email", read_only=True)
    teacher_name = serializers.CharField(source="teacher.get_full_name", read_only=True)

    class Meta:
        model = ReminderDelivery
        fields = ["id", "teacher", "teacher_email", "teacher_name", "status", "error", "sent_at", "created_at"]

