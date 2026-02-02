from rest_framework import serializers


class CourseProgressRowSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    teacher_name = serializers.CharField()
    teacher_email = serializers.EmailField()
    course_id = serializers.UUIDField()
    course_title = serializers.CharField()
    deadline = serializers.DateField(allow_null=True)
    status = serializers.CharField()
    completed_at = serializers.DateTimeField(allow_null=True)


class AssignmentStatusRowSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    teacher_name = serializers.CharField()
    teacher_email = serializers.EmailField()
    assignment_id = serializers.UUIDField()
    assignment_title = serializers.CharField()
    due_date = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    submitted_at = serializers.DateTimeField(allow_null=True)

