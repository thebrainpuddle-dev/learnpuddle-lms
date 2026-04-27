# apps/progress/rubric_serializers.py
#
# TASK-044 — Serializers for Rubric CRUD, cloning, assignment-attachment
# and submission evaluation.

from decimal import Decimal

from rest_framework import serializers

from .models import Assignment, AssignmentSubmission
from .rubric_models import (
    Rubric,
    RubricCriterion,
    RubricEvaluation,
    RubricLevel,
)


# ---------------------------------------------------------------------------
# Nested serializers (read + write)
# ---------------------------------------------------------------------------


class RubricLevelSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RubricLevel
        fields = ["id", "title", "description", "points", "order"]


class RubricCriterionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    levels = RubricLevelSerializer(many=True, required=False)

    class Meta:
        model = RubricCriterion
        fields = ["id", "title", "description", "max_points", "order", "levels"]


class RubricSerializer(serializers.ModelSerializer):
    criteria = RubricCriterionSerializer(many=True, required=False)

    class Meta:
        model = Rubric
        fields = [
            "id", "title", "description", "total_points",
            "is_active", "criteria",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "total_points", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# Write serializer — handles nested create/update of criteria + levels
# ---------------------------------------------------------------------------


class RubricWriteSerializer(serializers.ModelSerializer):
    """Accepts nested criteria (with optional levels) on create/update.

    On create / PATCH with `criteria` provided:
      - existing criteria/levels are replaced (simple, atomic)
      - levels nest under their parent criterion
    """

    criteria = RubricCriterionSerializer(many=True, required=False)

    class Meta:
        model = Rubric
        fields = ["title", "description", "is_active", "criteria"]

    def validate_title(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Title is required.")
        return value

    # -- helpers -----------------------------------------------------------
    def _write_criteria(self, rubric: Rubric, criteria_data: list) -> None:
        """Replace the rubric's criteria/levels with the supplied payload."""
        # Delete existing (cascade removes levels) and re-create.
        rubric.criteria.all().delete()
        for c_index, c_data in enumerate(criteria_data or []):
            levels_data = c_data.pop("levels", []) or []
            criterion = RubricCriterion.objects.create(
                rubric=rubric,
                title=c_data.get("title", ""),
                description=c_data.get("description", ""),
                max_points=c_data.get("max_points", 0),
                order=c_data.get("order", c_index),
            )
            for l_index, l_data in enumerate(levels_data):
                RubricLevel.objects.create(
                    criterion=criterion,
                    title=l_data.get("title", ""),
                    description=l_data.get("description", ""),
                    points=l_data.get("points", 0),
                    order=l_data.get("order", l_index),
                )
        rubric.recompute_total_points(save=True)

    # -- create / update ---------------------------------------------------
    def create(self, validated_data):
        criteria_data = validated_data.pop("criteria", [])
        request = self.context.get("request")
        rubric = Rubric.objects.create(
            tenant=request.tenant,
            created_by=request.user if request and request.user.is_authenticated else None,
            **validated_data,
        )
        self._write_criteria(rubric, criteria_data)
        return rubric

    def update(self, instance, validated_data):
        criteria_data = validated_data.pop("criteria", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if criteria_data is not None:
            self._write_criteria(instance, criteria_data)
        return instance


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class RubricEvaluationScoreEntrySerializer(serializers.Serializer):
    """One entry in the `scores` payload: {criterion_id, level_id?, points?, comment?}."""

    criterion_id = serializers.UUIDField()
    level_id = serializers.UUIDField(required=False, allow_null=True)
    points = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class RubricEvaluationReadSerializer(serializers.ModelSerializer):
    evaluator_email = serializers.EmailField(source="evaluator.email", read_only=True)
    rubric_title = serializers.CharField(source="rubric.title", read_only=True)

    class Meta:
        model = RubricEvaluation
        fields = [
            "id", "submission", "rubric", "rubric_title",
            "evaluator", "evaluator_email",
            "scores", "total_score", "feedback",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class RubricEvaluateSerializer(serializers.Serializer):
    """Input for POST /admin/submissions/{id}/evaluate/.

    The rubric is resolved from the submission's assignment — the client
    only supplies scores and (optionally) overall feedback. We validate
    every score entry against the rubric's criteria/levels and compute the
    `total_score` server-side.
    """

    scores = RubricEvaluationScoreEntrySerializer(many=True)
    feedback = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        submission: AssignmentSubmission = self.context["submission"]
        tenant = self.context["request"].tenant

        assignment: Assignment = submission.assignment
        rubric: Rubric | None = assignment.rubric
        if rubric is None:
            raise serializers.ValidationError(
                "This assignment does not have a rubric attached."
            )
        # Tenant isolation — rubric & submission must share the request tenant.
        if rubric.tenant_id != tenant.id or submission.tenant_id not in (None, tenant.id):
            raise serializers.ValidationError("Cross-tenant evaluation is not allowed.")

        # Pre-fetch the rubric's criteria/levels into an index for validation.
        criteria_index = {}
        for criterion in rubric.criteria.prefetch_related("levels").all():
            criteria_index[str(criterion.id)] = {
                "criterion": criterion,
                "levels": {str(l.id): l for l in criterion.levels.all()},
            }

        seen_criteria = set()
        normalized_scores = {}
        total = Decimal("0")

        for entry in attrs["scores"]:
            cid = str(entry["criterion_id"])
            if cid not in criteria_index:
                raise serializers.ValidationError(
                    f"Criterion {cid} does not belong to the rubric."
                )
            if cid in seen_criteria:
                raise serializers.ValidationError(
                    f"Duplicate score for criterion {cid}."
                )
            seen_criteria.add(cid)

            criterion = criteria_index[cid]["criterion"]
            level_id = entry.get("level_id")
            points = entry.get("points")

            if level_id is not None:
                lid = str(level_id)
                if lid not in criteria_index[cid]["levels"]:
                    raise serializers.ValidationError(
                        f"Level {lid} does not belong to criterion {cid}."
                    )
                level = criteria_index[cid]["levels"][lid]
                # If no explicit points, derive from the level.
                if points is None:
                    points = level.points
            else:
                lid = None

            if points is None:
                raise serializers.ValidationError(
                    f"Score for criterion {cid} must include either level_id or points."
                )
            # Clamp / validate
            if points < 0:
                raise serializers.ValidationError("Points must be non-negative.")
            if points > criterion.max_points:
                raise serializers.ValidationError(
                    f"Points for criterion {cid} exceed its max_points "
                    f"({criterion.max_points})."
                )

            total += Decimal(str(points))
            normalized_scores[cid] = {
                "level_id": lid,
                "points": str(points),
                "comment": entry.get("comment", "") or "",
            }

        attrs["_normalized_scores"] = normalized_scores
        attrs["_total_score"] = total
        attrs["_rubric"] = rubric
        return attrs


# ---------------------------------------------------------------------------
# Assignment-rubric attach
# ---------------------------------------------------------------------------


class AttachRubricSerializer(serializers.Serializer):
    rubric_id = serializers.UUIDField(allow_null=True, required=False)
