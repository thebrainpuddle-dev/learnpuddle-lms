# apps/webhooks/views.py
"""
Webhook management views.

Admin endpoints for managing webhook endpoints.
"""

import ipaddress
import logging
from urllib.parse import urlparse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from utils.decorators import admin_only, tenant_required

from .models import WebhookEndpoint, WebhookDelivery

logger = logging.getLogger(__name__)


# SSRF protection: block internal/private network URLs
_BLOCKED_HOSTNAMES = {'localhost', '127.0.0.1', '0.0.0.0', '::1', 'metadata.google.internal'}
_BLOCKED_DOMAINS = {'.local', '.internal', '.localhost'}


def _validate_webhook_url(url: str) -> str | None:
    """
    Validate webhook URL is safe (no SSRF).
    Returns error message if invalid, None if OK.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"

    if parsed.scheme != 'https':
        return "URL must use HTTPS"

    hostname = (parsed.hostname or '').lower()

    if not hostname:
        return "URL must have a hostname"

    # Block known internal hostnames
    if hostname in _BLOCKED_HOSTNAMES:
        return "URL must not point to internal hosts"

    # Block internal domain suffixes
    for suffix in _BLOCKED_DOMAINS:
        if hostname.endswith(suffix):
            return "URL must not point to internal domains"

    # Block Docker service names (common in compose setups)
    docker_services = {'web', 'db', 'redis', 'worker', 'flower', 'nginx', 'asgi', 'beat', 'postgres', 'celery'}
    if hostname in docker_services:
        return "URL must not point to internal services"

    # Block private/reserved IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            return "URL must not point to private/internal IP addresses"
    except ValueError:
        pass  # Not an IP address (it's a hostname), which is fine

    return None


class WebhookPagination(PageNumberPagination):
    page_size = 20


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def webhook_list_create(request):
    """
    GET: List all webhook endpoints for the tenant
    POST: Create a new webhook endpoint
    """
    if request.method == 'GET':
        endpoints = WebhookEndpoint.objects.filter(tenant=request.tenant)
        
        data = [{
            'id': str(ep.id),
            'name': ep.name,
            'url': ep.url,
            'events': ep.events,
            'is_active': ep.is_active,
            'total_deliveries': ep.total_deliveries,
            'successful_deliveries': ep.successful_deliveries,
            'failed_deliveries': ep.failed_deliveries,
            'success_rate': ep.success_rate,
            'last_triggered_at': ep.last_triggered_at.isoformat() if ep.last_triggered_at else None,
            'last_success_at': ep.last_success_at.isoformat() if ep.last_success_at else None,
            'last_failure_at': ep.last_failure_at.isoformat() if ep.last_failure_at else None,
            'created_at': ep.created_at.isoformat(),
        } for ep in endpoints]
        
        return Response(data)
    
    elif request.method == 'POST':
        name = request.data.get('name', '').strip()
        url = request.data.get('url', '').strip()
        events = request.data.get('events', [])
        
        if not name:
            return Response({'error': 'name is required'}, status=400)
        
        if not url:
            return Response({'error': 'url is required'}, status=400)
        
        # SSRF protection: validate URL is safe
        url_error = _validate_webhook_url(url)
        if url_error:
            return Response({'error': url_error}, status=400)
        
        if not events or not isinstance(events, list):
            return Response({'error': 'events must be a non-empty list'}, status=400)
        
        # Validate event types
        valid_events = [choice[0] for choice in WebhookEndpoint.EVENT_CHOICES]
        valid_events.append('*')  # Allow wildcard
        
        invalid = [e for e in events if e not in valid_events]
        if invalid:
            return Response({
                'error': f'Invalid event types: {invalid}',
                'valid_events': valid_events,
            }, status=400)
        
        endpoint = WebhookEndpoint.objects.create(
            tenant=request.tenant,
            name=name,
            url=url,
            events=events,
            created_by=request.user,
        )
        
        logger.info(f"Webhook endpoint created: {endpoint.name} for tenant {request.tenant.name}")
        
        return Response({
            'id': str(endpoint.id),
            'name': endpoint.name,
            'url': endpoint.url,
            'secret': endpoint.secret,
            'events': endpoint.events,
            'is_active': endpoint.is_active,
            'created_at': endpoint.created_at.isoformat(),
        }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def webhook_detail(request, webhook_id):
    """
    GET: Get webhook endpoint details
    PUT: Update webhook endpoint
    DELETE: Delete webhook endpoint
    """
    try:
        endpoint = WebhookEndpoint.objects.get(id=webhook_id, tenant=request.tenant)
    except WebhookEndpoint.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)
    
    if request.method == 'GET':
        return Response({
            'id': str(endpoint.id),
            'name': endpoint.name,
            'url': endpoint.url,
            'secret': endpoint.secret,
            'events': endpoint.events,
            'is_active': endpoint.is_active,
            'total_deliveries': endpoint.total_deliveries,
            'successful_deliveries': endpoint.successful_deliveries,
            'failed_deliveries': endpoint.failed_deliveries,
            'success_rate': endpoint.success_rate,
            'last_triggered_at': endpoint.last_triggered_at.isoformat() if endpoint.last_triggered_at else None,
            'last_success_at': endpoint.last_success_at.isoformat() if endpoint.last_success_at else None,
            'last_failure_at': endpoint.last_failure_at.isoformat() if endpoint.last_failure_at else None,
            'last_failure_reason': endpoint.last_failure_reason,
            'created_at': endpoint.created_at.isoformat(),
            'updated_at': endpoint.updated_at.isoformat(),
        })
    
    elif request.method == 'PUT':
        if 'name' in request.data:
            endpoint.name = request.data['name'].strip()
        
        if 'url' in request.data:
            url = request.data['url'].strip()
            if not url.startswith('https://'):
                return Response({'error': 'URL must use HTTPS'}, status=400)
            endpoint.url = url
        
        if 'events' in request.data:
            events = request.data['events']
            valid_events = [choice[0] for choice in WebhookEndpoint.EVENT_CHOICES]
            valid_events.append('*')
            invalid = [e for e in events if e not in valid_events]
            if invalid:
                return Response({'error': f'Invalid event types: {invalid}'}, status=400)
            endpoint.events = events
        
        if 'is_active' in request.data:
            endpoint.is_active = bool(request.data['is_active'])
        
        endpoint.save()
        
        return Response({
            'id': str(endpoint.id),
            'name': endpoint.name,
            'url': endpoint.url,
            'events': endpoint.events,
            'is_active': endpoint.is_active,
            'updated_at': endpoint.updated_at.isoformat(),
        })
    
    elif request.method == 'DELETE':
        endpoint.delete()
        logger.info(f"Webhook endpoint deleted: {endpoint.name}")
        return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def webhook_regenerate_secret(request, webhook_id):
    """
    Regenerate the webhook secret.
    """
    try:
        endpoint = WebhookEndpoint.objects.get(id=webhook_id, tenant=request.tenant)
    except WebhookEndpoint.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)
    
    import secrets
    endpoint.secret = secrets.token_hex(32)
    endpoint.save()
    
    return Response({
        'secret': endpoint.secret,
        'message': 'Secret regenerated. Update your webhook handler with the new secret.',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def webhook_test(request, webhook_id):
    """
    Send a test webhook to the endpoint.
    """
    try:
        endpoint = WebhookEndpoint.objects.get(id=webhook_id, tenant=request.tenant)
    except WebhookEndpoint.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)
    
    from .services import trigger_webhook
    
    test_payload = {
        'test': True,
        'message': 'This is a test webhook from Brain LMS',
        'triggered_by': request.user.email,
    }
    
    delivery_ids = trigger_webhook(
        str(request.tenant.id),
        'test.webhook',
        test_payload,
        delay=False,  # Deliver synchronously for immediate feedback
    )
    
    # Get the delivery result
    if delivery_ids:
        delivery = WebhookDelivery.objects.get(id=delivery_ids[0])
        return Response({
            'success': delivery.status == 'success',
            'status': delivery.status,
            'response_code': delivery.response_status_code,
            'response_time_ms': delivery.response_time_ms,
            'error': delivery.error_message if delivery.status != 'success' else None,
        })
    
    return Response({
        'success': False,
        'error': 'No delivery created - endpoint may not be subscribed to test events',
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def webhook_deliveries(request, webhook_id):
    """
    Get recent deliveries for a webhook endpoint.
    """
    try:
        endpoint = WebhookEndpoint.objects.get(id=webhook_id, tenant=request.tenant)
    except WebhookEndpoint.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)
    
    deliveries = WebhookDelivery.objects.filter(endpoint=endpoint).order_by('-created_at')[:50]
    
    data = [{
        'id': str(d.id),
        'event_type': d.event_type,
        'status': d.status,
        'attempt_count': d.attempt_count,
        'response_status_code': d.response_status_code,
        'response_time_ms': d.response_time_ms,
        'error_message': d.error_message,
        'created_at': d.created_at.isoformat(),
        'delivered_at': d.delivered_at.isoformat() if d.delivered_at else None,
    } for d in deliveries]
    
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def webhook_events(request):
    """
    Get list of available webhook event types.
    """
    events = [
        {
            'id': choice[0],
            'name': choice[1],
            'category': choice[0].split('.')[0],
        }
        for choice in WebhookEndpoint.EVENT_CHOICES
    ]
    
    return Response(events)
