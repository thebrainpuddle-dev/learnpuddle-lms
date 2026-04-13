# apps/notifications/middleware.py
"""
WebSocket authentication middleware using JWT tokens.

Authenticates WebSocket connections using JWT token passed as a
WebSocket subprotocol: Sec-WebSocket-Protocol: Bearer.<jwt>

Security: Tokens are NOT accepted via URL query strings to prevent
leakage through browser history, server/proxy access logs, and
referer headers.
"""

import logging
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)

# Subprotocol prefix used to carry the JWT token
BEARER_PREFIX = "Bearer."


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
        logger.warning("User not found for token")
        return AnonymousUser()
    except Exception as e:
        logger.error(f"Error validating JWT: {e}")
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware to authenticate WebSocket connections using JWT.

    Token is passed via the WebSocket subprotocol header:
        Sec-WebSocket-Protocol: Bearer.<jwt>

    The matched subprotocol is stored in scope so the consumer can
    accept the connection with the correct subprotocol (required by
    the WebSocket spec for the handshake to succeed).

    Sets scope["user"] to the authenticated user or AnonymousUser.
    """

    async def __call__(self, scope, receive, send):
        token = None
        accepted_subprotocol = None

        # Extract token from subprotocol (Bearer.<jwt>)
        subprotocols = scope.get("subprotocols", [])
        for protocol in subprotocols:
            if protocol.startswith(BEARER_PREFIX):
                token = protocol[len(BEARER_PREFIX):]
                accepted_subprotocol = protocol
                break

        # Authenticate user
        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        # Store the matched subprotocol so the consumer can accept it
        scope["accepted_subprotocol"] = accepted_subprotocol

        return await super().__call__(scope, receive, send)
