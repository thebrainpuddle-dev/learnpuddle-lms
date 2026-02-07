# apps/users/serializers.py

from rest_framework import serializers
from apps.users.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for returning user info."""
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'role',
            'employee_id', 'subjects', 'grades', 'department',
            'designation', 'bio', 'profile_picture', 'profile_picture_url',
            'date_of_joining',
            'is_active', 'email_verified', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_profile_picture_url(self, obj):
        if not obj.profile_picture:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.profile_picture.url)
        return obj.profile_picture.url


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    portal = serializers.ChoiceField(
        choices=['super_admin', 'tenant'],
        default='tenant',
        required=False,
        help_text="Which portal the login is coming from. 'super_admin' only accepts SUPER_ADMIN users; 'tenant' only accepts tenant users.",
    )
    
    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        portal = data.get('portal', 'tenant')
        
        if not email or not password:
            raise serializers.ValidationError("Email and password are required")
        
        # Authenticate user
        user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password
        )
        
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled")
        
        # Portal-aware role validation: prevent cross-portal logins
        if portal == 'super_admin' and user.role != 'SUPER_ADMIN':
            raise serializers.ValidationError(
                "This login page is for platform administrators only. "
                "Please use your school's login page."
            )
        if portal == 'tenant' and user.role == 'SUPER_ADMIN':
            raise serializers.ValidationError(
                "Super admin accounts must log in at the platform admin portal."
            )
        
        data['user'] = user
        return data


class RegisterTeacherSerializer(serializers.ModelSerializer):
    """Serializer for admin to create teacher accounts."""
    
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'first_name', 'last_name',
            'employee_id', 'subjects', 'grades', 'department', 'date_of_joining'
        ]
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords don't match"})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # Get current tenant from context
        tenant = self.context['request'].tenant
        
        user = User.objects.create_user(
            **validated_data,
            tenant=tenant,
            role='TEACHER'
        )
        user.set_password(password)
        user.save()
        
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password."""
    
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True, write_only=True)
    
    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password": "Passwords don't match"})
        return data
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value
