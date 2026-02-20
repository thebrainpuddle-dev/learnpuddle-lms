# apps/webhooks/services.py
"""
Webhook service for triggering and delivering webhooks.

Features:
- Event dispatching to subscribed endpoints
- HMAC signature generation
- Async delivery via Celery
- Retry logic with exponential backoff
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta
from typing import Any, Optional
from django.utils import timezone
import requests

from .models import WebhookEndpoint, WebhookDelivery

logger = logging.getLogger(__name__)


def generate_signature(payload: str, secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for webhook payload.
    
    The signature can be verified by recipients using:
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    is_valid = hmac.compare_digest(expected, received_signature)
    """
    return hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def trigger_webhook(
    tenant_id: str,
    event_type: str,
    payload: dict,
    delay: bool = True,
) -> list[str]:
    """
    Trigger webhook for an event.
    
    Finds all active endpoints subscribed to this event type
    and queues delivery tasks.
    
    Args:
        tenant_id: UUID of the tenant
        event_type: Event type (e.g., 'course.published')
        payload: Event payload data
        delay: If True, queue async delivery. If False, deliver synchronously.
    
    Returns:
        List of delivery IDs created
    """
    from apps.tenants.models import Tenant
    
    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist:
        logger.warning(f"Webhook trigger failed: tenant {tenant_id} not found")
        return []
    
    # Find active endpoints subscribed to this event
    endpoints = WebhookEndpoint.objects.filter(
        tenant=tenant,
        is_active=True,
    )
    
    # Filter by event subscription
    subscribed_endpoints = [
        ep for ep in endpoints
        if event_type in ep.events or '*' in ep.events
    ]
    
    if not subscribed_endpoints:
        return []
    
    delivery_ids = []
    
    for endpoint in subscribed_endpoints:
        # Create delivery record
        delivery = WebhookDelivery.objects.create(
            endpoint=endpoint,
            event_type=event_type,
            payload=payload,
            status='pending',
        )
        delivery_ids.append(str(delivery.id))
        
        # Update endpoint stats
        endpoint.total_deliveries += 1
        endpoint.last_triggered_at = timezone.now()
        endpoint.save(update_fields=['total_deliveries', 'last_triggered_at'])
        
        # Queue or execute delivery
        if delay:
            from .tasks import deliver_webhook
            deliver_webhook.delay(str(delivery.id))
        else:
            execute_delivery(delivery)
    
    logger.info(f"Triggered {len(delivery_ids)} webhooks for event {event_type}")
    
    return delivery_ids


def execute_delivery(delivery: WebhookDelivery) -> bool:
    """
    Execute a single webhook delivery.
    
    Returns True on success, False on failure.
    """
    endpoint = delivery.endpoint
    
    # Build payload with metadata
    full_payload = {
        'event_id': str(delivery.event_id),
        'event_type': delivery.event_type,
        'timestamp': timezone.now().isoformat(),
        'data': delivery.payload,
    }
    
    payload_json = json.dumps(full_payload, default=str)
    signature = generate_signature(payload_json, endpoint.secret)
    
    # Prepare headers
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-ID': str(delivery.id),
        'X-Webhook-Event': delivery.event_type,
        'X-Webhook-Signature': f'sha256={signature}',
        'X-Webhook-Timestamp': str(int(time.time())),
        'User-Agent': 'LearnPuddle-Webhook/1.0',
    }
    
    delivery.attempt_count += 1
    delivery.status = 'retrying'
    
    start_time = time.time()
    
    try:
        response = requests.post(
            endpoint.url,
            data=payload_json,
            headers=headers,
            timeout=30,
        )
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        delivery.response_status_code = response.status_code
        delivery.response_body = response.text[:5000]  # Truncate long responses
        delivery.response_time_ms = elapsed_ms
        delivery.delivered_at = timezone.now()
        
        # Success: 2xx status codes
        if 200 <= response.status_code < 300:
            delivery.status = 'success'
            delivery.save()
            
            # Update endpoint stats
            endpoint.successful_deliveries += 1
            endpoint.last_success_at = timezone.now()
            endpoint.save(update_fields=['successful_deliveries', 'last_success_at'])
            
            logger.info(f"Webhook delivered successfully: {delivery.id}")
            return True
        else:
            # Non-2xx response
            delivery.error_message = f"HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        delivery.error_message = "Request timed out"
    except requests.exceptions.ConnectionError as e:
        delivery.error_message = f"Connection error: {str(e)[:200]}"
    except Exception as e:
        delivery.error_message = f"Error: {str(e)[:200]}"
        logger.exception(f"Webhook delivery error: {delivery.id}")
    
    # Handle failure
    if delivery.attempt_count >= delivery.max_attempts:
        delivery.status = 'failed'
        endpoint.failed_deliveries += 1
        endpoint.last_failure_at = timezone.now()
        endpoint.last_failure_reason = delivery.error_message
        endpoint.save(update_fields=['failed_deliveries', 'last_failure_at', 'last_failure_reason'])
    else:
        # Schedule retry with exponential backoff
        delay_seconds = min(300, 10 * (2 ** (delivery.attempt_count - 1)))  # Max 5 minutes
        delivery.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
        delivery.status = 'retrying'
    
    delivery.save()
    logger.warning(f"Webhook delivery failed: {delivery.id} - {delivery.error_message}")
    
    return False


# Event helper functions
def emit_course_event(course, event_suffix: str, extra_data: Optional[dict] = None):
    """Emit a course-related webhook event."""
    payload = {
        'course_id': str(course.id),
        'title': course.title,
        'is_published': course.is_published,
    }
    if extra_data:
        payload.update(extra_data)
    
    trigger_webhook(str(course.tenant_id), f'course.{event_suffix}', payload)


def emit_user_event(user, event_suffix: str, extra_data: Optional[dict] = None):
    """Emit a user-related webhook event."""
    payload = {
        'user_id': str(user.id),
        'email': user.email,
        'role': user.role,
    }
    if extra_data:
        payload.update(extra_data)
    
    trigger_webhook(str(user.tenant_id), f'user.{event_suffix}', payload)


def emit_progress_event(progress, event_suffix: str, extra_data: Optional[dict] = None):
    """Emit a progress-related webhook event."""
    payload = {
        'user_id': str(progress.teacher_id),
        'course_id': str(progress.course_id),
        'status': progress.status,
        'progress_percentage': float(progress.progress_percentage),
    }
    if extra_data:
        payload.update(extra_data)
    
    trigger_webhook(str(progress.course.tenant_id), f'progress.{event_suffix}', payload)


def emit_assignment_event(submission, event_suffix: str, extra_data: Optional[dict] = None):
    """Emit an assignment-related webhook event."""
    assignment = submission.assignment
    payload = {
        'submission_id': str(submission.id),
        'assignment_id': str(assignment.id),
        'user_id': str(submission.teacher_id),
        'course_id': str(assignment.course_id),
        'status': submission.status,
    }
    if extra_data:
        payload.update(extra_data)
    
    trigger_webhook(str(assignment.course.tenant_id), f'assignment.{event_suffix}', payload)
