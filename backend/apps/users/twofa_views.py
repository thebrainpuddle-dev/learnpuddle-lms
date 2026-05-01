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
from django.conf import settings
from rest_framework import status
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes, throttle_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle


class TwoFAVerifyThrottle(ScopedRateThrottle):
    scope = 'twofa_verify'
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice  # noqa: F401 — legacy fallback

from apps.users.twofa_models import (
    BackupCode,
    create_encrypted_totp_device,
    encrypted_provisioning_uri,
    generate_hashed_backup_codes,
    remaining_backup_codes,
    verify_and_consume_backup_code,
    verify_encrypted_totp,
)

logger = logging.getLogger(__name__)


def get_qr_code_data_uri(device: TOTPDevice, provisioning_uri: str = None) -> str:
    """Generate QR code as data URI for TOTP setup.

    ``provisioning_uri`` may be passed explicitly for encryption-at-rest
    devices (where ``device.config_url`` would derive the secret from
    the sentinel ``bin_key``).  When omitted we fall back to the
    legacy in-row derivation for backwards compatibility.
    """
    try:
        import qrcode
        from qrcode.image.pure import PyPNGImage

        uri = provisioning_uri or device.config_url

        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)  # type: ignore[arg-type]
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
    """Generate new backup codes for user.

    AUDIT-2026-04-26-PHASE3-7: codes are now stored as Django password
    hashes via ``BackupCode``.  The plaintext returned here is the only
    moment the codes exist outside the user's possession.
    """
    return generate_hashed_backup_codes(user, count=count)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
