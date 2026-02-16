# apps/users/twofa_views.py
"""
Two-Factor Authentication (2FA/MFA) views.

Supports:
- TOTP (Time-based One-Time Password) setup
- Backup codes generation
- 2FA verification during login
- 2FA requirement enforcement per tenant
"""

import io
import base64
import logging
import secrets
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle


class TwoFAVerifyThrottle(ScopedRateThrottle):
    scope = 'twofa_verify'
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

logger = logging.getLogger(__name__)


def get_qr_code_data_uri(device: TOTPDevice) -> str:
    """Generate QR code as data URI for TOTP setup."""
    try:
        import qrcode
        from qrcode.image.pure import PyPNGImage
        
        # Generate provisioning URI
        uri = device.config_url
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        b64_img = base64.b64encode(buffer.read()).decode('utf-8')
        return f"data:image/png;base64,{b64_img}"
    except ImportError:
        return None


def generate_backup_codes(user, count: int = 10) -> list[str]:
    """Generate new backup codes for user."""
    # Get or create static device
    device, _ = StaticDevice.objects.get_or_create(
        user=user,
        name='backup',
        defaults={'confirmed': True}
    )
    
    # Remove old tokens
    device.token_set.all().delete()
    
    # Generate new tokens
    codes = []
    for _ in range(count):
        code = secrets.token_hex(4).upper()  # 8-character hex code
        StaticToken.objects.create(device=device, token=code)
        codes.append(code)
    
    return codes


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def twofa_status(request):
    """
    Get 2FA status for the current user.
    
    Returns whether 2FA is enabled and configuration options.
    """
    user = request.user
    
    # Check for TOTP device
    totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    
    # Check for backup codes
    static_device = StaticDevice.objects.filter(user=user, confirmed=True).first()
    backup_codes_remaining = (
        static_device.token_set.count() if static_device else 0
    )
    
    # Check tenant requirement
    tenant = getattr(request, 'tenant', None)
    required = tenant.require_2fa if tenant else False
    
    return Response({
        'enabled': totp_device is not None,
        'required': required,
        'totp_configured': totp_device is not None,
        'backup_codes_remaining': backup_codes_remaining,
        'can_disable': not required,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def twofa_setup_start(request):
    """
    Start 2FA setup - generates TOTP secret and QR code.
    
    Returns:
    {
        "secret": "base32_secret",
        "qr_code": "data:image/png;base64,...",
        "provisioning_uri": "otpauth://..."
    }
    """
    user = request.user
    
    # Check if already has confirmed device
    existing = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if existing:
        return Response(
            {'error': '2FA is already enabled. Disable it first to reconfigure.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Remove any unconfirmed devices
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    
    # Create new device
    device = TOTPDevice.objects.create(
        user=user,
        name=f"{settings.OTP_TOTP_ISSUER} ({user.email})",
        confirmed=False,
    )
    
    # Generate QR code
    qr_code = get_qr_code_data_uri(device)
    
    return Response({
        'secret': base64.b32encode(device.bin_key).decode('utf-8'),
        'qr_code': qr_code,
        'provisioning_uri': device.config_url,
        'device_id': str(device.id),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def twofa_setup_confirm(request):
    """
    Confirm 2FA setup by verifying a TOTP code.
    
    POST body:
    {
        "code": "123456"
    }
    
    Returns backup codes on success.
    """
    user = request.user
    code = request.data.get('code', '').strip()
    
    if not code or len(code) != 6:
        return Response(
            {'error': 'A 6-digit code is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Find unconfirmed device
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if not device:
        return Response(
            {'error': 'No pending 2FA setup found. Start setup first.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verify code
    if not device.verify_token(code):
        return Response(
            {'error': 'Invalid code. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Confirm device
    device.confirmed = True
    device.save()
    
    # Generate backup codes
    backup_codes = generate_backup_codes(user)
    
    logger.info(f"2FA enabled for user {user.email}")
    
    return Response({
        'success': True,
        'message': '2FA has been enabled successfully',
        'backup_codes': backup_codes,
        'backup_codes_warning': 'Save these backup codes in a secure location. They will only be shown once.',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def twofa_disable(request):
    """
    Disable 2FA for the current user.
    
    POST body:
    {
        "code": "123456",  // TOTP or backup code
        "password": "current_password"
    }
    """
    user = request.user
    code = request.data.get('code', '').strip()
    password = request.data.get('password', '')
    
    # Check tenant requirement
    tenant = getattr(request, 'tenant', None)
    if tenant and tenant.require_2fa:
        return Response(
            {'error': 'Your organization requires 2FA. It cannot be disabled.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Verify password
    if not user.check_password(password):
        return Response(
            {'error': 'Invalid password'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verify 2FA code
    totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if not totp_device:
        return Response(
            {'error': '2FA is not enabled'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check TOTP code
    if not totp_device.verify_token(code):
        # Try backup code
        static_device = StaticDevice.objects.filter(user=user).first()
        if not static_device or not static_device.verify_token(code):
            return Response(
                {'error': 'Invalid verification code'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # Delete all OTP devices
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()
    
    logger.info(f"2FA disabled for user {user.email}")
    
    return Response({
        'success': True,
        'message': '2FA has been disabled',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def twofa_regenerate_backup_codes(request):
    """
    Regenerate backup codes (invalidates old codes).
    
    POST body:
    {
        "code": "123456"  // Current TOTP code required
    }
    """
    user = request.user
    code = request.data.get('code', '').strip()
    
    # Verify user has 2FA enabled
    totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if not totp_device:
        return Response(
            {'error': '2FA is not enabled'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verify TOTP code
    if not totp_device.verify_token(code):
        return Response(
            {'error': 'Invalid verification code'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Generate new backup codes
    backup_codes = generate_backup_codes(user)
    
    logger.info(f"Backup codes regenerated for user {user.email}")
    
    return Response({
        'backup_codes': backup_codes,
        'warning': 'Old backup codes have been invalidated. Save these new codes securely.',
    })


@api_view(['POST'])
@throttle_classes([TwoFAVerifyThrottle])
def twofa_verify(request):
    """
    Verify 2FA code during login.
    
    Called after password authentication if 2FA is enabled.
    
    POST body:
    {
        "user_id": "uuid",
        "code": "123456"
    }
    
    Returns JWT tokens on success.
    """
    from apps.users.models import User
    from rest_framework_simplejwt.tokens import RefreshToken
    
    user_id = request.data.get('user_id')
    code = request.data.get('code', '').strip()
    
    if not user_id or not code:
        return Response(
            {'error': 'user_id and code are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return Response(
            {'error': 'Invalid user'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verify TOTP code
    totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if totp_device and totp_device.verify_token(code):
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })
    
    # Try backup code
    static_device = StaticDevice.objects.filter(user=user).first()
    if static_device and static_device.verify_token(code):
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'backup_code_used': True,
        })
    
    return Response(
        {'error': 'Invalid verification code'},
        status=status.HTTP_400_BAD_REQUEST
    )
