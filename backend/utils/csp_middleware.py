# utils/csp_middleware.py
"""
Content Security Policy (CSP) middleware with nonce support.

This middleware:
1. Generates unique nonces for each request
2. Attaches nonce to request object for use in templates
3. Sets appropriate CSP headers for Django-served content (admin, API)

Note: The React SPA served by nginx has separate CSP configuration.
This middleware focuses on Django admin and any server-rendered content.
"""

import secrets
from django.conf import settings


class CSPMiddleware:
    """
    Middleware to add Content-Security-Policy headers with nonce support.
    
    The nonce is a random value generated per-request that allows specific
    inline scripts/styles while blocking all others. This provides XSS 
    protection without breaking functionality.
    
    Usage in templates:
        <script nonce="{{ request.csp_nonce }}">...</script>
        <style nonce="{{ request.csp_nonce }}">...</style>
    """

    def __init__(self, get_response):
        self.get_response = get_response
        
        # CSP configuration from settings with secure defaults
        self.csp_enabled = getattr(settings, 'CSP_ENABLED', True)
        self.csp_report_only = getattr(settings, 'CSP_REPORT_ONLY', False)
        self.csp_report_uri = getattr(settings, 'CSP_REPORT_URI', None)
        
        # Paths that should have CSP (Django admin, etc.)
        # React SPA paths are handled by nginx
        self.csp_paths = getattr(settings, 'CSP_PATHS', ['/admin/', '/api/docs/', '/api/redoc/'])

    def __call__(self, request):
        # Generate nonce for this request
        request.csp_nonce = secrets.token_urlsafe(16)
        
        response = self.get_response(request)
        
        # Only add CSP header for specific paths (Django admin, docs)
        # API responses don't need CSP, and React SPA is handled by nginx
        if self.csp_enabled and self._should_add_csp(request):
            self._add_csp_header(request, response)
        
        return response

    def _should_add_csp(self, request):
        """Check if CSP should be added for this request."""
        path = request.path
        
        # Add CSP for Django admin and API documentation
        return any(path.startswith(csp_path) for csp_path in self.csp_paths)

    def _add_csp_header(self, request, response):
        """Build and add CSP header to response."""
        nonce = request.csp_nonce
        
        # Build CSP directives
        directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            f"style-src 'self' 'nonce-{nonce}'",
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "media-src 'self' blob:",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
            "upgrade-insecure-requests",
        ]
        
        # Add report-uri if configured
        if self.csp_report_uri:
            directives.append(f"report-uri {self.csp_report_uri}")
        
        csp_value = "; ".join(directives)
        
        # Use Report-Only header for testing without enforcement
        header_name = (
            "Content-Security-Policy-Report-Only" 
            if self.csp_report_only 
            else "Content-Security-Policy"
        )
        
        response[header_name] = csp_value


def get_csp_nonce(request):
    """
    Helper function to get CSP nonce from request.
    
    Use this in views or template tags to access the nonce:
        nonce = get_csp_nonce(request)
    """
    return getattr(request, 'csp_nonce', '')
