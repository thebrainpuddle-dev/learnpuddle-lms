# apps/users/student_serializers.py

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password

from apps.users.models import User


class StudentSerializer(serializers.ModelSerializer):
    """Serializer for returning student info (admin view)."""
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'role',
            'student_id', 'grade_level', 'section',
            'parent_email', 'enrollment_date',
            'bio', 'profile_picture', 'profile_picture_url',
            'is_active', 'email_verified', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_profile_picture_url(self, obj):
        if not obj.profile_picture:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.profile_picture.url)
        return obj.profile_picture.url


class RegisterStudentSerializer(serializers.ModelSerializer):
    """Serializer for admin to create student accounts."""

    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm',
            'first_name', 'last_name',
            'student_id', 'grade_level', 'section',
            'parent_email', 'enrollment_date',
        ]
        extra_kwargs = {
            'student_id': {'required': False, 'allow_blank': True},
            'grade_level': {'required': False, 'allow_blank': True},
            'section': {'required': False, 'allow_blank': True},
            'parent_email': {'required': False, 'allow_blank': True},
            'enrollment_date': {'required': False, 'allow_null': True},
        }

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value, is_deleted=False).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        deleted_user = User.all_objects.filter(email__iexact=value, is_deleted=True).first()
        if deleted_user:
            raise serializers.ValidationError(
                "This email was previously used. Contact support to restore."
            )
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords don't match"})
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        tenant = self.context['request'].tenant
        validated_data['email'] = validated_data['email'].lower().strip()

        user = User.objects.create_user(
            **validated_data,
            password=password,
            tenant=tenant,
            role='STUDENT',
        )
        return user
