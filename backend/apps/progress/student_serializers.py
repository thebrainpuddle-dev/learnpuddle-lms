from rest_framework import serializers

from apps.progress.models import TeacherProgress, Assignment, AssignmentSubmission, QuizSubmission


class StudentProgressSerializer(serializers.ModelSerializer):
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


class StudentAssignmentListSerializer(serializers.ModelSerializer):
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
        user = self.context["request"].user
        return getattr(obj, "_submission_for_student", None) or AssignmentSubmission.objects.filter(
            assignment=obj, teacher=user
        ).first()

    def _quiz_submission(self, obj) -> QuizSubmission | None:
        user = self.context["request"].user
        quiz = getattr(obj, "quiz", None)
        if not quiz:
            return None
        return QuizSubmission.objects.filter(quiz=quiz, teacher=user).first()

    def get_submission_status(self, obj):
        if getattr(obj, "quiz", None):
            qs = self._quiz_submission(obj)
            if not qs:
                return "PENDING"
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
            return ""
        s = self._submission(obj)
        return s.feedback if s else ""

    def get_is_quiz(self, obj):
        return bool(getattr(obj, "quiz", None))


class StudentAssignmentSubmissionSerializer(serializers.ModelSerializer):
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
