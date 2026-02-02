# apps/users/tokens.py

from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens_for_user(user):
    """
    Generate JWT tokens with custom claims.
    """
    refresh = RefreshToken.for_user(user)
    
    # Add custom claims
    refresh['email'] = user.email
    refresh['role'] = user.role
    refresh['tenant_id'] = str(user.tenant_id) if user.tenant_id else None
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