# No @tenant_required: reads request.user's own OTP devices; no cross-tenant data exposed.
def twofa_status(request):
    """
    Get 2FA status for the current user.

    Returns whether 2FA is enabled and configuration options.
    """
    user = request.user
    
    # Check for TOTP device
    totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    
    # Check for backup codes (hashed BackupCode rows; legacy StaticToken
    # rows are migrated by 0015_migrate_legacy_2fa_to_encrypted).
    backup_codes_remaining = remaining_backup_codes(user)
    
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
# No @tenant_required: creates OTP device for request.user only; no cross-tenant data exposed.
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

    # Create new device with the seed Fernet-encrypted at rest
    # (AUDIT-2026-04-26-PHASE3-7).  ``secret_b32`` is the only place the
    # plaintext secret exists in this request — it is shipped to the
    # client for QR rendering and discarded.
    device, secret_b32 = create_encrypted_totp_device(
        user,
        name=f"{settings.OTP_TOTP_ISSUER} ({user.email})",
        confirmed=False,
    )

    provisioning_uri = encrypted_provisioning_uri(device, secret_b32)
    qr_code = get_qr_code_data_uri(device, provisioning_uri=provisioning_uri)

    return Response({
        'secret': secret_b32,
        'qr_code': qr_code,
        'provisioning_uri': provisioning_uri,
        'device_id': str(device.id),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
# No @tenant_required: confirms OTP device for request.user only; no cross-tenant data exposed.
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
    
    # Verify code via the encryption-at-rest wrapper.
    if not verify_encrypted_totp(device, code):
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
# No @tenant_required: disables 2FA for request.user only; no cross-tenant data exposed.
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
    
    # Check TOTP code (via encrypted-at-rest wrapper)
    if not verify_encrypted_totp(totp_device, code):
        # Try backup code
        if not verify_and_consume_backup_code(user, code):
            return Response(
                {'error': 'Invalid verification code'},
                status=status.HTTP_400_BAD_REQUEST
            )

    # Delete all OTP devices and backup codes
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()
    BackupCode.objects.filter(user=user).delete()
    
    logger.info(f"2FA disabled for user {user.email}")
    
    return Response({
        'success': True,
        'message': '2FA has been disabled',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
# No @tenant_required: regenerates backup codes for request.user only; no cross-tenant data exposed.
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
    
    # Verify TOTP code (encryption-at-rest wrapper)
    if not verify_encrypted_totp(totp_device, code):
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


# ---------------------------------------------------------------------------
# Per-account 2FA lockout (AUDIT-2026-04-26-PHASE3-8)
# ---------------------------------------------------------------------------
#
# The bare-bones IP throttle on twofa_verify can be bypassed by an attacker
# who rotates source IPs.  These constants drive a defence-in-depth lockout
# that is keyed by user_id (and additionally by IP) and persisted in the
# Django cache so it survives across distinct challenge_tokens.
#
# Threshold: 5 failed attempts → lock for ``TWOFA_LOCKOUT_TTL`` seconds.
TWOFA_MAX_ATTEMPTS = 5
TWOFA_CHALLENGE_ATTEMPT_TTL = 10 * 60   # 10 min — same as challenge_token TTL
TWOFA_LOCKOUT_TTL = 15 * 60             # 15 min per (user, IP)


def _client_ip(request) -> str:
    """Best-effort IP extraction; matches DRF's default behaviour."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _twofa_lockout_key(user_id, ip: str) -> str:
    return f"2fa_lockout:{user_id}:{ip}"


def _twofa_attempts_key(challenge_token: str) -> str:
    return f"2fa_attempts:{challenge_token}"


def _is_locked_out(user_id, ip: str) -> bool:
    return bool(cache.get(_twofa_lockout_key(user_id, ip)))


def _register_failed_attempt(challenge_token: str, user_id, ip: str) -> bool:
    """Record a failed verify attempt.

    Returns ``True`` when the lockout threshold has just been crossed
    (caller should issue a 429 and destroy the challenge_token).
    """
    # Per-challenge counter — destroyed when the challenge_token is invalidated.
    chal_key = _twofa_attempts_key(challenge_token)
    chal_count = cache.get(chal_key, 0) + 1
    cache.set(chal_key, chal_count, timeout=TWOFA_CHALLENGE_ATTEMPT_TTL)

    # Per-user/IP counter — survives a fresh challenge_token, so an attacker
    # who burns one challenge then password-re-auths is still locked.
    user_key = f"2fa_attempts_user:{user_id}:{ip}"
    user_count = cache.get(user_key, 0) + 1
    cache.set(user_key, user_count, timeout=TWOFA_LOCKOUT_TTL)

    if chal_count >= TWOFA_MAX_ATTEMPTS or user_count >= TWOFA_MAX_ATTEMPTS:
        cache.set(
            _twofa_lockout_key(user_id, ip), True, timeout=TWOFA_LOCKOUT_TTL
        )
        return True
    return False


def _clear_attempts(challenge_token: str, user_id, ip: str) -> None:
    """Reset all counters after a successful verify."""
    cache.delete(_twofa_attempts_key(challenge_token))
    cache.delete(f"2fa_attempts_user:{user_id}:{ip}")
    cache.delete(_twofa_lockout_key(user_id, ip))


def _lockout_response():
    return Response(
        {
            'detail': 'Too many 2FA attempts. Sign in again.',
            'code': 'too_many_2fa_attempts',
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
@throttle_classes([TwoFAVerifyThrottle])
def twofa_verify(request):
    """
    Verify 2FA code during login.

    Called after password authentication if 2FA is enabled.

    POST body:
    {
        "challenge_token": "random_token",
        "code": "123456"
    }

    Returns JWT tokens on success.

    Security (AUDIT-2026-04-26-PHASE3-8):
      * Per-challenge_token attempt counter — at 5 wrong codes the challenge
        is destroyed and the endpoint returns 429.
      * Per-(user_id, IP) lockout counter — survives fresh challenge_tokens
        so an attacker who password-re-auths after burning a challenge stays
        locked for 15 minutes.
    """
    from apps.users.models import User
    from rest_framework_simplejwt.tokens import RefreshToken

    challenge_token = request.data.get('challenge_token')
    code = request.data.get('code', '').strip()

    if not challenge_token or not code:
        return Response(
            {'error': 'challenge_token and code are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Look up user_id from cache using the challenge token
    cache_key = f'2fa_challenge:{challenge_token}'
    user_id = cache.get(cache_key)
    if not user_id:
        return Response(
            {'error': 'Invalid or expired challenge token'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ip = _client_ip(request)

    # Per-account lockout — short-circuit BEFORE consulting the OTP devices,
    # so the attacker can't probe whether any code matches once locked.
    if _is_locked_out(user_id, ip):
        # Defensive: also destroy the challenge so a stuck client doesn't
        # keep hammering the same key after the lockout TTL expires.
        cache.delete(cache_key)
        return _lockout_response()

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return Response(
            {'error': 'Invalid user'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Verify TOTP code (encryption-at-rest wrapper)
    totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if totp_device and verify_encrypted_totp(totp_device, code):
        # Successful: reset attempt counters and consume the challenge.
        _clear_attempts(challenge_token, user_id, ip)
        cache.delete(cache_key)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })

    # Try backup code (hashed, single-use BackupCode rows).  Legacy
    # StaticToken plaintext fallback is preserved for installations
    # that have not yet run the data migration.
    if verify_and_consume_backup_code(user, code):
        _clear_attempts(challenge_token, user_id, ip)
        cache.delete(cache_key)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'backup_code_used': True,
        })

    static_device = StaticDevice.objects.filter(user=user).first()
    if static_device and static_device.verify_token(code):
        _clear_attempts(challenge_token, user_id, ip)
        cache.delete(cache_key)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'backup_code_used': True,
        })

    # Wrong code — register the failure.  When the threshold is reached
    # the per-(user, IP) lockout is set; the *current* response is still
    # 400 ("Invalid verification code") so the user who simply mistyped
    # the 5th code is not whip-sawed into a different error mid-attempt.
    # The *next* request will resolve the still-live challenge, hit the
    # lockout gate above, destroy the challenge, and return 429.
    _register_failed_attempt(challenge_token, user_id, ip)

    return Response(
        {'error': 'Invalid verification code'},
        status=status.HTTP_400_BAD_REQUEST
    )
