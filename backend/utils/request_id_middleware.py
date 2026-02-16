# utils/request_id_middleware.py
"""
Request ID middleware for tracing requests through the system.

Assigns a unique X-Request-ID to every request and injects it into the
logging context so all log messages for a request can be correlated.
"""

import uuid
from utils.logging import set_request_context, clear_request_context


class RequestIDMiddleware:
    """
    Assign a unique X-Request-ID to every request.
    Accepts an incoming header or generates a new UUID.
    Adds it to the response header and makes it available on request.request_id.
    Also sets the logging context with request_id, tenant_id, and user_id.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Generate or use existing request ID
        request_id = request.META.get('HTTP_X_REQUEST_ID', '') or str(uuid.uuid4())
        request.request_id = request_id

        # Get tenant_id and user_id if available
        tenant_id = None
        user_id = None
        
        # Tenant is set by TenantMiddleware (runs after this)
        # We'll update the context in the response phase
        if hasattr(request, 'tenant') and request.tenant:
            tenant_id = str(request.tenant.id)
        
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = str(request.user.id)

        # Set initial logging context
        set_request_context(
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        response = self.get_response(request)

        # Clear logging context after request
        clear_request_context()

        # Add request ID to response header
        response['X-Request-ID'] = request_id
        return response


class LoggingContextMiddleware:
    """
    Update logging context with tenant and user after authentication.
    
    Must run AFTER AuthenticationMiddleware and TenantMiddleware.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Update context with authenticated user and tenant
        tenant_id = None
        user_id = None
        
        if hasattr(request, 'tenant') and request.tenant:
            tenant_id = str(request.tenant.id)
        
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = str(request.user.id)
        
        # Update the logging context (request_id already set)
        request_id = getattr(request, 'request_id', None)
        set_request_context(
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        
        return self.get_response(request)
