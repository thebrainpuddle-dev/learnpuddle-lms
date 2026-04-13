# apps/users/serializers.py

import re

from rest_framework import serializers
from apps.users.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache

# Account lockout settings
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes


def _lockout_key(email):
    return f"login_fail:{email.lower()}"


# Patterns for auto-generated user IDs: PREFIX-S-DIGITS or PREFIX-T-DIGITS
_STUDENT_ID_PATTERN = re.compile(r'^[A-Z]{2,10}-S-\d{4,}$', re.IGNORECASE)
_TEACHER_ID_PATTERN = re.compile(r'^[A-Z]{2,10}-T-\d{4,}$', re.IGNORECASE)


def detect_identifier_type(identifier: str) -> str:
    """
    Detect whether a login identifier is an email, student ID, or teacher ID.

    Rules:
    - Contains '@' → email
    - Matches PREFIX-S-DIGITS → student_id  (e.g. KIS-S-0001)
    - Matches PREFIX-T-DIGITS → teacher_id  (e.g. KIS-T-0042)
    - Otherwise → email (default fallback)
    """
    identifier = identifier.strip()
    if '@' in identifier:
        return 'email'
    if _STUDENT_ID_PATTERN.match(identifier):
        return 'student_id'
    if _TEACHER_ID_PATTERN.match(identifier):
        return 'teacher_id'
    return 'email'


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for returning user info."""
    profile_picture_url = serializers.SerializerMethodField()
    tenant_subdomain = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'role',
            'student_id', 'grade_fk', 'section_fk',
            'employee_id', 'subjects', 'grades', 'department',
            'designation', 'bio', 'profile_picture', 'profile_picture_url',
            'date_of_joining',
            'is_active', 'email_verified', 'created_at',
            'tenant_subdomain',
        ]
        read_only_fields = ['id', 'created_at']

    def get_profile_picture_url(self, obj):
        if not obj.profile_picture:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.profile_picture.url)
        return obj.profile_picture.url

    def get_tenant_subdomain(self, obj):
        return obj.tenant.subdomain if obj.tenant_id else None


class LoginSerializer(serializers.Serializer):
    """Serializer for user login with flexible identifier support.

    Accepts email, student ID (e.g. KIS-S-0001), or teacher ID (e.g. KIS-T-0042).
    """

    identifier = serializers.CharField(
        required=False,
        help_text="Email, student ID (KIS-S-0001), or teacher ID (KIS-T-0001)",
    )
    email = serializers.EmailField(
        required=False,
        help_text="Legacy field — use 'identifier' instead",
    )
    password = serializers.CharField(write_only=True)
    portal = serializers.ChoiceField(
        choices=['super_admin', 'tenant'],
        default='tenant',
        required=False,
        help_text="Which portal the login is coming from.",
    )

    def validate(self, data):
        # Support both 'identifier' (new) and 'email' (legacy) fields
        identifier = (data.get('identifier') or data.get('email') or '').strip()
        password = data.get('password')
        portal = data.get('portal', 'tenant')

        if not identifier or not password:
            raise serializers.ValidationError("Identifier and password are required")

        # Check account lockout
        key = _lockout_key(identifier)
        attempts = cache.get(key, 0)
        if attempts >= MAX_LOGIN_ATTEMPTS:
            raise serializers.ValidationError(
                "Account temporarily locked due to too many failed attempts. "
                "Please try again in 15 minutes."
            )

        # Detect identifier type and resolve user
        id_type = detect_identifier_type(identifier)
        user = None

        if id_type == 'email':
            # Standard email-based authentication
            user = authenticate(
                request=self.context.get('request'),
                username=identifier,
                password=password,
            )
        elif id_type == 'student_id':
            # Look up by student_id — REQUIRES tenant for multi-tenant isolation
            from apps.users.models import User as UserModel
            try:
                request = self.context.get('request')
                tenant = getattr(request, 'tenant', None) if request else None
                if not tenant:
                    raise serializers.ValidationError("Invalid credentials")
                found = UserModel.objects.filter(
                    tenant=tenant, is_deleted=False,
                ).get(student_id__iexact=identifier)
                if found.check_password(password):
                    user = found
            except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
                pass
        elif id_type == 'teacher_id':
            # Look up by employee_id — REQUIRES tenant for multi-tenant isolation
            from apps.users.models import User as UserModel
            try:
                request = self.context.get('request')
                tenant = getattr(request, 'tenant', None) if request else None
                if not tenant:
                    raise serializers.ValidationError("Invalid credentials")
                found = UserModel.objects.filter(
                    tenant=tenant, is_deleted=False,
                ).get(employee_id__iexact=identifier)
                if found.check_password(password):
                    user = found
            except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
                pass

        if not user:
            # Increment failed attempts
            cache.set(key, attempts + 1, LOCKOUT_DURATION_SECONDS)
            raise serializers.ValidationError("Invalid credentials")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled")

        # Block login if the user's tenant is deactivated
        if portal == 'tenant' and user.tenant_id and not user.tenant.is_active:
            raise serializers.ValidationError(
                "Your school account has been deactivated. Please contact your administrator."
            )

        # Portal-aware role validation
        if portal == 'super_admin' and user.role != 'SUPER_ADMIN':
            raise serializers.ValidationError(
                "This login page is for platform administrators only. "
                "Please use your school's login page."
            )

        if portal == 'tenant' and user.role == 'SUPER_ADMIN':
            raise serializers.ValidationError(
                "Please use the platform admin portal at the main domain."
            )

        # Reset failed attempts on success
        cache.delete(key)

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
        extra_kwargs = {
            'employee_id': {'required': False, 'allow_blank': True},
            'subjects': {'required': False, 'default': list},
            'grades': {'required': False, 'default': list},
            'department': {'required': False, 'allow_blank': True},
            'date_of_joining': {'required': False, 'allow_null': True},
        }
    
    def validate_email(self, value):
        """Check if email already exists (globally, as emails are unique across tenants)."""
        value = value.lower().strip()
        
        # Check for existing active user
        if User.objects.filter(email__iexact=value, is_deleted=False).exists():
            raise serializers.ValidationError(
                "A user with this email already exists. "
                "If they need access to this school, contact support."
            )
        
        # Check for soft-deleted user that could be restored
        deleted_user = User.objects.filter(email__iexact=value, is_deleted=True).first()
        if deleted_user:
            raise serializers.ValidationError(
                "This email was previously used. "
                "Contact support to restore the account or use a different email."
            )
        
        return value
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords don't match"})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        # Get current tenant from context
        tenant = self.context['request'].tenant

        # Normalize email
        validated_data['email'] = validated_data['email'].lower().strip()

        # Pass password directly to create_user() which handles hashing
        # internally via set_password(). Previously, create_user() was called
        # without the password (defaulting to None → unusable password), then
        # set_password() + save() were called separately — a redundant pattern
        # that risked double-hashing if create_user() ever received the password.
        user = User.objects.create_user(
            **validated_data,
            password=password,
            tenant=tenant,
            role='TEACHER'
        )

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
