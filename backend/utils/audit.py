# utils/audit.py

import logging

logger = logging.getLogger(__name__)


def log_audit(action, target_type, target_id='', target_repr='', changes=None, request=None, actor=None, tenant=None):
    """
    Create an audit log entry.

    Usage:
        log_audit('CREATE', 'User', target_id=str(user.id), target_repr=str(user), request=request)
    """
    from apps.tenants.models import AuditLog

    ip = None
    ua = ''
    request_id = ''

    if request:
        ip = _get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')[:500]
        request_id = getattr(request, 'request_id', '')
        if actor is None and hasattr(request, 'user') and request.user.is_authenticated:
            actor = request.user
        if tenant is None:
            tenant = getattr(request, 'tenant', None)

    try:
        AuditLog.objects.create(
            tenant=tenant,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            target_repr=str(target_repr)[:500],
            changes=changes or {},
            ip_address=ip,
            user_agent=ua,
            request_id=request_id,
        )
    except Exception:
        logger.exception("Failed to create audit log entry")


def _get_client_ip(request):
    """Extract client IP, respecting X-Forwarded-For behind proxy."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
