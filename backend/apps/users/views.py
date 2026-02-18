# apps/users/views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import update_session_auth_hash
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .serializers import (
    UserSerializer, LoginSerializer, RegisterTeacherSerializer,
    ChangePasswordSerializer
)
from .tokens import get_tokens_for_user
from utils.decorators import admin_only, tenant_required, check_tenant_limit
from utils.audit import log_audit


class LoginThrottle(ScopedRateThrottle):
    scope = 'login'


class PasswordResetThrottle(ScopedRateThrottle):
    scope = 'password_reset'


class RegisterThrottle(ScopedRateThrottle):
    scope = 'register'


class EmailVerifyThrottle(ScopedRateThrottle):
    scope = 'email_verify'


class ResendVerifyThrottle(ScopedRateThrottle):
    scope = 'resend_verify'


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login_view(request):
    """
    User login endpoint.
    Returns access and refresh tokens with custom claims.
    
    May return `requires_2fa: true` if user has 2FA enabled.
    May return `must_change_password: true` if user needs to change password.
    """
    serializer = LoginSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    
    user = serializer.validated_data['user']
    
    # Check if 2FA is required
    from django_otp.plugins.otp_totp.models import TOTPDevice
    totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    
    if totp_device:
        # User has 2FA enabled - don't issue tokens yet
        log_audit('LOGIN_2FA_REQUIRED', 'User', target_id=str(user.id), target_repr=str(user), request=request, actor=user)
        return Response({
            'requires_2fa': True,
            'user_id': str(user.id),
            'message': 'Please enter your 2FA code',
        }, status=status.HTTP_200_OK)
    
    # Update last login
    from django.utils import timezone
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])
    
    # Generate tokens with custom claims
    tokens = get_tokens_for_user(user)

    log_audit('LOGIN', 'User', target_id=str(user.id), target_repr=str(user), request=request, actor=user)

    response_data = {
        'user': UserSerializer(user).data,
        'tokens': tokens,
    }
    
    # Check if user must change password
    if user.must_change_password:
        response_data['must_change_password'] = True
        response_data['message'] = 'Please change your password before continuing'

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    User logout endpoint.
    Blacklists the refresh token.
    """
    try:
        refresh_token = request.data.get('refresh_token')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        token = RefreshToken(refresh_token)
        token.blacklist()

        log_audit('LOGOUT', 'User', target_id=str(request.user.id), target_repr=str(request.user), request=request)

        return Response(
            {'message': 'Logout successful'},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': 'Invalid token'},
            status=status.HTTP_400_BAD_REQUEST
        )


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    """
    Refresh access token using refresh token.
    Validates that the token is not blacklisted (e.g. after logout).
    """
    try:
        refresh_token = request.data.get('refresh_token')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        refresh = RefreshToken(refresh_token)
        # Check blacklist — rejects tokens that were invalidated on logout
        if hasattr(refresh, 'check_blacklist'):
            refresh.check_blacklist()
        
        return Response({
            'access': str(refresh.access_token),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': 'Invalid or expired refresh token'},
            status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me_view(request):
    """
    GET: Get current user profile.
    PATCH: Update editable profile fields. Supports multipart for profile_picture.
    """
    if request.method == 'PATCH':
        allowed_text = {'first_name', 'last_name', 'department', 'subjects', 'grades', 'designation', 'bio'}
        user = request.user
        for key, value in request.data.items():
            if key in allowed_text:
                setattr(user, key, value)
        # Handle profile picture upload (validate type + size)
        if 'profile_picture' in request.FILES:
            pic = request.FILES['profile_picture']
            allowed_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
            allowed_mimes = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
            max_size = 5 * 1024 * 1024  # 5 MB

            ext = ''
            name = getattr(pic, 'name', '') or ''
            if '.' in name:
                ext = '.' + name.rsplit('.', 1)[-1].lower()
            mime = getattr(pic, 'content_type', '') or ''
            size = getattr(pic, 'size', 0) or 0

            if not ext and not mime:
                return Response({'error': 'File must have a recognizable extension or MIME type.'}, status=status.HTTP_400_BAD_REQUEST)

            if ext and ext not in allowed_exts:
                return Response(
                    {'error': f"Image type '{ext}' not allowed. Accepted: {', '.join(sorted(allowed_exts))}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if mime and mime not in allowed_mimes:
                return Response({'error': f"MIME type '{mime}' not allowed."}, status=status.HTTP_400_BAD_REQUEST)
            if size > max_size:
                return Response({'error': 'Profile picture must be under 5 MB.'}, status=status.HTTP_400_BAD_REQUEST)

            # Verify file is a valid image by reading its content
            try:
                from PIL import Image
                pic.seek(0)
                img = Image.open(pic)
                img.verify()
                pic.seek(0)
            except Exception:
                return Response({'error': 'File is not a valid image.'}, status=status.HTTP_400_BAD_REQUEST)

            user.profile_picture = pic
        user.save()
        return Response(UserSerializer(user, context={'request': request}).data, status=status.HTTP_200_OK)

    serializer = UserSerializer(request.user, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([RegisterThrottle])
@admin_only
@tenant_required
@check_tenant_limit("teachers")
def register_teacher_view(request):
    """
    Admin endpoint to create teacher accounts.
    """
    serializer = RegisterTeacherSerializer(
        data=request.data,
        context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    # Send welcome/verification email
    _send_verification_email(user, request)

    log_audit('CREATE', 'User', target_id=str(user.id), target_repr=str(user), request=request)

    return Response(
        UserSerializer(user).data,
        status=status.HTTP_201_CREATED
    )


def _send_verification_email(user, request=None):
    """Send email verification link to a newly created user."""
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.mail import send_mail
    from django.conf import settings
    from utils.email_verification import email_verification_token

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    domain = getattr(settings, 'PLATFORM_DOMAIN', 'lms.com')
    scheme = 'https' if not settings.DEBUG else 'http'
    port = ':3000' if settings.DEBUG else ''
    subdomain = user.tenant.subdomain if user.tenant else ''
    base = f"{scheme}://{subdomain + '.' if subdomain else ''}{domain}{port}"
    verify_link = f"{base}/verify-email?uid={uid}&token={token}"

    send_mail(
        subject=f"Welcome to {getattr(settings, 'PLATFORM_NAME', 'Brain LMS')} — Verify your email",
        message=(
            f"Hi {user.first_name},\n\n"
            f"Your account has been created. Please verify your email address by clicking the link below:\n\n"
            f"  {verify_link}\n\n"
            f"This link expires in 3 days.\n\n"
            f"If you didn't expect this, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """
    Change user password.
    Also clears the must_change_password flag if set.
    """
    serializer = ChangePasswordSerializer(
        data=request.data,
        context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    
    # Set new password and clear must_change_password
    user = request.user
    user.set_password(serializer.validated_data['new_password'])
    user.must_change_password = False
    user.save(update_fields=['password', 'must_change_password'])

    # Update session to keep user logged in
    update_session_auth_hash(request, user)

    log_audit('PASSWORD_CHANGE', 'User', target_id=str(user.id), target_repr=str(user), request=request)

    return Response(
        {'message': 'Password changed successfully'},
        status=status.HTTP_200_OK
    )


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def request_password_reset_view(request):
    """
    Request password reset email.
    Sends a time-limited token via email. Never reveals whether the email exists.
    """
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.mail import send_mail
    from django.conf import settings
    from .models import User

    email = request.data.get('email')
    if not email:
        return Response(
            {'error': 'Email is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Always return success to avoid email enumeration
    try:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist:
        return Response({'message': 'Password reset email sent if account exists'})

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    domain = getattr(settings, 'PLATFORM_DOMAIN', 'lms.com')
    scheme = 'https' if not settings.DEBUG else 'http'
    port = ':3000' if settings.DEBUG else ''
    subdomain = user.tenant.subdomain if user.tenant else ''
    base = f"{scheme}://{subdomain + '.' if subdomain else ''}{domain}{port}"
    reset_link = f"{base}/reset-password?uid={uid}&token={token}"

    send_mail(
        subject=f"Password reset — {getattr(settings, 'PLATFORM_NAME', 'Brain LMS')}",
        message=(
            f"Hi {user.first_name},\n\n"
            f"Click the link below to reset your password:\n\n"
            f"  {reset_link}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"If you didn't request this, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )

    return Response({'message': 'Password reset email sent if account exists'})


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def confirm_password_reset_view(request):
    """
    Confirm password reset with uid + token + new password.
    """
    from django.contrib.auth.tokens import default_token_generator
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from django.utils.http import urlsafe_base64_decode
    from .models import User

    uid = request.data.get('uid')
    token = request.data.get('token')
    new_password = request.data.get('new_password')

    if not uid or not token or not new_password:
        return Response(
            {'error': 'uid, token, and new_password are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user_id = urlsafe_base64_decode(uid).decode()
        user = User.objects.get(pk=user_id, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({'error': 'Invalid reset link'}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({'error': 'Reset link has expired or is invalid'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        validate_password(new_password, user)
    except ValidationError as e:
        messages = getattr(e, 'messages', [str(e)])
        return Response(
            {'error': 'Password does not meet requirements', 'details': list(messages)},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save()

    log_audit('PASSWORD_RESET', 'User', target_id=str(user.id), target_repr=str(user), request=request, actor=user)

    return Response({'message': 'Password has been reset successfully'})


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([EmailVerifyThrottle])
def verify_email_view(request):
    """
    Verify email with uid + token from the verification link.
    """
    from django.utils.http import urlsafe_base64_decode
    from utils.email_verification import email_verification_token
    from .models import User

    uid = request.data.get('uid')
    token = request.data.get('token')

    if not uid or not token:
        return Response(
            {'error': 'uid and token are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user_id = urlsafe_base64_decode(uid).decode()
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({'error': 'Invalid verification link'}, status=status.HTTP_400_BAD_REQUEST)

    if user.email_verified:
        return Response({'message': 'Email already verified'})

    if not email_verification_token.check_token(user, token):
        return Response({'error': 'Verification link has expired or is invalid'}, status=status.HTTP_400_BAD_REQUEST)

    user.email_verified = True
    user.save(update_fields=['email_verified'])

    return Response({'message': 'Email verified successfully'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ResendVerifyThrottle])
def resend_verification_view(request):
    """Resend verification email to the current user."""
    user = request.user
    if user.email_verified:
        return Response({'message': 'Email already verified'})
    _send_verification_email(user, request)
    return Response({'message': 'Verification email sent'})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def preferences_view(request):
    """
    GET: Return notification preferences.
    PATCH: Update notification preferences.
    """
    ALLOWED_PREF_KEYS = {
        'email_courses', 'email_assignments', 'email_reminders',
        'email_announcements', 'in_app_courses', 'in_app_assignments',
        'in_app_reminders', 'in_app_announcements',
    }
    user = request.user
    if request.method == 'PATCH':
        prefs = user.notification_preferences or {}
        for key, value in request.data.items():
            if key in ALLOWED_PREF_KEYS and isinstance(value, bool):
                prefs[key] = value
        user.notification_preferences = prefs
        user.save(update_fields=['notification_preferences'])
    return Response(user.notification_preferences or {})
