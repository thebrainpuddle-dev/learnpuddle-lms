from rest_framework import serializers

from apps.courses.models import Course, Content
from .models import TeacherProgress, Assignment, AssignmentSubmission


class TeacherProgressSerializer(serializers.ModelSerializer):
    content_id = serializers.UUIDField(source="content.id", read_only=True)
    course_id = serializers.UUIDField(source="course.id", read_only=True)

    class Meta:
        model = TeacherProgress
        fields = [
            "id",
            "course_id",
            "content_id",
            "status",
            "progress_percentage",
            "video_progress_seconds",
            "started_at",
            "completed_at",
            "last_accessed",
            "created_at",
            "updated_at",
        ]


class TeacherAssignmentListSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(source="course.id", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    submission_status = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    feedback = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            "id",
            "course_id",
            "course_title",
            "title",
            "description",
            "instructions",
            "due_date",
            "max_score",
            "passing_score",
            "is_mandatory",
            "is_active",
            "submission_status",
            "score",
            "feedback",
        ]

    def _submission(self, obj) -> AssignmentSubmission | None:
        teacher = self.context["request"].user
        return getattr(obj, "_submission_for_teacher", None) or AssignmentSubmission.objects.filter(
            assignment=obj, teacher=teacher
        ).first()

    def get_submission_status(self, obj):
        s = self._submission(obj)
        return s.status if s else "PENDING"

    def get_score(self, obj):
        s = self._submission(obj)
        return float(s.score) if (s and s.score is not None) else None

    def get_feedback(self, obj):
        s = self._submission(obj)
        return s.feedback if s else ""


class TeacherAssignmentSubmissionSerializer(serializers.ModelSerializer):
    assignment_id = serializers.UUIDField(source="assignment.id", read_only=True)

    class Meta:
        model = AssignmentSubmission
        fields = [
            "id",
            "assignment_id",
            "submission_text",
            "file_url",
            "status",
            "score",
            "feedback",
            "submitted_at",
            "updated_at",
        ]

