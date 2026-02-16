# apps/notifications/middleware.py
"""
WebSocket authentication middleware using JWT tokens.

Authenticates WebSocket connections using JWT token passed as:
1. Query parameter: /ws/notifications/?token=<jwt>
2. Subprotocol: Sec-WebSocket-Protocol: <jwt>
"""

import logging
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_from_token(token_str: str):
    """
    Validate JWT token and return the associated user.
    
    Args:
        token_str: JWT access token string
        
    Returns:
        User instance if valid, AnonymousUser otherwise
    """
    try:
        from apps.users.models import User
        
        token = AccessToken(token_str)
        user_id = token.payload.get("user_id")
        
        if not user_id:
            logger.warning("JWT token missing user_id")
            return AnonymousUser()
        
        user = User.objects.select_related("tenant").get(id=user_id, is_active=True)
        return user
        
    except (InvalidToken, TokenError) as e:
        logger.warning(f"Invalid JWT token: {e}")
        return AnonymousUser()
    except User.DoesNotExist:
        logger.warning(f"User not found for token")
        return AnonymousUser()
    except Exception as e:
        logger.error(f"Error validating JWT: {e}")
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware to authenticate WebSocket connections using JWT.
    
    Token can be passed via:
    - Query parameter: ?token=<jwt>
    - Subprotocol header (for browsers that don't support custom headers)
    
    Sets scope["user"] to the authenticated user or AnonymousUser.
    """
    
    async def __call__(self, scope, receive, send):
        # Extract token from query string
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]
        
        # Fallback: check subprotocols for token
        if not token:
            subprotocols = scope.get("subprotocols", [])
            for protocol in subprotocols:
                if protocol.startswith("jwt."):
                    token = protocol[4:]  # Remove "jwt." prefix
                    break
        
        # Authenticate user
        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)
