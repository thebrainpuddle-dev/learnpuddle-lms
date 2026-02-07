# apps/users/views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import update_session_auth_hash
from .serializers import (
    UserSerializer, LoginSerializer, RegisterTeacherSerializer,
    ChangePasswordSerializer
)
from .tokens import get_tokens_for_user
from utils.decorators import admin_only, tenant_required, check_tenant_limit


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    User login endpoint.
    Returns access and refresh tokens with custom claims.
    """
    serializer = LoginSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    
    user = serializer.validated_data['user']
    
    # Update last login
    from django.utils import timezone
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])
    
    # Generate tokens with custom claims
    tokens = get_tokens_for_user(user)
    
    return Response({
        'user': UserSerializer(user).data,
        'tokens': tokens
    }, status=status.HTTP_200_OK)


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
        
        return Response(
            {'message': 'Logout successful'},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': 'Invalid token'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    """
    Refresh access token using refresh token.
    """
    try:
        refresh_token = request.data.get('refresh_token')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        refresh = RefreshToken(refresh_token)
        
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
        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
        user.save()
        return Response(UserSerializer(user, context={'request': request}).data, status=status.HTTP_200_OK)

    serializer = UserSerializer(request.user, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
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
    
    # TODO: Send welcome email with login instructions
    
    return Response(
        UserSerializer(user).data,
        status=status.HTTP_201_CREATED
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """
    Change user password.
    """
    serializer = ChangePasswordSerializer(
        data=request.data,
        context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    
    # Set new password
    user = request.user
    user.set_password(serializer.validated_data['new_password'])
    user.save()
    
    # Update session to keep user logged in
    update_session_auth_hash(request, user)
    
    return Response(
        {'message': 'Password changed successfully'},
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([AllowAny])
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


@api_view(['POST'])
@permission_classes([AllowAny])
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

    return Response({'message': 'Password has been reset successfully'})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def preferences_view(request):
    """
    GET: Return notification preferences.
    PATCH: Update notification preferences.
    """
    user = request.user
    if request.method == 'PATCH':
        prefs = user.notification_preferences or {}
        prefs.update(request.data)
        user.notification_preferences = prefs
        user.save(update_fields=['notification_preferences'])
    return Response(user.notification_preferences or {})
