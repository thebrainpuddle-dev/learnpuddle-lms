# apps/progress/assessment_serializers.py

from rest_framework import serializers

from .assessment_models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuizAttempt,
    QuizConfig,
)


# ---------------------------------------------------------------------------
# Question / QuestionBank
# ---------------------------------------------------------------------------

class QuestionChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionChoice
        fields = ["id", "text", "is_correct", "order"]
        read_only_fields = ["id"]

    def validate_text(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Choice text cannot be empty.")
        return value


class QuestionSerializer(serializers.ModelSerializer):
    choices = QuestionChoiceSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = [
            "id",
            "bank",
            "question_type",
            "prompt",
            "points",
            "difficulty",
            "explanation",
            "metadata",
            "order",
            "choices",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_bank(self, bank):
        # Enforce tenant isolation on write path (M4 / tenant safety).
        request = self.context.get("request")
        if request is not None and getattr(request, "tenant", None) is not None:
            if bank.tenant_id != request.tenant.id:
                raise serializers.ValidationError(
                    "Question bank does not belong to this tenant.",
                )
        return bank

    def validate_points(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError("Points must be non-negative.")
        return value

    def validate(self, data):
        """Per-question-type shape validation (M4).

        - MCQ / TRUE_FALSE: exactly 1 correct choice, >= 2 total choices.
        - MULTI: >= 2 correct choices, >= 2 total choices.
        - SHORT / ESSAY: no choices required.
        - Choices must have non-empty text.
        """
        # Determine effective question_type (falls back to instance on PATCH)
        qtype = data.get("question_type")
        if qtype is None and self.instance is not None:
            qtype = self.instance.question_type

        # Choices: only validate shape when caller supplied a choices list.
        choices = data.get("choices")
        if choices is None:
            return data

        # Empty-text guard (also covered in QuestionChoiceSerializer but cheap here).
        for c in choices:
            text = (c.get("text") or "").strip()
            if not text:
                raise serializers.ValidationError(
                    {"choices": "All choices must have non-empty text."},
                )

        correct_count = sum(1 for c in choices if c.get("is_correct"))

        if qtype in ("MCQ", "TRUE_FALSE"):
            if len(choices) < 2:
                raise serializers.ValidationError(
                    {"choices": f"{qtype} requires at least 2 choices."},
                )
            if correct_count != 1:
                raise serializers.ValidationError(
                    {"choices": f"{qtype} requires exactly 1 correct choice."},
                )
        elif qtype == "MULTI":
            if len(choices) < 2:
                raise serializers.ValidationError(
                    {"choices": "MULTI requires at least 2 choices."},
                )
            if correct_count < 2:
                raise serializers.ValidationError(
                    {"choices": "MULTI requires at least 2 correct choices."},
                )
        elif qtype in ("SHORT", "ESSAY"):
            # Free-text types may optionally carry reference choices; no structural rule.
            pass

        return data

    def create(self, validated_data):
        choices = validated_data.pop("choices", [])
        tenant = self.context["request"].tenant
        question = Question.objects.create(tenant=tenant, **validated_data)
        for choice in choices:
            QuestionChoice.objects.create(question=question, **choice)
        return question

    def update(self, instance, validated_data):
        choices_data = validated_data.pop("choices", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if choices_data is not None:
            # Replace-style update: delete existing, recreate
            instance.choices.all().delete()
            for choice in choices_data:
                QuestionChoice.objects.create(question=instance, **choice)
        return instance


class QuestionBankSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = QuestionBank
        fields = [
            "id",
            "title",
            "description",
            "tags",
            "is_active",
            "question_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "question_count", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# QuizConfig
# ---------------------------------------------------------------------------

class QuizConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizConfig
        fields = [
            "id",
            "content",
            "time_limit_seconds",
            "max_attempts",
            "pass_threshold_percent",
            "shuffle_questions",
            "shuffle_choices",
            "show_correct_answers_after",
            "multi_partial_credit",
            "random_selection_count",
            "source_question_banks",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "content", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# QuizAttempt
# ---------------------------------------------------------------------------

class QuizAttemptStartSerializer(serializers.ModelSerializer):
    """What the teacher sees when starting an attempt: questions, no answers."""

    class Meta:
        model = QuizAttempt
        fields = [
            "id",
            "attempt_number",
            "status",
            "started_at",
            "questions_snapshot",
            "max_score",
        ]
        read_only_fields = fields


class QuizAttemptSubmitSerializer(serializers.Serializer):
    """Payload for submitting an attempt."""

    answers = serializers.DictField(
        child=serializers.JSONField(),
        help_text="Keyed by question id → answer payload.",
    )
    time_spent_seconds = serializers.IntegerField(required=False, min_value=0)


def _strip_answer_key(snapshot):
    """Return a copy of `questions_snapshot` with `is_correct` and
    `explanation` removed from each question/choice. Safe to hand to a
    teacher during IN_PROGRESS or when the config forbids revealing answers.
    """
    sanitized = []
    for q in snapshot or []:
        s = dict(q)
        s.pop("explanation", None)
        s["choices"] = [
            {"id": c.get("id"), "text": c.get("text"), "order": c.get("order")}
            for c in (q.get("choices") or [])
        ]
        sanitized.append(s)
    return sanitized


class QuizAttemptSerializer(serializers.ModelSerializer):
    """Sanitized view of an attempt for list/retrieve endpoints.

    H1 — never exposes the answer key unless BOTH:
      * the attempt has been SUBMITTED, AND
      * the related `QuizConfig.show_correct_answers_after` is True.
    Otherwise, `questions_snapshot` is stripped of `is_correct` /
    `explanation` and `answers` is only returned after submission.
    """

    score_percent = serializers.FloatField(read_only=True)
    questions_snapshot = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()

    class Meta:
        model = QuizAttempt
        fields = [
            "id",
            "content",
            "attempt_number",
            "status",
            "started_at",
            "submitted_at",
            "time_spent_seconds",
            "score",
            "max_score",
            "score_percent",
            "passed",
            "answers",
            "questions_snapshot",
        ]
        read_only_fields = fields

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _can_show_answers(self, obj):
        """Answer key is only visible when the attempt is fully submitted
        AND the QuizConfig explicitly allows it. Defaults to False when no
        config is found (most restrictive, safest).
        """
        if obj.status != "SUBMITTED":
            return False
        # Prefer cached config off the context to avoid N+1 when many
        # attempts share the same content.
        configs = (self.context or {}).get("_quiz_configs_by_content") or {}
        cfg = configs.get(obj.content_id)
        if cfg is None:
            try:
                cfg = QuizConfig.objects.get(content_id=obj.content_id)
            except QuizConfig.DoesNotExist:
                return False
        return bool(cfg.show_correct_answers_after)

    def get_questions_snapshot(self, obj):
        if self._can_show_answers(obj):
            return obj.questions_snapshot
        return _strip_answer_key(obj.questions_snapshot)

    def get_answers(self, obj):
        # Never return the teacher's submitted answers back while the attempt
        # is in progress. (Prevents a teacher from "checking" before submit.)
        if obj.status == "IN_PROGRESS":
            return {}
        return obj.answers or {}


# ---------------------------------------------------------------------------
# Gradebook
# ---------------------------------------------------------------------------

class GradebookRowSerializer(serializers.Serializer):
    """
    Centralized gradebook row – one row per teacher × course.

    Structured output only (not a model serializer) so the view can assemble
    data from QuizAttempt, AssignmentSubmission, and TeacherProgress without
    forcing a new denormalized table.
    """

    teacher_id = serializers.UUIDField()
    teacher_name = serializers.CharField()
    teacher_email = serializers.EmailField()
    course_id = serializers.UUIDField()
    course_title = serializers.CharField()
    quiz_attempts = serializers.IntegerField()
    quiz_best_score_percent = serializers.FloatField()
    quiz_passed = serializers.IntegerField()
    assignments_submitted = serializers.IntegerField()
    assignments_graded = serializers.IntegerField()
    assignments_avg_score = serializers.FloatField()
    progress_percent = serializers.FloatField()
