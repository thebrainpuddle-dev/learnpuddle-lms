"""
Parent portal authentication utilities.

Provides:
    - parent_required decorator for view protection
    - Validates ParentToken-based session tokens
"""

import functools
import logging

from rest_framework import status
from rest_framework.response import Response

from apps.courses.parent_models import ParentSession

logger = logging.getLogger(__name__)


def parent_required(view_func):
    """
    Decorator that validates a parent session token from the Authorization header.
    Sets request.parent_session and request.parent_email on success.

    Expected header: Authorization: ParentToken <session_token>
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('ParentToken '):
            return Response(
                {"error": "Parent authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token = auth_header.split(' ', 1)[1].strip()
        if not token:
            return Response(
                {"error": "Invalid authentication token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            session = ParentSession.objects.select_related(
                'tenant',
            ).prefetch_related(
                'students',
            ).get(
                session_token=token,
                is_active=True,
            )
        except ParentSession.DoesNotExist:
            return Response(
                {"error": "Invalid or expired session"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if session.is_expired:
            session.is_active = False
            session.save(update_fields=['is_active'])
            return Response(
                {"error": "Session expired. Please request a new login link."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Validate tenant matches request tenant
        if hasattr(request, 'tenant') and request.tenant and session.tenant != request.tenant:
            return Response(
                {"error": "Invalid session for this institution"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Set parent context on request
        request.parent_session = session
        request.parent_email = session.parent_email
        request.tenant = session.tenant

        # Update last_accessed
        session.save(update_fields=['last_accessed'])

        return view_func(request, *args, **kwargs)
    return wrapper
