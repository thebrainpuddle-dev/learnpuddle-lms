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

    def validate(self, attrs):
        reminder_type = attrs.get("reminder_type")
        course_id = attrs.get("course_id")
        assignment_id = attrs.get("assignment_id")

        if reminder_type == "COURSE_DEADLINE":
            if not course_id:
                raise serializers.ValidationError(
                    {"course_id": "course_id is required when reminder_type=COURSE_DEADLINE"}
                )
            if assignment_id:
                raise serializers.ValidationError(
                    {"assignment_id": "Do not provide assignment_id when reminder_type=COURSE_DEADLINE"}
                )

        elif reminder_type == "ASSIGNMENT_DUE":
            if not assignment_id:
                raise serializers.ValidationError(
                    {"assignment_id": "assignment_id is required when reminder_type=ASSIGNMENT_DUE"}
                )
            if course_id:
                raise serializers.ValidationError(
                    {"course_id": "Do not provide course_id when reminder_type=ASSIGNMENT_DUE"}
                )

        elif reminder_type == "CUSTOM":
            # Explicitly reject unused fields to avoid silent confusion.
            if course_id:
                raise serializers.ValidationError(
                    {"course_id": "Do not provide course_id when reminder_type=CUSTOM"}
                )
            if assignment_id:
                raise serializers.ValidationError(
                    {"assignment_id": "Do not provide assignment_id when reminder_type=CUSTOM"}
                )

        teacher_ids = attrs.get("teacher_ids")
        if teacher_ids is not None:
            if len(teacher_ids) == 0:
                raise serializers.ValidationError(
                    {"teacher_ids": "teacher_ids must be a non-empty list when provided"}
                )
            max_ids = 1000
            if len(teacher_ids) > max_ids:
                raise serializers.ValidationError(
                    {"teacher_ids": f"Too many teacher_ids (max {max_ids})"}
                )

        return attrs


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

