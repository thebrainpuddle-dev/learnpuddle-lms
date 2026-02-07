from rest_framework import serializers

from apps.courses.models import Course, Content
from .models import TeacherProgress, Assignment, AssignmentSubmission, QuizSubmission


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
    is_quiz = serializers.SerializerMethodField()

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
            "is_quiz",
        ]

    def _submission(self, obj) -> AssignmentSubmission | None:
        teacher = self.context["request"].user
        return getattr(obj, "_submission_for_teacher", None) or AssignmentSubmission.objects.filter(
            assignment=obj, teacher=teacher
        ).first()

    def _quiz_submission(self, obj) -> QuizSubmission | None:
        teacher = self.context["request"].user
        quiz = getattr(obj, "quiz", None)
        if not quiz:
            return None
        return QuizSubmission.objects.filter(quiz=quiz, teacher=teacher).first()

    def get_submission_status(self, obj):
        # Quiz assignments derive status from QuizSubmission; reflection uses AssignmentSubmission.
        if getattr(obj, "quiz", None):
            qs = self._quiz_submission(obj)
            if not qs:
                return "PENDING"
            # Only "GRADED" when graded_at is set (fully auto-graded or manually reviewed).
            # Quizzes with short-answer questions stay "SUBMITTED" until admin reviews.
            return "GRADED" if qs.graded_at is not None else "SUBMITTED"
        s = self._submission(obj)
        return s.status if s else "PENDING"

    def get_score(self, obj):
        if getattr(obj, "quiz", None):
            qs = self._quiz_submission(obj)
            return float(qs.score) if (qs and qs.score is not None) else None
        s = self._submission(obj)
        return float(s.score) if (s and s.score is not None) else None

    def get_feedback(self, obj):
        if getattr(obj, "quiz", None):
            # Quiz feedback (if any) can be added later; keep empty for now.
            return ""
        s = self._submission(obj)
        return s.feedback if s else ""

    def get_is_quiz(self, obj):
        return bool(getattr(obj, "quiz", None))


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

