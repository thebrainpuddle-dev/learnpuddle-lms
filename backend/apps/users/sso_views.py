# apps/users/sso_views.py
"""
SSO (Single Sign-On) views for OAuth2/OIDC authentication.

Supports:
- Google Workspace SSO
- Token exchange after OAuth callback
- SSO status check
"""

import logging
from django.conf import settings
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from social_django.utils import psa

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def sso_providers(request):
    """
    Get available SSO providers for the current tenant.
    
    Returns list of enabled SSO providers with auth URLs.
    """
    providers = []
    
    # Check if Google SSO is configured
    if settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY:
        providers.append({
            'id': 'google-oauth2',
            'name': 'Google',
            'icon': 'google',
            'auth_url': '/api/v1/users/auth/sso/google-oauth2/',
        })
    
    # Check tenant-specific SSO settings
    tenant = getattr(request, 'tenant', None)
    if tenant:
        return Response({
            'providers': providers if tenant.feature_sso else [],
            'sso_enabled': tenant.feature_sso,
            'sso_required': tenant.require_sso,
        })
    
    return Response({
        'providers': providers,
        'sso_enabled': bool(providers),
        'sso_required': False,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
@psa('social:complete')
def sso_callback(request, backend):
    """
    Handle OAuth callback and exchange for JWT tokens.
    
    This is called after the OAuth provider redirects back.
    Exchanges the OAuth tokens for our JWT tokens.
    """
    user = request.backend.do_auth(request.backend.strategy.request_data())
    
    if user and user.is_active:
        # Generate a short-lived one-time code instead of exposing tokens in URL
        # The frontend will exchange this code for tokens via POST to /sso/token-exchange/
        import secrets as _secrets
        from django.core.cache import cache
        
        sso_code = _secrets.token_urlsafe(48)
        
        # Generate JWT tokens and store in cache (expires in 60 seconds)
        refresh = RefreshToken.for_user(user)
        cache.set(f'sso_code:{sso_code}', {
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user_id': str(user.id),
        }, timeout=60)
        
        # Redirect with only the one-time code (not the actual tokens)
        frontend_url = settings.SOCIAL_AUTH_LOGIN_REDIRECT_URL
        redirect_url = f"{frontend_url}?code={sso_code}"
        
        logger.info(f"SSO login successful for {user.email}")
        return redirect(redirect_url)
    
    logger.warning(f"SSO login failed for backend {backend}")
    return redirect(settings.SOCIAL_AUTH_LOGIN_ERROR_URL)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def sso_token_exchange(request):
    """
    Exchange a one-time SSO code for JWT tokens.
    
    The SSO callback redirect includes a short-lived code (not tokens).
    The frontend calls this endpoint to exchange the code for actual tokens.
    
    POST body:
    {
        "code": "one-time-sso-code"
    }
    """
    from django.core.cache import cache
    
    code = request.data.get('code')
    if not code:
        return Response(
            {'error': 'code is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Look up and consume the one-time code
    cache_key = f'sso_code:{code}'
    token_data = cache.get(cache_key)
    
    if not token_data:
        return Response(
            {'error': 'Invalid or expired code'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Delete the code so it can't be reused
    cache.delete(cache_key)
    
    return Response({
        'access_token': token_data['access_token'],
        'refresh_token': token_data['refresh_token'],
        'user_id': token_data['user_id'],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sso_status(request):
    """
    Get SSO status for the current user.
    
    Returns whether user has linked social accounts.
    """
    from social_django.models import UserSocialAuth
    
    user = request.user
    social_auths = UserSocialAuth.objects.filter(user=user)
    
    linked_providers = [
        {
            'provider': sa.provider,
            'uid': sa.uid,
            'created': sa.created.isoformat() if hasattr(sa, 'created') else None,
        }
        for sa in social_auths
    ]
    
    return Response({
        'has_password': user.has_usable_password(),
        'linked_providers': linked_providers,
        'can_unlink': user.has_usable_password() and len(linked_providers) > 0,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sso_unlink(request):
    """
    Unlink a social account from the user.
    
    POST body:
    {
        "provider": "google-oauth2"
    }
    
    Only allowed if user has a password set.
    """
    from social_django.models import UserSocialAuth
    
    provider = request.data.get('provider')
    if not provider:
        return Response(
            {'error': 'provider is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    user = request.user
    
    # Prevent unlinking if no password
    if not user.has_usable_password():
        return Response(
            {'error': 'Cannot unlink SSO account without a password set'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        social_auth = UserSocialAuth.objects.get(user=user, provider=provider)
        social_auth.delete()
        
        logger.info(f"User {user.email} unlinked {provider}")
        return Response({'success': True})
    except UserSocialAuth.DoesNotExist:
        return Response(
            {'error': 'Provider not linked'},
            status=status.HTTP_404_NOT_FOUND
        )
